# 🤖 Multi-Agent Code Generator

Autonomous coding agent with iterative refinement

    Planning Agent: Breaks down requirements into concrete tasks
    Research Agent: Gathers relevant technical knowledge
    Executor Agent: Generates complete, working code files
    Critic Agent: Validates output quality and provides feedback
    Automatic file extraction from code blocks
    Iterative improvement (up to 5 cycles)
    ZIP download of generated projects

Use cases: Generate full applications, build React components, create Python scripts, scaffold entire projects

---

Multi-Agent Pipeline Pattern

```
User Request
     ↓
[Planner Agent] ──→ Task Breakdown
     ↓
[Researcher Agent] ──→ Knowledge Gathering
     ↓
[Executor Agent] ──→ Output Generation
     ↓
[Critic Agent] ──→ Quality Check
     ↓
Pass? ──No──→ Feedback Loop (back to Planner)
     ↓ Yes
Final Output
```

---

## 📦 Installation

### Prerequisites
- Python 3.8+
- OpenAI API key

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/blakebrandon-hub/Multi-Agent-Code-Generator
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set OpenAI API key**
```bash
export OPENAI_API_KEY='your-api-key-here'
```

4. **Run the application**
```bash
python app.py
```

5. **Open in browser**
```
http://localhost:5000
```

---

<img width="2560" height="1440" alt="image" src="https://github.com/user-attachments/assets/413adad2-7f2e-405c-b231-ddd60fd1d0dc" />
