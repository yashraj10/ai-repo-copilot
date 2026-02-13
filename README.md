# AI Repo Co-Pilot

A tool-using AI agent that analyzes code repositories and produces citation-backed reports with strict JSON outputs. Every claim is grounded in actual file contents with exact line numbers — no hallucinations.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

# Analyze a repo
python cli.py /path/to/your/repo "Find security vulnerabilities"
```

## Usage

```bash
# General analysis (default task)
python cli.py ./my-project

# Specific question
python cli.py ./my-project "Where is the database connection configured?"

# JSON output (for piping/scripting)
python cli.py ./my-project --json

# Save report to file
python cli.py ./my-project -o report.json

# Quiet mode (suppress progress logs)
python cli.py ./my-project -q "Find error handling patterns"
```

## Example Output

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

## Architecture

```
[START] → plan → execute → analyze → route
                                       ├─→ summarize → verify → [retry?] → END
                                       ├─→ finalize (skip LLM) → END
                                       └─→ handle_error → END
```

Built with **LangGraph** for stateful graph execution with conditional routing and retry loops.

### Components
- **Planner** — classifies task type, extracts file references
- **Executor** — calls `list_files` and `read_file` tools with retry + chunk fallback
- **Analyzer** — routes based on evidence (empty repo, binary, security, normal)
- **Summarizer** — LLM call (GPT-4o-mini) with schema-clamped output
- **Verifier** — strict schema validation + evidence-grounded citation checking

### Key Properties
- **No hallucinations** — can only cite files it actually read, lines that actually exist
- **Strict schema** — no extra fields, no type coercion, no nested structures
- **Fail-loud** — symlinks, path traversal, tool errors all propagate to validation
- **Retry loop** — if validation fails, re-prompts LLM with error feedback

## Test Suite

33 adversarial tests across two phases:

```bash
python -m eval.evaluator --phase 1-core      # 25 core tests
python -m eval.evaluator --phase 2-advanced   # 8 advanced tests
```

Tests include: schema enforcement, citation grounding, hallucination traps, path traversal attacks, symlink detection, encoding edge cases, retry logic, binary file rejection, and more.

**Current score: 33/33**

## Project Structure

```
├── cli.py                   # CLI entry point
├── agent/
│   ├── langgraph_workflow.py  # LangGraph state graph
│   ├── state.py               # AgentState dataclass
│   ├── planner.py             # Task classification
│   ├── executor.py            # Tool orchestration
│   ├── analyzer.py            # Evidence routing
│   ├── summarizer.py          # LLM output generation
│   └── verifier.py            # Schema + citation validation
├── tools/
│   ├── list_files.py          # Filesystem walk tool
│   └── read_file.py           # Line-numbered file reader
├── eval/
│   ├── evaluator.py           # Test harness with mutations
│   ├── schema_validate.py     # Strict JSON schema checker
│   ├── citation_validate.py   # Evidence-grounded citation checker
│   └── test_cases.json        # 33 test definitions
└── requirements.txt
```