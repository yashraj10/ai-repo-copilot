"""
Executor node — calls tools to gather evidence from the repository.
Uses module-level imports so evaluator monkey-patching works.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from agent.state import AgentState
import tools.list_files as lf_mod
import tools.read_file as rf_mod


MAX_GLOBAL_RETRIES = 6
MAX_FILE_RETRIES = 3


def _extract_task_files(task: str) -> List[str]:
    patterns = [
        r'["\']([a-zA-Z0-9_/\\.\-]+\.\w{1,5})["\']',
        r'(?:file|path|in|from|of)\s+([a-zA-Z0-9_/\\.\-]+\.\w{1,5})',
        r'([a-zA-Z0-9_]+(?:/[a-zA-Z0-9_]+)*\.\w{1,5})',
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, task):
            candidate = m.group(1).strip().strip("'\"")
            if len(candidate) > 2 and not candidate.startswith('.'):
                found.append(candidate)
    return list(dict.fromkeys(found))


def _extract_task_line_numbers(task: str) -> List[Tuple[int, int]]:
    ranges = []
    for m in re.finditer(r'lines?\s+(\d[\d,]*)\s*(?:to|-)\s*(\d[\d,]*)', task, re.IGNORECASE):
        start = int(m.group(1).replace(',', ''))
        end = int(m.group(2).replace(',', ''))
        ranges.append((start, end))
    for m in re.finditer(r'line\s+(\d[\d,]*)', task, re.IGNORECASE):
        n = int(m.group(1).replace(',', ''))
        ranges.append((n, n))
    return ranges


def _pick_files_to_read(all_files: List[str], max_files: int = 6) -> List[str]:
    def score(p: str) -> int:
        lp = p.lower().replace("\\", "/")
        name = lp.rsplit("/", 1)[-1]
        # README and docs — always read first
        if name in ("readme.md", "readme.txt", "readme", "readme.rst"):
            return -1
        # Entry points
        if lp in ("main.py", "app.py", "server.py", "run.py", "index.js",
                   "index.ts", "index.tsx", "app.js", "app.ts", "app.tsx",
                   "src/main.py", "src/app.py", "src/index.js", "src/index.ts",
                   "src/index.tsx", "src/app.js", "src/app.ts", "src/app.tsx"):
            return 0
        if lp.endswith(("/settings.py", "/config.py")) or lp in (
            "config.yml", "config.yaml", "config.json", "config.toml", "config.ini",
            "package.json", "pyproject.toml", "setup.py", "setup.cfg",
            "cargo.toml", "go.mod", "gemfile",
        ):
            return 1
        if lp.endswith((".yml", ".yaml", ".toml", ".ini", ".cfg")):
            return 2
        # Source code in common directories
        if lp.startswith(("utils/", "src/", "app/", "lib/", "api/", "backend/", "frontend/src/")):
            return 3
        # Code files
        if lp.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                        ".java", ".rb", ".php", ".c", ".cpp", ".cs")):
            return 4
        # Skip lock files and generated files
        if name in ("package-lock.json", "yarn.lock", "poetry.lock", "uv.lock",
                     "pipfile.lock", "composer.lock", "gemfile.lock"):
            return 20
        return 10
    ranked = sorted(all_files, key=lambda p: (score(p), p))
    return ranked[:max_files]


def execute_plan(state: AgentState) -> AgentState:
    print("EXECUTOR: executing plan")

    listed_files: List[str] = []
    list_files_succeeded = False
    global_failures = [0]

    task_files = _extract_task_files(state.task)
    task_lines = _extract_task_line_numbers(state.task)

    for step in state.plan:
        print(f" - {step}")

        if step == "List repository files":
            print("   -> Calling list_files tool")
            try:
                result = lf_mod.list_files(state.repo_path)
                state.tool_calls.append({
                    "tool": "list_files",
                    "name": "list_files",
                    "repo_path": state.repo_path,
                    "returned_file_count": len(result.files),
                    "ignored_dir_count": result.ignored_count,
                    "result_status": "success",
                })
                state.retrieved_files.append({
                    "tool": "list_files",
                    "repo_path": state.repo_path,
                    "files": result.files,
                    "total_files": len(result.files),
                })
                listed_files = result.files
                list_files_succeeded = True
                print(f"   -> Found {len(result.files)} files (ignored dirs: {result.ignored_count})")
            except Exception as e:
                print(f"   !! list_files failed: {e}")
                state.tool_calls.append({
                    "tool": "list_files",
                    "name": "list_files",
                    "repo_path": state.repo_path,
                    "returned_file_count": 0,
                    "ignored_dir_count": 0,
                    "error": f"{type(e).__name__}: {e}",
                    "result_status": "error",
                })

        elif step == "Read relevant files":
            if list_files_succeeded and not listed_files:
                print("   !! No file list available. Skipping read_file.")
                continue

            if not listed_files and task_files:
                to_read = task_files
                print(f"   -> No file list; trying {len(to_read)} file(s) from task")
            elif not listed_files:
                to_read = ["main.py"]
                print("   -> No file list; trying default files")
            else:
                # Prioritize files mentioned in the task
                task_mentioned = []
                for tf in task_files:
                    tf_norm = tf.replace("\\", "/")
                    for lf in listed_files:
                        if lf.replace("\\", "/").endswith(tf_norm) or tf_norm.endswith(lf.replace("\\", "/")):
                            if lf not in task_mentioned:
                                task_mentioned.append(lf)
                            break
                # Fill remaining slots with ranked files
                remaining = [f for f in listed_files if f not in task_mentioned]
                ranked_remaining = _pick_files_to_read(remaining, max_files=10)
                to_read = task_mentioned + [f for f in ranked_remaining if f not in task_mentioned]
                to_read = to_read[:10]  # cap at 10
                print(f"   -> Reading {len(to_read)} files")

            for rel_path in to_read:
                if global_failures[0] >= MAX_GLOBAL_RETRIES:
                    print(f"     !! Global retry budget exhausted ({MAX_GLOBAL_RETRIES})")
                    break
                rel_path = os.path.normpath(rel_path)
                _read_with_retries(state, rel_path, global_failures, task_lines)

    return state


def _read_with_retries(
    state: AgentState,
    rel_path: str,
    global_failures: List[int],
    task_lines: List[Tuple[int, int]],
) -> None:
    """Read a file with retries. Falls back to chunk reads on failure."""

    # Check if task mentions specific lines for this file
    line_start = None
    line_end = None
    if len(task_lines) == 1 and task_lines[0][0] > 200:
        ls, le = task_lines[0]
        line_start = max(1, ls - 5)
        line_end = le + 5

    use_chunk_fallback = False  # Set True after first failure

    for attempt in range(1, MAX_FILE_RETRIES + 1):
        if global_failures[0] >= MAX_GLOBAL_RETRIES:
            break

        try:
            if line_start is not None:
                # Task specifies lines — always use chunk read
                res = rf_mod.read_file(state.repo_path, rel_path,
                                       line_start=line_start, line_end=line_end)
            elif use_chunk_fallback:
                # Previous attempt failed — try chunk read (first 200 lines)
                res = rf_mod.read_file(state.repo_path, rel_path,
                                       line_start=1, line_end=200)
            else:
                # Normal full read
                try:
                    res = rf_mod.read_file(state.repo_path, rel_path, max_lines=5000)
                except TypeError:
                    res = rf_mod.read_file(state.repo_path, rel_path)

            # Success
            state.tool_calls.append({
                "tool": "read_file",
                "name": "read_file",
                "repo_path": state.repo_path,
                "path": rel_path,
                "returned_lines": len(getattr(res, "lines", []) or []),
                "truncated": bool(getattr(res, "truncated", False)),
                "is_binary": bool(getattr(res, "is_binary", False)),
                "error": getattr(res, "error", None),
                "attempt": attempt,
                "result_status": "success",
            })
            state.retrieved_files.append({
                "tool": "read_file",
                "repo_path": state.repo_path,
                "path": getattr(res, "path", rel_path),
                "lines": getattr(res, "lines", []) or [],
                "total_lines": int(getattr(res, "total_lines", 0) or 0),
                "truncated": bool(getattr(res, "truncated", False)),
                "is_binary": bool(getattr(res, "is_binary", False)),
                "error": getattr(res, "error", None),
            })
            lines_read = len(getattr(res, "lines", []) or [])
            is_bin = bool(getattr(res, "is_binary", False))
            print(f"     -> Read {rel_path} ({lines_read} lines, "
                  f"truncated={bool(getattr(res, 'truncated', False))})"
                  + (" [BINARY/UNSUPPORTED]" if is_bin else ""))
            return

        except Exception as e:
            global_failures[0] += 1
            state.tool_calls.append({
                "tool": "read_file",
                "name": "read_file",
                "repo_path": state.repo_path,
                "path": rel_path,
                "returned_lines": 0,
                "error": f"{type(e).__name__}: {e}",
                "attempt": attempt,
                "result_status": "error",
            })
            if attempt < MAX_FILE_RETRIES:
                print(f"     !! Read failed ({attempt}/{MAX_FILE_RETRIES}) for {rel_path}: "
                      f"{type(e).__name__}: {e}")
                # On failure, switch to chunk read for next attempt
                use_chunk_fallback = True
            else:
                print(f"     !! Skipped {rel_path} after {MAX_FILE_RETRIES} attempts: "
                      f"{type(e).__name__}: {e}")

    # All attempts failed
    state.retrieved_files.append({
        "tool": "read_file",
        "repo_path": state.repo_path,
        "path": rel_path,
        "lines": [],
        "total_lines": 0,
        "is_binary": False,
        "error": "All read attempts failed",
    })