import json
import os
import re
from flask import Flask, render_template, request, jsonify, send_file
from openai import OpenAI
import threading
from datetime import datetime
import zipfile
from io import BytesIO

# ---------------------------------------------------
# Configuration
# ---------------------------------------------------

MODEL = "gpt-5.4-mini"
MAX_ITERATIONS = 5
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Store job results in memory (in production, use Redis or database)
job_results = {}

# ---------------------------------------------------
# LLM Wrapper
# ---------------------------------------------------

def call_llm(system_prompt, user_prompt):
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------
# Agent Base Class
# ---------------------------------------------------

class Agent:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt

    def run(self, prompt):
        return call_llm(self.system_prompt, prompt)


# ---------------------------------------------------
# Planner Agent
# ---------------------------------------------------

planner = Agent(
    "planner",
"""
You are a planning agent.

Break the user's goal into a list of concrete tasks.

Return JSON ONLY in this format:

{
  "tasks": [
    "task1",
    "task2",
    "task3"
  ]
}
"""
)


# ---------------------------------------------------
# Research Agent
# ---------------------------------------------------

researcher = Agent(
    "researcher",
"""
You are a research agent.

Gather relevant knowledge needed to complete the tasks.

Return structured information that will help produce the final result.

Focus on facts, explanations, and useful data.
"""
)


# ---------------------------------------------------
# Executor Agent
# ---------------------------------------------------

executor = Agent(
    "executor",
"""
You are an execution agent responsible for producing COMPLETE, WORKING code.

You MUST internally iterate and refine your output before returning the final result.

Follow this exact internal process:

---

### Stage 1: Initial Build
- Generate a full first version of the solution
- Include ALL required files
- Do not worry about perfection

---

### Stage 2: Self-Review
Critically evaluate:
- Missing files or incomplete components
- Bugs or broken logic
- Integration issues between files
- Violations of the user's requirements

---

### Stage 3: Revision
- Fix all identified issues
- Improve structure and correctness
- Ensure everything is runnable

---

### Stage 4: Final Validation
Before output:
- Ensure ALL files are present
- Ensure code is complete (no placeholders)
- Ensure correct formatting with ```filename.ext blocks

---

### OUTPUT RULES (CRITICAL)

- ONLY output the FINAL version
- DO NOT show drafts or reasoning
- Each file MUST be in its own code block:
  ```filename.ext
  code...

Example output format:

```index.html
<!DOCTYPE html>
<html>
...
</html>
```

```styles.css
body {
...
}
```

```script.js
function calculate() {
...
}
```

For non-code tasks, provide clear structured answers.
"""
)


# ---------------------------------------------------
# Critic Agent
# ---------------------------------------------------

critic = Agent(
    "critic",
"""
You are a critic agent.

Evaluate whether the output satisfies the goal.

If the goal was to build/create something with code:
- Check if actual code files were generated (look for ```filename blocks)
- Verify the code is complete and functional
- Ensure all necessary files are present

Return JSON ONLY:

{
  "pass": true or false,
  "feedback": "explanation"
}

Pass = true if the output fully satisfies the goal.
Pass = false if code is missing, incomplete, or if a tutorial was provided instead of actual code.
"""
)


# ---------------------------------------------------
# File Extractor
# ---------------------------------------------------

def extract_and_save_files(result, job_id):
    """
    Extract code blocks with filenames and save them to OUTPUT_DIR.
    """
    pattern = r'```(\S+)\n(.*?)```'
    matches = re.findall(pattern, result, re.DOTALL)
    
    if not matches:
        return []
    
    output_folder = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_folder, exist_ok=True)
    
    saved_files = []
    
    for filename, content in matches:
        if '.' not in filename:
            continue
            
        filepath = os.path.join(output_folder, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content.strip())
        
        saved_files.append(filepath)
    
    return saved_files


# ---------------------------------------------------
# Optional RAG Memory
# ---------------------------------------------------

def retrieve_memory(goal):
    return ""


# ---------------------------------------------------
# Orchestrator (Modified for Flask)
# ---------------------------------------------------

