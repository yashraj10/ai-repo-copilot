# AI Repo Co-Pilot

An AI-powered tool that analyzes your code and tells you about security risks, bugs, and patterns — with exact file names and line numbers. No hallucinations — every claim is backed by actual code it read.

## How to Use (5 minutes)

### 1. Clone this repo
```bash
git clone https://github.com/yashraj10/ai-repo-copilot.git
cd ai-repo-copilot
```

### 2. Set up Python
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Add your OpenAI API key
You need an OpenAI API key. Get one at https://platform.openai.com/api-keys
```bash
export OPENAI_API_KEY="sk-paste-your-key-here"
```

### 4. Analyze any code
```bash
python cli.py /path/to/any/project "your question here"
```

That's it!

## What Can You Ask?

You can ask **any question in plain English**. The format is always:

```bash
python cli.py /path/to/code "your question here"
```

Some ideas:
- `"Find security vulnerabilities"`
- `"What does this app do"`
- `"Where are API calls made"`
- `"How does the authentication work"`
- `"Find error handling patterns"`
- `"What dependencies does this project use"`
- `"Explain the main function"`
- `"Find bugs and potential issues"`

The agent reads the actual code files and answers with exact file names and line numbers.

## Analyze a Local Project

```bash
python cli.py ~/Desktop/my-app "Find security vulnerabilities"
```

## Analyze a GitHub Repo

To analyze any public GitHub repo, clone it first, then analyze:

```bash
git clone https://github.com/someone/their-repo.git /tmp/their-repo
python cli.py /tmp/their-repo "Find security vulnerabilities"
```

Two steps: clone, then analyze. Works with any public repo.

## Options

```bash
# Quiet mode — just the report, no progress logs
python cli.py /path/to/code -q "your question"

# Save the report as JSON
python cli.py /path/to/code -o report.json

# Get raw JSON output (for piping to other tools)
python cli.py /path/to/code --json
```

## What You'll See

```
============================================================
  AI REPO CO-PILOT — ANALYSIS REPORT
============================================================

SUMMARY
----------------------------------------
Error handling in main.py includes a try-except block for
ZeroDivisionError. The divide function in utils/math.py
raises the error when the divisor is zero.

CONFIDENCE: ● HIGH

HIGH RISK AREAS (2 found)
----------------------------------------
  1. main.py:15-19
     Handles ZeroDivisionError when dividing two numbers.

  2. utils/math.py:15-18
     Raises ZeroDivisionError if the divisor is zero.

VALIDATION
----------------------------------------
  Schema:    [PASS]
  Citations: [PASS]

============================================================
  Completed in 2.3s (1 LLM call)
```

## Supported File Types

The tool can read code in **40+ languages** including:

Python, JavaScript, TypeScript, JSX/TSX, HTML, CSS, Java, Go, Rust, C/C++, C#, Ruby, PHP, Swift, Kotlin, Scala, Shell scripts, SQL, Dart, and many more.

It also reads config files like JSON, YAML, TOML, XML, .env, and Dockerfile.

## For Developers

If you want to modify the agent code or run the test suite:

```bash
python -m eval.evaluator --phase 1-core      # 25 core tests
python -m eval.evaluator --phase 2-advanced   # 8 advanced tests
```

Current score: **33/33**

### Architecture

```
[START] → plan → execute → analyze → route
                                       ├─→ summarize → verify → [retry?] → END
                                       ├─→ finalize (skip LLM) → END
                                       └─→ handle_error → END
```

Built with **LangGraph** for stateful graph execution with conditional routing and retry loops.

### How It Works
1. **Planner** — figures out what the task is asking
2. **Executor** — reads the actual files from your repo
3. **Analyzer** — decides what to do with the evidence
4. **Summarizer** — uses GPT-4o-mini to generate a structured report
5. **Verifier** — checks that every citation points to real code

### Key Properties
- **No hallucinations** — only cites files it actually read, lines that actually exist
- **Strict schema** — validated JSON output every time
- **Retry loop** — if validation fails, automatically re-prompts the AI
- **Security aware** — blocks path traversal attacks and symlink exploits

### Project Structure

```
├── cli.py                   # CLI entry point (start here)
├── agent/
│   ├── langgraph_workflow.py  # LangGraph state graph
│   ├── state.py               # Agent state
│   ├── planner.py             # Task classification
│   ├── executor.py            # Tool orchestration
│   ├── analyzer.py            # Evidence routing
│   ├── summarizer.py          # LLM output generation
│   └── verifier.py            # Schema + citation validation
├── tools/
│   ├── list_files.py          # Filesystem walk
│   └── read_file.py           # Line-numbered file reader
├── eval/
│   ├── evaluator.py           # Test harness
│   ├── schema_validate.py     # JSON schema checker
│   ├── citation_validate.py   # Citation checker
│   └── test_cases.json        # 33 test definitions
└── requirements.txt
```