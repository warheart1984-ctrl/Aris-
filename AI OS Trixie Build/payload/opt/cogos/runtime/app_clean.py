"""
app.py — UL Dev Playground FastAPI Backend
===========================================
Thin HTTP layer only. All logic lives in the aris.* package.

Pipeline per request:
    1. Tokenize + Parse (for AST preview)
    2. forge_eval.evaluate(source)   ← admission gate, runs BEFORE compile
    3. If blocked → return governance rejection; no VM execution
    4. Compile to bytecode
    5. VM.run_code with Tracer observer
    6. Return tokens + AST + bytecode + eval + vm_trace + output
"""

from __future__ import annotations

import io
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from aris.ul        import tokenize, Parser, Compiler, VM, Tracer
from aris.forge     import ForgeEvaluator, DocChannel


# ── Policy ────────────────────────────────────────────────────────────────────

_DEFAULT_POLICY = """\
DSL v1
NAMESPACE: ul_playground.sandbox

LAW no_import_os:
    forbid_import os

LAW no_import_sys:
    forbid_import sys
"""

_channel   = DocChannel.from_text(_DEFAULT_POLICY)
_evaluator = ForgeEvaluator(_channel)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="UL Dev Playground")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    source: str


# ── Serialisers ───────────────────────────────────────────────────────────────

def ast_to_json(node):
    if not isinstance(node, tuple): return node
    kind = node[0]
    if kind == "program":   return {"kind": "program",  "body":    [ast_to_json(s) for s in node[1]]}
    if kind == "set":       return {"kind": "set",      "name":    node[1], "value": ast_to_json(node[2])}
    if kind == "print":     return {"kind": "print",    "expr":    ast_to_json(node[1])}
    if kind == "function":  return {"kind": "function", "name":    node[1], "params": node[2],
                                    "body": [ast_to_json(s) for s in node[3]]}
    if kind == "return":    return {"kind": "return",   "expr":    ast_to_json(node[1])}
    if kind == "if":        return {"kind": "if",       "cond":    ast_to_json(node[1]),
                                    "body": [ast_to_json(s) for s in node[2]],
                                    "else": [ast_to_json(s) for s in node[3]]}
    if kind == "while":     return {"kind": "while",    "cond":    ast_to_json(node[1]),
                                    "body": [ast_to_json(s) for s in node[2]]}
    if kind == "repeat":    return {"kind": "repeat",   "times":   ast_to_json(node[1]),
                                    "body": [ast_to_json(s) for s in node[2]]}
    if kind in ("number", "string", "bool", "null"):
                            return {"kind": kind,       "value":   node[1]}
    if kind == "name":      return {"kind": "name",     "value":   node[1]}
    if kind == "binop":     return {"kind": "binop",    "op":      node[1],
                                    "left": ast_to_json(node[2]), "right": ast_to_json(node[3])}
    if kind == "call":      return {"kind": "call",     "name":    node[1],
                                    "args": [ast_to_json(a) for a in node[2]]}
    if kind == "list":      return {"kind": "list",     "items":   [ast_to_json(i) for i in node[1]]}
    if kind == "dict":      return {"kind": "dict",
                                    "items": [{"key": ast_to_json(k), "val": ast_to_json(v)}
                                              for k, v in node[1]]}
    if kind == "expr":      return {"kind": "expr",     "expr":    ast_to_json(node[1])}
    if kind == "unary":     return {"kind": "unary",    "op":      node[1],
                                    "operand": ast_to_json(node[2])}
    return {"kind": kind, "raw": str(node)}


def bytecode_to_json(code, consts, names):
    from aris.ul import (LOAD_CONST, LOAD_NAME, STORE_NAME, BINARY_OP,
                          CALL, MAKE_FUNCTION, JUMP_IF_FALSE, JUMP,
                          BUILD_LIST, BUILD_DICT)
    result = []
    for i, (op, arg) in enumerate(code):
        entry = {"i": i, "op": op, "arg": None, "note": ""}
        if op == LOAD_CONST and arg is not None:
            val = consts[arg]
            entry["arg"]  = arg
            entry["note"] = "<function>" if isinstance(val, tuple) else repr(val)
        elif op in (LOAD_NAME, STORE_NAME) and arg is not None:
            entry["arg"]  = arg
            entry["note"] = names[arg]
        elif op == BINARY_OP:
            entry["arg"]  = arg; entry["note"] = arg
        elif op == CALL:
            fname, argc   = arg
            entry["arg"]  = f"{fname}/{argc}"
            entry["note"] = f"call {fname} with {argc} args"
        elif op == MAKE_FUNCTION:
            idx, fname    = arg
            entry["arg"]  = fname
            entry["note"] = f"define {fname}"
        elif op in (JUMP_IF_FALSE, JUMP) and arg is not None:
            entry["arg"]  = arg; entry["note"] = f"→ {arg}"
        elif op in (BUILD_LIST, BUILD_DICT):
            entry["arg"]  = arg; entry["note"] = f"{arg} items"
        result.append(entry)
    return result


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.post("/api/run")
def run_ul(req: RunRequest):
    try:
        source = req.source

        # 1. Tokenize + Parse
        tokens   = tokenize(source)
        tok_list = [{"type": t.type, "value": t.value}
                    for t in tokens if t.type != "EOF"]
        ast_node = Parser(tokens).parse()
        ast_json = ast_to_json(ast_node)

        # 2. Governance gate — BEFORE compile or execute
        eval_result = _evaluator.evaluate(source)
        eval_json   = eval_result.to_dict()

        if not eval_result.allowed:
            return {"ok": True, "governed": True, "allowed": False,
                    "tokens": tok_list, "ast": ast_json,
                    "bytecode": [], "eval": eval_json,
                    "vm_trace": [], "output": []}

        # 3. Compile
        comp     = Compiler(); comp.compile(ast_node)
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

    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/", response_class=HTMLResponse)
def index():
    try:
        with open("index.html") as f: return f.read()
    except FileNotFoundError:
        return "<h1>UL Dev Playground</h1><p>index.html not found.</p>"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
