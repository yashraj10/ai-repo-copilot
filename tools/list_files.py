from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ListFilesResult:
    repo_path: str
    files: List[str]
    ignored_count: int


DEFAULT_IGNORE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
}


def list_files(
    repo_path: str,
    ignore_dirs: Optional[set[str]] = None,
    max_files: int = 5000,
) -> ListFilesResult:
    """
    Safely list files in a repository.
    - Returns relative paths (portable)
    - Skips common junk directories
    - Caps number of files to avoid runaway scans
    """
    if not os.path.isdir(repo_path):
        raise ValueError(f"repo_path is not a directory: {repo_path}")

    ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS

    files: List[str] = []
    ignored_count = 0

    for root, dirs, filenames in os.walk(repo_path):
        # Mutate dirs in-place so os.walk does not traverse ignored dirs
        pruned = []
        for d in list(dirs):
            if d in ignore_dirs:
                pruned.append(d)
        for d in pruned:
            dirs.remove(d)
            ignored_count += 1

        for name in filenames:
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, repo_path)
            files.append(rel_path)

            if len(files) >= max_files:
                return ListFilesResult(repo_path=repo_path, files=files, ignored_count=ignored_count)

    files.sort()
    return ListFilesResult(repo_path=repo_path, files=files, ignored_count=ignored_count)
