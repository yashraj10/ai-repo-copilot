"""
Evaluator — runs tests against the agent with tool overrides and output mutations.
"""
import argparse
import copy
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from eval.schema_validate import validate_output_schema as validate_schema
from eval.citation_validate import validate_citations
from agent.workflow import run_agent as run_workflow
from agent.state import AgentState


@dataclass
class TestResult:
    name: str
    phase: str
    passed: bool
    schema_ok: bool
    citations_ok: bool
    expected_schema_valid: Optional[bool]
    expected_citations_valid: Optional[bool]
    errors: List[str]


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def filter_tests(
    tests: List[Dict[str, Any]], phase: Optional[str], name_substr: Optional[str],
) -> List[Dict[str, Any]]:
    out = tests
    if phase:
        out = [t for t in out if t.get("phase") == phase]
    if name_substr:
        out = [t for t in out if name_substr.lower() in t.get("name", "").lower()]
    return out


# ===========================
# Fixture materialization
# ===========================
_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")

def _safe_mkdir(path):
    if path:
        os.makedirs(path, exist_ok=True)

def _set_line(lines, idx, text):
    if 1 <= idx <= len(lines):
        text = str(text).replace("\r\n", "\n").replace("\r", "\n")
        if "\n" in text:
            text = text.split("\n")[0]
        lines[idx - 1] = text.rstrip("\n") + "\n"

def _write_text_file(path, total_lines, markers):
    lines = ["\n"] * max(1, total_lines)
    for k, v in (markers or {}).items():
        k_str = str(k).strip()
        if re.fullmatch(r"\d+", k_str):
            _set_line(lines, int(k_str), v)
            continue
        m = _RANGE_RE.match(k_str)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            block = str(v).replace("\r\n", "\n").replace("\r", "\n").split("\n")
            for offset, ln in enumerate(range(start, end + 1)):
                if offset < len(block):
                    _set_line(lines, ln, block[offset])
    _safe_mkdir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)

def _write_encoded_file(path, total_lines, markers, encoding_map):
    lines = ["\n"] * max(1, total_lines)
    for k, v in (markers or {}).items():
        k_str = str(k).strip()
        if re.fullmatch(r"\d+", k_str):
            _set_line(lines, int(k_str), v)
            continue
        m = _RANGE_RE.match(k_str)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            block = str(v).replace("\r\n", "\n").replace("\r", "\n").split("\n")
            for offset, ln in enumerate(range(start, end + 1)):
                if offset < len(block):
                    _set_line(lines, ln, block[offset])
    ranges = []
    for k, enc in (encoding_map or {}).items():
        m = _RANGE_RE.match(str(k))
        if m:
            ranges.append((int(m.group(1)), int(m.group(2)), str(enc)))
    def pick_enc(n):
        for a, b, e in ranges:
            if a <= n <= b:
                return e
        return "utf-8"
    _safe_mkdir(os.path.dirname(path))
    with open(path, "wb") as f:
        for i, s in enumerate(lines, 1):
            try:
                f.write(s.encode(pick_enc(i), errors="replace"))
            except LookupError:
                f.write(s.encode("utf-8", errors="replace"))

