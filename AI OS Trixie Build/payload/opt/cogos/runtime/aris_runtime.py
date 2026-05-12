"""
aris_runtime.py — ARIS Orchestrator
=====================================
Thin entry point that wires the four layers together.
This file owns no business logic — it only imports, configures, and connects.

Request pipeline:
    source → ForgeEvaluator (gate) → UL compile → VM.run_code → result

Smoke-test all four layers:
    python aris_runtime.py --smoke

Serve the FastAPI playground:
    python aris_runtime.py --serve
"""

from __future__ import annotations

import io
import sys

# ── Import layers (the only place where everything is assembled) ──────────────

from aris.voss      import voss_run, voss_verify, VOSS_GOLDEN_PATH
from aris.ul        import tokenize, Parser, Compiler, VM, Tracer, ul_run_traced
from aris.forge     import ForgeEvaluator, DocChannel, GovernanceError
from aris.substrate import SubstrateRuntime


# ── Default sandbox policy ─────────────────────────────────────────────────────

DEFAULT_POLICY = """\
DSL v1
NAMESPACE: ul_playground.sandbox

LAW no_import_os:
    forbid_import os

LAW no_import_sys:
    forbid_import sys
"""

_channel   = DocChannel.from_text(DEFAULT_POLICY)
_evaluator = ForgeEvaluator(_channel)


# ── Core pipeline function ────────────────────────────────────────────────────

def run_governed(source: str) -> dict:
    """
    Execute UL source through the full governed pipeline.

    Returns a dict with keys:
        allowed, tokens, ast, bytecode, eval, vm_trace, output, error
    """
    from aris.ul import tokenize as _tok, Parser as _Parser
    from app_serialisers import ast_to_json, bytecode_to_json   # see below

    # 1. Parse (needed for AST even if gate blocks)
    try:
        tokens   = _tok(source)
        tok_list = [{"type": t.type, "value": t.value}
                    for t in tokens if t.type != "EOF"]
        ast_node = _Parser(tokens).parse()
        ast_json = ast_to_json(ast_node)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # 2. Gate
    eval_result = _evaluator.evaluate(source)
    eval_json   = eval_result.to_dict()

    if not eval_result.allowed:
        return {"ok": True, "governed": True, "allowed": False,
                "tokens": tok_list, "ast": ast_json,
                "bytecode": [], "eval": eval_json,
                "vm_trace": [], "output": []}

    # 3. Compile
    comp = Compiler(); comp.compile(ast_node)
    bytecode = bytecode_to_json(comp.code, comp.consts, comp.names)

    # 4. Run with Tracer
    vm = VM(); tracer = Tracer(vm); vm.add_observer(tracer)
    captured = io.StringIO(); sys.stdout = captured
    try:
        vm.run_code(comp.code, comp.consts, comp.names, globals_={})
    finally:
        sys.stdout = sys.__stdout__

    return {"ok": True, "governed": True, "allowed": True,
            "tokens": tok_list, "ast": ast_json,
            "bytecode": bytecode, "eval": eval_json,
            "vm_trace": tracer.trace_log, "output": tracer.output_lines}


# ── Smoke tests ───────────────────────────────────────────────────────────────

def smoke_test():
    print("=" * 60)
    print("ARIS Runtime — Smoke Tests")
    print("=" * 60)

    # §1 Voss Binary
    print("\n[1] Voss Binary — golden path")
    fs, trace = voss_run(VOSS_GOLDEN_PATH, verbose=False)
    print(f"  Status={fs.status.value}  Cycle={fs.cycle}  "
          f"Delta={dict(fs.delta)}  Fate={{k: hex(v) for k,v in fs.fate.items()}}")
    verdict = voss_verify(trace)
    print(f"  Verifier: {verdict}")

    # §2 UL Language
    print("\n[2] UL Language — run_traced")
    ul_src = """\
set x to 5
set y to 3
function add a b
    return a + b
end
set z to add(x, y)
print z
"""
    _, ul_tracer = ul_run_traced(ul_src)
    print(f"  Output: {ul_tracer.output_lines}  "
          f"Trace entries: {len(ul_tracer.trace_log)}")

    # §3 Forge Evaluator
    print("\n[3] Forge Evaluator — admission gate")
    r_safe   = _evaluator.evaluate("set x to 1\nprint x")
    r_unsafe = _evaluator.evaluate("import os\nprint os")
    print(f"  safe   → allowed={r_safe.allowed}")
    print(f"  unsafe → allowed={r_unsafe.allowed}  "
          f"violation={r_unsafe.violations[0].rule if r_unsafe.violations else 'none'}")

    # §4 Substrate
    print("\n[4] UL Substrate — governed dispatch")
    runtime = SubstrateRuntime()
    runtime.dispatcher.set_default(
        lambda actor, verb, times, ctx: f"{actor}.{verb}×{times}")
    r_ok  = runtime.execute("cat jumps x3\nagent pings")
    r_bad = runtime.execute("repo deletes x1")
    print(f"  allowed   → {r_ok.allowed}  outputs={r_ok.outputs}")
    print(f"  dangerous → allowed={r_bad.allowed}  "
          f"violation={r_bad.gate.violations[0].rule if r_bad.gate.violations else 'none'}")

    print("\nAll smoke tests complete.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description="ARIS Runtime")
    cli.add_argument("--serve", action="store_true",
                     help="Start FastAPI dev server on :8000")
    cli.add_argument("--smoke", action="store_true",
                     help="Run smoke tests for all four layers (default)")
    args = cli.parse_args()

    if args.serve:
        try:
            import uvicorn
            from app import app   # FastAPI app defined in app.py
            uvicorn.run(app, host="127.0.0.1", port=8000)
        except ImportError as e:
            print(f"Missing dependency: {e}")
            print("Run: pip install fastapi uvicorn")
            sys.exit(1)
    else:
        smoke_test()
