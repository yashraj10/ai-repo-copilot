# AI Repo Co-Pilot

**Ask questions about any codebase and get answers with exact file names and line numbers.**

This tool reads your code, understands it using AI, and gives you a report. Every answer is backed by real code — no guessing, no making things up.

---

## What Does It Do?

You point it at any code folder and ask a question in plain English:

```
python cli.py /path/to/code "your question here"
```

It reads the files, analyzes them, and gives you a report like this:

```
============================================================
  AI REPO CO-PILOT — ANALYSIS REPORT
============================================================

QUESTION: What does this app do

SUMMARY
----------------------------------------
The app is a social media sentiment analysis platform that
analyzes content from Reddit, Twitter, and YouTube.

CONFIDENCE: ● HIGH

HIGH RISK AREAS (2 found)
----------------------------------------
  1. README.md:3
     Describes the app as a sentiment analysis platform.

  2. backend/api/main.py:15-22
     Main API endpoint that processes social media data.

VALIDATION
----------------------------------------
  Schema:    [PASS]
  Citations: [PASS]

============================================================
  Completed in 2.9s (1 LLM call)
```

---

## Setup (5 minutes)

You need three things: **Python**, **this code**, and an **OpenAI API key**.

### Step 1: Get the code

Open your terminal (on Mac: search for "Terminal" in Spotlight).

```bash
git clone https://github.com/yashraj10/ai-repo-copilot.git
cd ai-repo-copilot
```

### Step 2: Set up Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **What does this do?** It creates a clean workspace for this project so it doesn't mess with anything else on your computer.

### Step 3: Get an OpenAI API key

1. Go to https://platform.openai.com/api-keys
2. Create an account (or sign in)
3. Click "Create new secret key"
4. Copy the key

**Important: You need a paid account with billing enabled. Free accounts will not work.**

### Step 4: Set your key

Paste your key into this command (replace the placeholder with your actual key):

```bash
export OPENAI_API_KEY="paste-your-key-here"
```

> **Note:** You need to run this every time you open a new terminal window.

### Step 5: You're done!

Try it:

```bash
python cli.py ./sample_repo "What does this code do"
```

---

## How to Use

### Analyze a folder on your computer

```bash
python cli.py ~/Desktop/my-project "Find security vulnerabilities"
```

### Analyze a GitHub repo

First download it, then analyze it:

```bash
git clone https://github.com/someone/their-repo.git /tmp/their-repo
python cli.py /tmp/their-repo "What does this app do"
```

### Ask any question

You can ask anything in plain English:

- `"What does this app do"`
- `"Find security vulnerabilities"`
- `"Where are API calls made"`
- `"How does authentication work"`
- `"Find bugs and potential issues"`
- `"What dependencies does this project use"`
- `"Explain the main function"`
- `"Find error handling patterns"`

### Options

| Command | What it does |
|---------|-------------|
| `python cli.py /path/to/code "question"` | Analyze and show report |
| `python cli.py /path/to/code "question" -v` | Show detailed logs (what files it reads, retries, etc.) |
| `python cli.py /path/to/code -o report.json` | Save report to a file |
| `python cli.py /path/to/code --json` | Output raw JSON (for scripts) |

---

## Supported Languages

The tool can read code in **40+ languages**:

Python, JavaScript, TypeScript, React (JSX/TSX), HTML, CSS, Java, Go, Rust, C, C++, C#, Ruby, PHP, Swift, Kotlin, Scala, Shell scripts, SQL, Dart, and many more.

It also reads config files like JSON, YAML, TOML, XML, .env, and Dockerfile.

---

## Troubleshooting

### "No module named 'langgraph'"
You forgot to activate the virtual environment:
```bash
source .venv/bin/activate
```

### "api_key must be set"
You forgot to set your OpenAI key:
```bash
export OPENAI_API_KEY="paste-your-key-here"
```

### "Cannot analyze reliably due to JSON parsing failure"
Your OpenAI API key doesn't have billing enabled. You need a paid account. Check at https://platform.openai.com/settings/organization/billing/overview

### Report says "not found" for files that exist
The tool reads up to 10 files per run. Try asking a more specific question that points to the file you care about.

---

## How It Works (Technical)

The tool runs a 5-step AI pipeline:

1. **Planner** — Reads your question and decides what to look for
2. **Executor** — Opens and reads the actual code files from your repo
3. **Analyzer** — Figures out what's relevant in the code it read
4. **Summarizer** — Uses GPT-4o-mini to write a structured report
5. **Verifier** — Checks that every citation points to real code that actually exists

If the verifier finds a problem, it sends the report back to step 4 to try again. This is why the tool never makes up file names or line numbers.

```
[START] → Plan → Execute → Analyze → Summarize → Verify → [END]
                                              ↑              |
                                              └── retry ─────┘
```

Built with **LangGraph** (a framework for building AI agents with state machines).

---

## For Developers

### Run the test suite

```bash
python -m eval.evaluator --phase 1-core      # 25 core tests
python -m eval.evaluator --phase 2-advanced   # 8 adversarial tests
```

Current score: **33/33**

The tests check things like:
- Does it refuse to make up files that don't exist?
- Does it handle retries when file reads fail?
- Does it block path traversal attacks?
- Does it reject corrupted data?
- Does it detect duplicate citations?

### Project structure

```
ai-repo-copilot/
├── cli.py                     ← Start here (main entry point)
├── agent/
│   ├── langgraph_workflow.py  ← AI pipeline (state machine)
│   ├── planner.py             ← Step 1: understand the question
│   ├── executor.py            ← Step 2: read code files
│   ├── analyzer.py            ← Step 3: decide what to do
│   ├── summarizer.py          ← Step 4: generate report (calls GPT)
│   └── verifier.py            ← Step 5: validate everything
├── tools/
│   ├── list_files.py          ← Lists files in a repo
│   └── read_file.py           ← Reads files with line numbers
├── eval/
│   ├── evaluator.py           ← Runs 33 tests
│   ├── schema_validate.py     ← Checks JSON structure
│   └── citation_validate.py   ← Checks citation accuracy
├── requirements.txt
└── README.md
```

### Key properties

- **No hallucinations** — Only cites files it actually read, lines that actually exist
- **Strict schema** — Every report follows the exact same JSON structure
- **Retry loop** — If validation fails, automatically tries again
- **Security aware** — Blocks path traversal attacks and symlink exploits
- **40+ languages** — Reads Python, JS, TS, Java, Go, Rust, C++, and more

---