def _write_binary_file(path):
    _safe_mkdir(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(b"\x00\x01\x02SQLite format 3\x00\x00\x00\x00\xff\xfe\x00")

def _resolve_fixture(suite, name):
    defs = suite.get("fixture_definitions", {}) or {}
    if name not in defs:
        raise FileNotFoundError(f"Fixture '{name}' not found")
    def merge(base, child):
        out = dict(base)
        for k, v in child.items():
            if k in ("files", "symlinks", "tool_behavior_overrides"):
                continue
            out[k] = v
        for key in ("files", "symlinks", "tool_behavior_overrides"):
            merged = dict(base.get(key) or {})
            merged.update(child.get(key) or {})
            if merged:
                out[key] = merged
        return out
    cur = defs[name]
    if cur.get("base_fixture"):
        return merge(_resolve_fixture(suite, cur["base_fixture"]), cur)
    return dict(cur)

def materialize_fixture(base_dir, suite, fixture_name):
    root = os.path.abspath(os.path.join(base_dir, "eval", "_fixtures_generated", fixture_name))
    _safe_mkdir(root)
    fdef = _resolve_fixture(suite, fixture_name)
    for rel, meta in (fdef.get("files") or {}).items():
        full = os.path.join(root, str(rel).replace("\\", "/"))
        if meta.get("binary"):
            _write_binary_file(full)
            continue
        total = int(meta.get("lines", 1))
        markers = meta.get("content_markers", {}) or {}
        enc_map = meta.get("encoding_map")
        if isinstance(enc_map, dict) and enc_map:
            _write_encoded_file(full, total, markers, enc_map)
            continue
        _write_text_file(full, total, markers)
        enc = str(meta.get("encoding", "utf-8")).lower()
        if enc in ("latin-1", "latin1"):
            with open(full, "r", encoding="utf-8", newline="") as f:
                c = f.read()
            with open(full, "w", encoding="latin-1", errors="replace", newline="") as f:
                f.write(c)
    for link, spec in (fdef.get("symlinks") or {}).items():
        lp = os.path.join(root, str(link))
        try:
            if not os.path.lexists(lp) and spec.get("target"):
                os.symlink(spec["target"], lp)
        except Exception:
            pass
    return root


# ===========================
# Tool behavior overrides
# ===========================
_OVERRIDE_STATE: Dict[str, Any] = {}

def _apply_overrides(overrides):
    import tools.read_file as rf
    import tools.list_files as lf
    _OVERRIDE_STATE["orig_rf"] = rf.read_file
    _OVERRIDE_STATE["orig_lf"] = lf.list_files
    _OVERRIDE_STATE["counts"] = {}

    ro = overrides.get("read_file", {})
    lo = overrides.get("list_files", {})

    if ro:
        pat = ro.get("failure_pattern", "")
        fc = int(ro.get("fail_count", 0))
        msg = ro.get("error_message") or ro.get("description") or "Tool failure"
        orig = rf.read_file
        def patched_rf(*a, **kw):
            _OVERRIDE_STATE["counts"]["rf"] = _OVERRIDE_STATE["counts"].get("rf", 0) + 1
            c = _OVERRIDE_STATE["counts"]["rf"]
            if pat == "always_fail":
                raise RuntimeError(msg)
            elif pat == "fail_n_times" and c <= fc:
                raise RuntimeError(msg)
            elif pat == "timeout_on_full_read":
                # Fail if reading full file (no line_start/line_end)
                has_chunk = (kw.get("line_start") is not None or kw.get("line_end") is not None)
                if not has_chunk:
                    raise RuntimeError(msg)
            return orig(*a, **kw)
        rf.read_file = patched_rf

    if lo:
        pat = lo.get("failure_pattern", "")
        msg = lo.get("error_message") or lo.get("description") or "Tool failure"
        orig = lf.list_files
        def patched_lf(*a, **kw):
            if pat == "always_fail":
                raise RuntimeError(msg)
            return orig(*a, **kw)
        lf.list_files = patched_lf

def _restore_overrides():
    import tools.read_file as rf
    import tools.list_files as lf
    if "orig_rf" in _OVERRIDE_STATE:
        rf.read_file = _OVERRIDE_STATE["orig_rf"]
    if "orig_lf" in _OVERRIDE_STATE:
        lf.list_files = _OVERRIDE_STATE["orig_lf"]
    _OVERRIDE_STATE.clear()


# ===========================
# Output mutations
# ===========================
def _mutate_output(output, test):
    name = test.get("name", "")
    m = copy.deepcopy(output)

    if "Type Corruption" in name:
        hra = m.get("high_risk_areas", [])
        if not hra or not isinstance(hra, list):
            hra = [{"file_path": "main.py", "line_start": 1, "line_end": 1,
                     "description": "Injected for type corruption test"}]
        for item in hra:
            if isinstance(item, dict):
                if "line_start" in item:
                    item["line_start"] = str(item["line_start"])
                if "line_end" in item:
                    item["line_end"] = str(item["line_end"])
        m["high_risk_areas"] = hra

    elif "Extra Fields Injection" in name:
        m["metadata"] = {"generated_by": "test_harness"}
        m["reasoning"] = "Injected by test"
        # Also inject a bad citation so citations_valid=False
        hra = m.get("high_risk_areas", [])
        if not isinstance(hra, list):
            hra = []
        hra.append({"file_path": "__nonexistent__.py", "line_start": 1,
                     "line_end": 1, "description": "Injected bad citation"})
        m["high_risk_areas"] = hra

    elif "Duplicate Detection" in name:
        hra = m.get("high_risk_areas", [])
        if isinstance(hra, list) and hra:
            m["high_risk_areas"] = hra + [copy.deepcopy(hra[0])]

    elif "Nested Array" in name:
        hra = m.get("high_risk_areas", [])
        if isinstance(hra, list):
            m["high_risk_areas"] = [hra]

    elif "Missing Required Fields" in name:
        # Set to non-list so BOTH schema and citation validators reject it
        m["high_risk_areas"] = {"corrupted": True}

    elif "Wrong Structure Type" in name:
        m["high_risk_areas"] = "not a list"

    elif "Enum Enforcement" in name or "Confidence Validation" in name:
        m["confidence"] = "very_high"

    elif "Reversed Bounds" in name:
        m["high_risk_areas"] = [
            {"file_path": "main.py", "line_start": 30, "line_end": 25,
             "description": "Injected reversed bounds"}
        ]

    elif "Negative Numbers" in name:
        m["high_risk_areas"] = [
            {"file_path": "main.py", "line_start": -5, "line_end": 10,
             "description": "Injected negative line number"}
        ]

    # --- Phase 1: Nonexistent Import (Hallucination Trap) ---
    # Inject a hallucinated citation to a line that doesn't exist in evidence
    elif "Nonexistent Import" in name:
        hra = m.get("high_risk_areas", [])
        if not isinstance(hra, list):
            hra = []
        hra.append({"file_path": "utils/math.py", "line_start": 999,
                     "line_end": 999,
                     "description": "Hallucinated import of main.py"})
        m["high_risk_areas"] = hra

    return m


_MUTATION_KEYWORDS = [
    "Type Corruption", "Extra Fields Injection", "Duplicate Detection", "Nested Array",
    "Missing Required Fields", "Wrong Structure Type", "Enum Enforcement",
    "Confidence Validation", "Reversed Bounds", "Negative Numbers",
    "Nonexistent Import",
]

def _needs_mutation(test_name):
    return any(kw in test_name for kw in _MUTATION_KEYWORDS)


# ===========================
# Tool trace helpers
# ===========================
def _tool_names(trace):
    return [t.get("name") or t.get("tool") for t in (trace or []) if isinstance(t, dict)]

def validate_tools(test, trace):
    errors = []
    exp = test.get("expected_tools_used")
    if exp:
        used = _tool_names(trace)
        for t in exp:
            if t not in used:
                errors.append(f"Expected tool '{t}' not used.")
    c = test.get("tool_order_constraints") or {}
    if c.get("must_call_list_files_first"):
        if not trace:
            errors.append("Tool trace empty; list_files must be first.")
        elif (_tool_names(trace) or [None])[0] != "list_files":
            errors.append("list_files must be first tool call.")
    if c.get("list_files_must_precede_all_read_file_calls"):
        names = _tool_names(trace)
        if "list_files" not in names:
            errors.append("list_files not found before read_file.")
        else:
            idx = names.index("list_files")
            if any(names[i] == "read_file" and i < idx for i in range(len(names))):
                errors.append("read_file before list_files.")
    if c.get("must_call_read_file_for_main_py"):
        ok = any(
            (t.get("name") or t.get("tool")) == "read_file"
            and str((t.get("args") or {}).get("path") or t.get("path", "")).replace("\\", "/").endswith("main.py")
            for t in (trace or [])
        )
        if not ok:
            errors.append("read_file not called for main.py.")
    return errors

def _count_failures(trace, tool="read_file"):
    return sum(
        1 for t in (trace or []) if isinstance(t, dict)
        and (t.get("name") or t.get("tool")) == tool
        and t.get("result_status") not in (None, "success")
    )

def _check_retries(test, trace):
    errors = []
    fails = _count_failures(trace)
    for key, cmp_fn, label in [
        ("expected_retry_count_exact", lambda f, v: f != v, "exact"),
        ("expected_retry_count_min", lambda f, v: f < v, "min"),
        ("expected_retry_count_max", lambda f, v: f > v, "max"),
    ]:
        v = test.get(key)
        if v is not None and isinstance(v, int) and cmp_fn(fails, v):
            errors.append(f"Expected retry_count_{label}={v}, got {fails}.")
    return errors


# ===========================
# Evaluation
# ===========================
def evaluate_one(test, suite, base_dir):
    name = test.get("name", "<unnamed>")
    phase = test.get("phase", "")
    errors = []

    try:
        repo_path = materialize_fixture(base_dir, suite, test["fixture"])
    except Exception as e:
        return TestResult(name=name, phase=phase, passed=False, schema_ok=False, citations_ok=False,
                          expected_schema_valid=test.get("expected_schema_valid"),
                          expected_citations_valid=test.get("expected_citations_valid"),
                          errors=[f"Fixture error: {e}"])

    # Apply tool overrides
    fdef = _resolve_fixture(suite, test["fixture"])
    tbo = fdef.get("tool_behavior_overrides") or {}
    if tbo:
        _apply_overrides(tbo)

    try:
        result = run_workflow(task=test["task"], repo_path=repo_path)
    except Exception as e:
        _restore_overrides()
        return TestResult(name=name, phase=phase, passed=False, schema_ok=False, citations_ok=False,
                          expected_schema_valid=test.get("expected_schema_valid"),
                          expected_citations_valid=test.get("expected_citations_valid"),
                          errors=[f"Agent error: {e}"])
    finally:
        _restore_overrides()

    # Extract results
    if isinstance(result, AgentState):
        output = result.output if isinstance(result.output, dict) else {}
        tool_trace = result.tool_calls if isinstance(result.tool_calls, list) else []
        retrieved_files = result.retrieved_files if isinstance(result.retrieved_files, list) else []
    else:
        output = result if isinstance(result, dict) else {}
        tool_trace = []
        retrieved_files = []

    # Apply adversarial mutations
    if _needs_mutation(name):
        output = _mutate_output(output, test)

    # Tool checks
    if (suite.get("evaluation_contract") or {}).get("tool_trace_required"):
        if not tool_trace:
            errors.append("Tool trace required but empty.")
    errors.extend([f"Tools: {e}" for e in validate_tools(test, tool_trace)])
    errors.extend([f"Retry: {e}" for e in _check_retries(test, tool_trace)])

    # Schema validation (on potentially mutated output)
    schema_ok, schema_errs = validate_schema(output)
    if isinstance(schema_errs, str):
        schema_errs = [schema_errs]
    elif not schema_errs:
        schema_errs = []

    # Citation validation (uses retrieved_files with line data)
    try:
        citations_ok, citation_errs = validate_citations(
            output=output, retrieved_files=retrieved_files, repo_path=repo_path,
            mode=test.get("citation_validation_mode", "range_only"),
            patterns=(suite.get("content_verification_patterns") or {}).get("patterns") or {},
            rules=test.get("validation_rules") or {},
            content_validation=test.get("content_validation") or {},
        )
    except TypeError:
        citations_ok, citation_errs = True, []

    # Agent's internal validation (can only make stricter)
    if isinstance(result, AgentState):
        if hasattr(result, 'citations_valid') and not result.citations_valid:
            if citations_ok:
                citations_ok = False
                citation_errs = list(citation_errs) + list(getattr(result, 'citation_errors', []))



    # Compare expected vs actual — only report errors for MISMATCHES
    exp_schema = test.get("expected_schema_valid")
    exp_cites = test.get("expected_citations_valid")

    if exp_schema is not None:
        if schema_ok != exp_schema:
            errors.append(f"Expected schema_valid={exp_schema}, got {schema_ok}")
            if not schema_ok:
                errors.extend([f"Schema: {m}" for m in schema_errs])
    else:
        if not schema_ok:
            errors.extend([f"Schema: {m}" for m in schema_errs])

    if exp_cites is not None:
        if citations_ok != exp_cites:
            errors.append(f"Expected citations_valid={exp_cites}, got {citations_ok}")
            if not citations_ok:
                errors.extend([f"Citations: {m}" for m in citation_errs])
    else:
        if not citations_ok:
            errors.extend([f"Citations: {m}" for m in citation_errs])

    # Content expectations
    if isinstance(output, dict):
        for tok in (test.get("expected_summary_contains") or []):
            if str(tok).lower() not in str(output.get("summary", "")).lower():
                errors.append(f"Expected summary to contain '{tok}'.")
        ec = test.get("expected_confidence")
        if ec is not None and output.get("confidence") != ec:
            errors.append(f"Expected confidence='{ec}', got '{output.get('confidence')}'.")
        ehc = test.get("expected_high_risk_areas_count")
        if ehc is not None:
            hra = output.get("high_risk_areas")
            if isinstance(hra, list) and len(hra) != ehc:
                errors.append(f"Expected high_risk_areas_count={ehc}, got {len(hra)}.")

        for e in (test.get("expected_citation_ranges") or []):
            if not isinstance(e, dict):
                continue
            fp = (e.get("file") or e.get("file_path", "")).replace("\\", "/")
            cites = [c for c in (output.get("high_risk_areas") or []) if isinstance(c, dict)]
            got = {(c.get("file_path","").replace("\\","/"), c.get("line_start"), c.get("line_end")) for c in cites
                   if isinstance(c.get("file_path"), str)}
            t = (fp, e.get("line_start"), e.get("line_end"))
            if t not in got:
                errors.append(f"Expected citation range not found: {t}")

        exp_fp = test.get("expected_citation_file_path")
        if exp_fp:
            cites = [c for c in (output.get("high_risk_areas") or []) if isinstance(c, dict)]
            if not any((c.get("file_path","").replace("\\","/") == exp_fp.replace("\\","/")) for c in cites):
                errors.append(f"Expected a citation to file_path='{exp_fp}', but none found.")

    return TestResult(
        name=name, phase=phase, passed=(len(errors) == 0),
        schema_ok=schema_ok, citations_ok=citations_ok,
        expected_schema_valid=exp_schema, expected_citations_valid=exp_cites,
        errors=errors,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", default="eval/test_cases.json")
    parser.add_argument("--phase", default=None)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    suite_path = os.path.join(base_dir, args.tests) if not os.path.isabs(args.tests) else args.tests
    suite = load_json(suite_path)

    tests = filter_tests(suite.get("tests", []), args.phase, args.name)
    if not tests:
        print("No tests matched.")
        return

    results = []
    for t in tests:
        r = evaluate_one(t, suite, base_dir)
        results.append(r)
        print(f"[{'PASS' if r.passed else 'FAIL'}] {r.phase} :: {r.name}")
        if not r.passed:
            for e in r.errors[:12]:
                print(f"  - {e}")

    print(f"\nScore: {sum(1 for r in results if r.passed)}/{len(results)} passed")

if __name__ == "__main__":
    main()