def run_agent(goal, job_id):
    """
    Run the agent system and update job_results with progress.
    """
    
    state = {
        "goal": goal,
        "tasks": [],
        "research": "",
        "result": "",
        "feedback": "",
        "files": [],
        "status": "running",
        "current_iteration": 0,
        "logs": []
    }
    
    job_results[job_id] = state

    try:
        for step in range(MAX_ITERATIONS):
            state["current_iteration"] = step + 1
            state["logs"].append(f"Starting iteration {step + 1}")

            # Retrieve memory
            memory = retrieve_memory(state["goal"])

            # Planner
            planner_prompt = f"""
Goal:
{state['goal']}

Memory:
{memory}
"""
            state["logs"].append("Running planner...")
            plan_response = planner.run(planner_prompt)

            try:
                data = json.loads(plan_response)
                state["tasks"] = data["tasks"]
                state["logs"].append(f"Tasks identified: {len(data['tasks'])}")
            except:
                state["logs"].append("Planner JSON parse failed")
                continue

            # Research
            research_prompt = f"""
Tasks:
{state['tasks']}
"""
            state["logs"].append("Running researcher...")
            state["research"] = researcher.run(research_prompt)
            state["logs"].append("Research gathered")

            # Execute
            execute_prompt = f"""
Goal:
{state['goal']}

Tasks:
{state['tasks']}

Research:
{state['research']}
"""
            state["logs"].append("Running executor...")
            state["result"] = executor.run(execute_prompt)
            state["logs"].append("Result generated")

            # Extract and save files
            state["logs"].append("Extracting files...")
            state["files"] = extract_and_save_files(state["result"], job_id)
            state["logs"].append(f"Saved {len(state['files'])} file(s)")

            # Critic
            critic_prompt = f"""
Goal:
{state['goal']}

Result:
{state['result']}

Files generated: {len(state['files'])}
"""
            state["logs"].append("Running critic...")
            review = critic.run(critic_prompt)

            try:
                review_data = json.loads(review)
            except:
                state["logs"].append("Critic JSON parse failed")
                continue

            if review_data["pass"]:
                state["logs"].append("✓ Critic approved the result")
                state["status"] = "completed"
                state["feedback"] = review_data["feedback"]
                return

            else:
                state["logs"].append(f"✗ Critic feedback: {review_data['feedback']}")
                state["feedback"] = review_data["feedback"]
                state["goal"] += f"\n\nImprove the result using this feedback:\n{review_data['feedback']}"

        state["status"] = "completed"
        state["logs"].append("Reached iteration limit")
        
    except Exception as e:
        state["status"] = "error"
        state["logs"].append(f"Error: {str(e)}")


# ---------------------------------------------------
# Flask Routes
# ---------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/generate', methods=['POST'])
def generate():
    """Start a new agent job"""
    data = request.json
    goal = data.get('goal', '')
    
    if not goal:
        return jsonify({"error": "No goal provided"}), 400
    
    # Generate unique job ID
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Start agent in background thread
    thread = threading.Thread(target=run_agent, args=(goal, job_id))
    thread.start()
    
    return jsonify({"job_id": job_id})


@app.route('/api/status/<job_id>')
def get_status(job_id):
    """Get the current status of a job"""
    if job_id not in job_results:
        return jsonify({"error": "Job not found"}), 404
    
    state = job_results[job_id]
    
    return jsonify({
        "status": state["status"],
        "current_iteration": state["current_iteration"],
        "logs": state["logs"],
        "tasks": state["tasks"],
        "files": [os.path.basename(f) for f in state["files"]],
        "result": state["result"] if state["status"] == "completed" else "",
        "feedback": state["feedback"]
    })


@app.route('/api/download/<job_id>')
def download_files(job_id):
    """Download all generated files as a ZIP"""
    if job_id not in job_results:
        return jsonify({"error": "Job not found"}), 404
    
    state = job_results[job_id]
    
    if not state["files"]:
        return jsonify({"error": "No files generated"}), 404
    
    # Create ZIP file in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filepath in state["files"]:
            zf.write(filepath, os.path.basename(filepath))
    
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'agent_output_{job_id}.zip'
    )


if __name__ == "__main__":
    print("\n" + "="*50)
    print("Multi-Agent Flask Web App")
    print("="*50)
    print(f"Output directory: {OUTPUT_DIR}")
    print("Starting server on http://localhost:5000")
    print("="*50 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
