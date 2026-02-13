from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ReadFileResult:
    repo_path: str
    path: str
    lines: List[str]          # each entry like "12| actual text"
    total_lines: int
    truncated: bool
    is_binary: bool = False
    error: Optional[str] = None


TEXT_EXTENSIONS = {
    # Python
    ".py", ".pyi", ".pyx",
    # JavaScript / TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".svg",
    # Systems
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".cs",
    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy",
    # Other languages
    ".go", ".rs", ".rb", ".php", ".swift", ".m", ".mm",
    ".r", ".R", ".jl", ".lua", ".pl", ".pm", ".ex", ".exs",
    ".hs", ".erl", ".clj", ".dart", ".v", ".zig",
    # Shell / scripting
    ".sh", ".bash", ".zsh", ".fish", ".bat", ".cmd", ".ps1",
    # Config / data
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".env", ".properties", ".gradle",
    # Docs / text
    ".md", ".txt", ".rst", ".csv", ".tsv", ".log",
    # SQL
    ".sql",
    # Docker / CI
    ".dockerfile",
    # Misc
    ".graphql", ".proto", ".tf", ".hcl",
}


def read_file(
    repo_path: str,
    rel_path: str,
    max_lines: int = 200,
    max_chars: int = 50_000,
    allowed_extensions: Optional[set[str]] = None,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
) -> ReadFileResult:
    """
    Read a text file from repo_path/rel_path and return line-numbered content.
    Safety:
      - prevents path traversal
      - blocks symlinks + realpath escape
      - returns is_binary=True for unsupported extensions (does NOT raise)
      - supports chunk reads with line_start/line_end (1-indexed, inclusive)
    """
    allowed_extensions = allowed_extensions or TEXT_EXTENSIONS

    # Normalize + block traversal
    norm = os.path.normpath(rel_path)
    if norm.startswith("..") or os.path.isabs(norm):
        raise ValueError(f"Invalid rel_path (path traversal blocked): {rel_path}")

    full_path = os.path.join(repo_path, norm)

    # Block symlinks
    if os.path.islink(full_path):
        raise ValueError(f"Symlink not allowed: {rel_path}")

    # Block realpath escape
    repo_real = os.path.realpath(repo_path)
    full_real = os.path.realpath(full_path)
    if not (full_real == repo_real or full_real.startswith(repo_real + os.sep)):
        raise ValueError(f"Path escapes repo via symlink/realpath: {rel_path}")

    if not os.path.isfile(full_real):
        raise FileNotFoundError(f"File not found: {full_path}")

    ext = os.path.splitext(norm)[1].lower()
    if ext and ext not in allowed_extensions:
        # Don’t crash the agent – mark binary/unsupported
        return ReadFileResult(
            repo_path=repo_path,
            path=norm,
            lines=[],
            total_lines=0,
            truncated=False,
            is_binary=True,
            error=f"Unsupported/binary file type: {ext}",
        )

    # Read file as text
    with open(full_real, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    truncated = False
    if len(raw) > max_chars:
        raw = raw[:max_chars]
        truncated = True

    raw_lines = raw.splitlines()
    total_lines = len(raw_lines)

    # Optional chunking by line range (1-indexed inclusive)
    if line_start is not None or line_end is not None:
        ls = 1 if line_start is None else max(1, int(line_start))
        le = total_lines if line_end is None else max(ls, int(line_end))
        # slice is 0-indexed and end-exclusive
        raw_lines = raw_lines[ls - 1 : le]

        numbered = [f"{(ls - 1) + i + 1}| {line}" for i, line in enumerate(raw_lines)]
        return ReadFileResult(
            repo_path=repo_path,
            path=norm,
            lines=numbered,
            total_lines=total_lines,
            truncated=truncated,
            is_binary=False,
            error=None,
        )

    # Default behavior: limit by max_lines
    if total_lines > max_lines:
        raw_lines = raw_lines[:max_lines]
        truncated = True

    numbered = [f"{i+1}| {line}" for i, line in enumerate(raw_lines)]
    return ReadFileResult(
        repo_path=repo_path,
        path=norm,
        lines=numbered,
        total_lines=total_lines,
        truncated=truncated,
        is_binary=False,
        error=None,
    )