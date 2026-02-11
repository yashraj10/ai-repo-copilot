from agent.state import AgentState
from tools.list_files import list_files


def execute_plan(state: AgentState) -> AgentState:
    print("EXECUTOR: executing plan")

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

            state.retrieved_files.append({
                "tool": "list_files",
                "repo_path": state.repo_path,
                "files": result.files[:50],
                "total_files": len(result.files),
            })

            print(f"   -> Found {len(result.files)} files (ignored dirs: {result.ignored_count})")

    return state
