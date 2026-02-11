from agent.state import AgentState
from tools.list_files import list_files
from tools.read_file import read_file


def execute_plan(state: AgentState) -> AgentState:
    print("EXECUTOR: executing plan")

    listed_files = []

    for step in state.plan:
        print(f" - {step}")

        if step == "List repository files":
            print("   -> Calling list_files tool")
            result = list_files(state.repo_path)

            state.tool_calls.append({
                "tool": "list_files",
                "repo_path": state.repo_path,
                "returned_file_count": len(result.files),
                "ignored_dir_count": result.ignored_count,
            })

            listed_files = result.files

            state.retrieved_files.append({
                "tool": "list_files",
                "repo_path": state.repo_path,
                "files": result.files,
                "total_files": len(result.files),
            })

            print(f"   -> Found {len(result.files)} files (ignored dirs: {result.ignored_count})")

        if step == "Read relevant files":
            if not listed_files:
                print("   !! No file list available. Skipping read_file.")
                continue

            # Read first 2 files for now (we’ll make this smarter later)
            to_read = listed_files[:2]
            print(f"   -> Reading {len(to_read)} files")

            for rel_path in to_read:
                res = read_file(state.repo_path, rel_path)

                state.tool_calls.append({
                    "tool": "read_file",
                    "repo_path": state.repo_path,
                    "path": rel_path,
                    "returned_lines": len(res.lines),
                    "truncated": res.truncated,
                })

                state.retrieved_files.append({
                    "tool": "read_file",
                    "repo_path": state.repo_path,
                    "path": res.path,
                    "lines": res.lines,
                    "total_lines": res.total_lines,
                    "truncated": res.truncated,
                })

                print(f"     -> Read {rel_path} ({len(res.lines)} lines, truncated={res.truncated})")

    return state
