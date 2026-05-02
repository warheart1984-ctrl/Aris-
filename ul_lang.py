"""
ul_lang.py — Universal Language (Programming Language Edition)

A minimal, governed, general-purpose programming language.
Tokenizer → Parser → AST → Compiler → VM (with observer hooks).

Features:
    - Variables, arithmetic, comparisons, booleans, null
    - Functions with parameters and return values
    - if / else / while / repeat
    - Lists and dicts
    - Observer pattern for tracing, governance, and instrumentation

This is the LANGUAGE layer. It handles general computation.
For AAIS governed command execution, see ul_substrate.py.

Key design rules:
    - All opcode semantics live in VM._exec_opcode — nowhere else
    - Governance and tracing attach via add_observer() — not subclassing
    - The Compiler is stateless per-program — instantiate a new one each run
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import re


# ─────────────────────────────────────────────────────────────────────────────
# Universal Payload Envelope
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ULPayload:
    """Canonical envelope for data moving through the UL runtime."""
    source:   str
    kind:     str
    section:  str
    data:     Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

TOKEN_SPEC = [
    ('NUMBER',   r'\d+(\.\d+)?'),
    ('STRING',   r'"([^"\\]|\\.)*"'),
    ('NAME',     r'[A-Za-z_][A-Za-z0-9_]*'),
    ('OP',       r'==|!=|<=|>=|[+\-*/%<>=\[\]\{\}\(\),.]'),
    ('NEWLINE',  r'\n'),
    ('SKIP',     r'[ \t]+'),
    ('MISMATCH', r'.'),
]
_TOK_RE = re.compile('|'.join('(?P<%s>%s)' % pair for pair in TOKEN_SPEC))


@dataclass
class Token:
    type:  str
    value: str


def tokenize(code: str) -> List[Token]:
    tokens = []
    for mo in _TOK_RE.finditer(code):
        kind = mo.lastgroup
        val  = mo.group()
        if kind == 'NUMBER':
            tokens.append(Token('NUMBER', val))
        elif kind == 'STRING':
            tokens.append(Token('STRING', val[1:-1].encode('utf-8').decode('unicode_escape')))
        elif kind == 'NAME':
            tokens.append(Token('NAME', val))
        elif kind == 'OP':
            tokens.append(Token('OP', val))
        elif kind == 'NEWLINE':
            tokens.append(Token('NEWLINE', val))
        elif kind == 'SKIP':
            continue
        else:
            raise SyntaxError(f'Unexpected character: {val!r}')
    tokens.append(Token('EOF', ''))
    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Parser — recursive descent
# ─────────────────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos    = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, ttype: str, val: Optional[str] = None) -> Token:
        t = self.peek()
        if t.type != ttype or (val is not None and t.value != val):
            raise SyntaxError(f'Expected {ttype!r} {val!r}, got {t.type!r} {t.value!r}')
        return self.advance()

    def skip_newlines(self):
        while self.peek().type == 'NEWLINE':
            self.advance()

    # ── Statements ────────────────────────────────────────────────────────────

    def parse(self):
        stmts = []
        while self.peek().type != 'EOF':
            if self.peek().type == 'NEWLINE':
                self.advance(); continue
            stmts.append(self.parse_stmt())
        return ('program', stmts)

    def parse_stmt(self):
        self.skip_newlines()
        t = self.peek()

        if t.type == 'NAME' and t.value == 'set':
            self.advance()
            name = self.expect('NAME').value
            self.expect('NAME', 'to')
            return ('set', name, self.parse_expr())

        if t.type == 'NAME' and t.value == 'print':
            self.advance()
            return ('print', self.parse_expr())

        if t.type == 'NAME' and t.value == 'function':
            self.advance()
            fname  = self.expect('NAME').value
            params = []
            while self.peek().type == 'NAME' and self.peek().value not in (
                'set', 'print', 'if', 'while', 'repeat', 'return', 'end', 'else'
            ):
                params.append(self.advance().value)
            body = self._parse_block('end')
            return ('function', fname, params, body)

        if t.type == 'NAME' and t.value == 'return':
            self.advance()
            return ('return', self.parse_expr())

        if t.type == 'NAME' and t.value == 'if':
            self.advance()
            cond = self.parse_expr()
            body = []
            else_body = []
            self.skip_newlines()
            while not (self.peek().type == 'NAME' and self.peek().value in ('else', 'end')):
                body.append(self.parse_stmt())
                self.skip_newlines()
            if self.peek().value == 'else':
                self.advance()
                else_body = self._parse_block('end')
            else:
                self.expect('NAME', 'end')
            return ('if', cond, body, else_body)

        if t.type == 'NAME' and t.value == 'while':
            self.advance()
            cond = self.parse_expr()
            body = self._parse_block('end')
            return ('while', cond, body)

        if t.type == 'NAME' and t.value == 'repeat':
            self.advance()
            times = self.parse_expr()
            self.expect('NAME', 'times')
            body = self._parse_block('end')
            return ('repeat', times, body)

        # expression statement
        return ('expr', self.parse_expr())

    def _parse_block(self, terminator: str) -> List:
        body = []
        self.skip_newlines()
        while not (self.peek().type == 'NAME' and self.peek().value == terminator):
            body.append(self.parse_stmt())
            self.skip_newlines()
        self.expect('NAME', terminator)
        return body

    # ── Expressions (precedence climbing) ────────────────────────────────────

    def parse_expr(self):     return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while self.peek().type == 'NAME' and self.peek().value == 'or':
            self.advance(); node = ('binop', 'or', node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_cmp()
        while self.peek().type == 'NAME' and self.peek().value == 'and':
            self.advance(); node = ('binop', 'and', node, self.parse_cmp())
        return node

    def parse_cmp(self):
        node = self.parse_add()
        while self.peek().type == 'OP' and self.peek().value in ('==', '!=', '<', '>', '<=', '>='):
            op = self.advance().value; node = ('binop', op, node, self.parse_add())
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.peek().type == 'OP' and self.peek().value in ('+', '-'):
            op = self.advance().value; node = ('binop', op, node, self.parse_mul())
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.peek().type == 'OP' and self.peek().value in ('*', '/', '%'):
            op = self.advance().value; node = ('binop', op, node, self.parse_unary())
        return node

    def parse_unary(self):
        if self.peek().type == 'OP' and self.peek().value == '-':
            self.advance()
            return ('unary', '-', self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.peek()

        if t.type == 'NUMBER':
            self.advance()
            return ('number', float(t.value) if '.' in t.value else int(t.value))

        if t.type == 'STRING':
            self.advance()
            return ('string', t.value)

        if t.type == 'NAME':
            name = self.advance().value
            if name == 'true':  return ('bool', True)
            if name == 'false': return ('bool', False)
            if name == 'null':  return ('null', None)
            if self.peek().type == 'OP' and self.peek().value == '(':
                self.advance()
                args = []
                if not (self.peek().type == 'OP' and self.peek().value == ')'):
                    args.append(self.parse_expr())
                    while self.peek().type == 'OP' and self.peek().value == ',':
                        self.advance(); args.append(self.parse_expr())
                self.expect('OP', ')')
                return ('call', name, args)
            return ('name', name)

        if t.type == 'OP' and t.value == '[':
            self.advance()
            items = []
            if not (self.peek().type == 'OP' and self.peek().value == ']'):
                items.append(self.parse_expr())
                while self.peek().type == 'OP' and self.peek().value == ',':
                    self.advance(); items.append(self.parse_expr())
            self.expect('OP', ']')
            return ('list', items)

        if t.type == 'OP' and t.value == '{':
            self.advance()
            items = []
            if not (self.peek().type == 'OP' and self.peek().value == '}'):
                while True:
                    k = self.parse_expr()
                    self.expect('OP', ':')
                    v = self.parse_expr()
                    items.append((k, v))
                    if not (self.peek().type == 'OP' and self.peek().value == ','):
                        break
                    self.advance()
            self.expect('OP', '}')
            return ('dict', items)

        if t.type == 'OP' and t.value == '(':
            self.advance()
            node = self.parse_expr()
            self.expect('OP', ')')
            return node

        raise SyntaxError(f'Unexpected token in expression: {t.type!r} {t.value!r}')


# ─────────────────────────────────────────────────────────────────────────────
# Bytecode opcodes
# ─────────────────────────────────────────────────────────────────────────────

LOAD_CONST    = 'LOAD_CONST'
LOAD_NAME     = 'LOAD_NAME'
STORE_NAME    = 'STORE_NAME'
BINARY_OP     = 'BINARY_OP'
POP_TOP       = 'POP_TOP'
JUMP_IF_FALSE = 'JUMP_IF_FALSE'
JUMP          = 'JUMP'
CALL          = 'CALL'
RETURN        = 'RETURN'
MAKE_FUNCTION = 'MAKE_FUNCTION'
PRINT         = 'PRINT'
BUILD_LIST    = 'BUILD_LIST'
BUILD_DICT    = 'BUILD_DICT'


# ─────────────────────────────────────────────────────────────────────────────
# Compiler — AST → bytecode
# ─────────────────────────────────────────────────────────────────────────────

class Compiler:
    def __init__(self):
        self.consts: List[Any]           = []
        self.names:  List[str]           = []
        self.code:   List[tuple]         = []

    def _const(self, v) -> int:
        if v not in self.consts:
            self.consts.append(v)
        return self.consts.index(v)

    def _name(self, n: str) -> int:
        if n not in self.names:
            self.names.append(n)
        return self.names.index(n)

    def _emit(self, op: str, arg=None):
        self.code.append((op, arg))

    def compile(self, node) -> tuple:
        self._compile_node(node)
        return self.code, self.consts, self.names

    def _compile_node(self, node):
        kind = node[0]

        if kind == 'program':
            for s in node[1]: self._compile_node(s)

        elif kind == 'set':
            self._compile_node(node[2])
            self._emit(STORE_NAME, self._name(node[1]))

        elif kind == 'print':
            self._compile_node(node[1])
            self._emit(PRINT)

        elif kind == 'number':
            self._emit(LOAD_CONST, self._const(node[1]))

        elif kind == 'string':
            self._emit(LOAD_CONST, self._const(node[1]))

        elif kind == 'bool':
            self._emit(LOAD_CONST, self._const(node[1]))

        elif kind == 'null':
            self._emit(LOAD_CONST, self._const(None))

        elif kind == 'name':
            self._emit(LOAD_NAME, self._name(node[1]))

        elif kind == 'binop':
            _, op, left, right = node
            self._compile_node(left)
            self._compile_node(right)
            self._emit(BINARY_OP, op)

        elif kind == 'unary':
            _, op, operand = node
            self._emit(LOAD_CONST, self._const(0))
            self._compile_node(operand)
            self._emit(BINARY_OP, '-')

        elif kind == 'call':
            _, fname, args = node
            for a in args: self._compile_node(a)
            self._emit(CALL, (fname, len(args)))

        elif kind == 'function':
            _, fname, params, body = node
            sub = Compiler()
            for s in body: sub._compile_node(s)
            sub._emit(RETURN)
            func_obj = ('code', sub.code, sub.consts, sub.names, params)
            self._emit(MAKE_FUNCTION, (self._const(func_obj), fname))

        elif kind == 'return':
            self._compile_node(node[1])
            self._emit(RETURN)

        elif kind == 'if':
            _, cond, body, else_body = node
            self._compile_node(cond)
            patch_jf = len(self.code); self._emit(JUMP_IF_FALSE, None)
            for s in body: self._compile_node(s)
            if else_body:
                patch_j = len(self.code); self._emit(JUMP, None)
                self.code[patch_jf] = (JUMP_IF_FALSE, len(self.code))
                for s in else_body: self._compile_node(s)
                self.code[patch_j] = (JUMP, len(self.code))
            else:
                self.code[patch_jf] = (JUMP_IF_FALSE, len(self.code))

        elif kind == 'while':
            _, cond, body = node
            start = len(self.code)
            self._compile_node(cond)
            patch_jf = len(self.code); self._emit(JUMP_IF_FALSE, None)
            for s in body: self._compile_node(s)
            self._emit(JUMP, start)
            self.code[patch_jf] = (JUMP_IF_FALSE, len(self.code))

        elif kind == 'repeat':
            # repeat N times → counter counts down from N to 1
            _, times, body = node
            counter = '__repeat__'
            self._compile_node(times)
            self._emit(STORE_NAME, self._name(counter))
            start = len(self.code)
            self._emit(LOAD_NAME,  self._name(counter))
            self._emit(LOAD_CONST, self._const(0))
            self._emit(BINARY_OP,  '>')           # counter > 0 → keep looping
            patch_jf = len(self.code); self._emit(JUMP_IF_FALSE, None)
            for s in body: self._compile_node(s)
            self._emit(LOAD_NAME,  self._name(counter))
            self._emit(LOAD_CONST, self._const(1))
            self._emit(BINARY_OP,  '-')
            self._emit(STORE_NAME, self._name(counter))
            self._emit(JUMP, start)
            self.code[patch_jf] = (JUMP_IF_FALSE, len(self.code))

        elif kind == 'list':
            for item in node[1]: self._compile_node(item)
            self._emit(BUILD_LIST, len(node[1]))

        elif kind == 'dict':
            for k, v in node[1]:
                self._compile_node(k)
                self._compile_node(v)
            self._emit(BUILD_DICT, len(node[1]))

        elif kind == 'expr':
            self._compile_node(node[1])
            self._emit(POP_TOP)

        else:
            raise NotImplementedError(f'Compiler: unknown node kind {kind!r}')


# ─────────────────────────────────────────────────────────────────────────────
# VM — stack machine with observer hooks
# ─────────────────────────────────────────────────────────────────────────────

class Frame:
    def __init__(self, code, consts, names, globals_):
        self.code    = code
        self.consts  = consts
        self.names   = names
        self.stack:  List[Any]       = []
        self.locals: Dict[str, Any]  = {}
        self.globals = globals_
        self.ip      = 0
        self._return_val = None


class VMObserver:
    """
    Attach to a VM via vm.add_observer(obs).
    Override handle_event to react to execution events.
    Events: 'before_opcode', 'after_opcode', 'print_output'
    """
    def handle_event(self, event_type: str, **payload):
        pass


class VM:
    """
    Stack-based VM. All opcode semantics live in _exec_opcode — nowhere else.
    Governance, tracing, and instrumentation attach via add_observer().
    """

    def __init__(self):
        self.frames:    List[Frame]       = []
        self._observers: List[VMObserver] = []
        self.builtins: Dict[str, Any]     = {
            'print':  lambda *a: print(*a),
            'len':    lambda x: len(x),
            'append': lambda lst, v: lst.append(v) or None,
            'pop':    lambda lst: lst.pop(),
            'str':    lambda x: str(x),
            'int':    lambda x: int(x),
            'float':  lambda x: float(x),
        }

    def add_observer(self, observer: VMObserver):
        self._observers.append(observer)

    def _emit(self, event_type: str, **payload):
        for obs in self._observers:
            obs.handle_event(event_type, **payload)

    def run_code(self, code, consts, names, globals_=None):
        globals_ = globals_ or {}
        frame = Frame(code, consts, names, globals_)
        self.frames.append(frame)
        result = self._run_frame(frame)
        # promote top-level functions to globals so they're callable cross-scope
        for k, v in frame.locals.items():
            if isinstance(v, dict) and v.get('type') == 'function':
                globals_[k] = v
        return result

    def _run_frame(self, f: Frame):
        while f.ip < len(f.code):
            op, arg     = f.code[f.ip]
            ip_before   = f.ip
            f.ip       += 1

            self._emit('before_opcode',
                       ip=ip_before, op=op, arg=arg,
                       stack=list(f.stack), locals=dict(f.locals), frame=f)

            signal = self._exec_opcode(f, op, arg)

            self._emit('after_opcode',
                       ip=ip_before, op=op, arg=arg,
                       stack=list(f.stack), locals=dict(f.locals), frame=f)

            if signal == '__RETURN__':
                return f._return_val

        self.frames.pop() if self.frames else None
        return None

    def _exec_opcode(self, f: Frame, op: str, arg) -> Optional[str]:
        """
        Execute one opcode. Returns '__RETURN__' when the frame should end.
        This is the only place opcode behaviour is defined.
        """
        if op == LOAD_CONST:
            f.stack.append(f.consts[arg])

        elif op == LOAD_NAME:
            name = f.names[arg]
            if   name in f.locals:       f.stack.append(f.locals[name])
            elif name in f.globals:      f.stack.append(f.globals[name])
            elif name in self.builtins:  f.stack.append(self.builtins[name])
            else: raise NameError(f'Undefined name: {name!r}')

        elif op == STORE_NAME:
            f.locals[f.names[arg]] = f.stack.pop()

        elif op == BINARY_OP:
            b = f.stack.pop(); a = f.stack.pop()
            if   arg == '+':   f.stack.append(a + b)
            elif arg == '-':   f.stack.append(a - b)
            elif arg == '*':   f.stack.append(a * b)
            elif arg == '/':   f.stack.append(a / b)
            elif arg == '%':   f.stack.append(a % b)
            elif arg == '==':  f.stack.append(a == b)
            elif arg == '!=':  f.stack.append(a != b)
            elif arg == '<':   f.stack.append(a < b)
            elif arg == '>':   f.stack.append(a > b)
            elif arg == '<=':  f.stack.append(a <= b)
            elif arg == '>=':  f.stack.append(a >= b)
            elif arg == 'and': f.stack.append(a and b)
            elif arg == 'or':  f.stack.append(a or b)
            else: raise RuntimeError(f'Unknown binop: {arg!r}')

        elif op == PRINT:
            val = f.stack.pop()
            self._emit('print_output', value=val)
            self.builtins['print'](val)

        elif op == POP_TOP:
            f.stack.pop()

        elif op == BUILD_LIST:
            items = [f.stack.pop() for _ in range(arg)][::-1]
            f.stack.append(items)

        elif op == BUILD_DICT:
            d = {}
            for _ in range(arg):
                v = f.stack.pop(); k = f.stack.pop()
                d[k] = v
            f.stack.append(d)

        elif op == CALL:
            fname, argc = arg
            args = [f.stack.pop() for _ in range(argc)][::-1]
            if fname in self.builtins:
                f.stack.append(self.builtins[fname](*args))
                return None
            func = (f.locals.get(fname) or f.globals.get(fname))
            if func is None or not isinstance(func, dict) or func.get('type') != 'function':
                raise NameError(f'Function not found: {fname!r}')
            new_f = Frame(func['code'], func['consts'], func['names'], f.globals)
            for i, p in enumerate(func['params']):
                new_f.locals[p] = args[i] if i < len(args) else None
            self.frames.append(new_f)
            f.stack.append(self._run_frame(new_f))

        elif op == MAKE_FUNCTION:
            idx, fname = arg
            _, code_obj, consts, names, params = f.consts[idx]
            func_def = {'type': 'function', 'code': code_obj,
                        'consts': consts, 'names': names, 'params': params}
            f.locals[fname]  = func_def
            f.globals[fname] = func_def

        elif op == RETURN:
            f._return_val = f.stack.pop() if f.stack else None
            if self.frames and self.frames[-1] is f:
                self.frames.pop()
            return '__RETURN__'

        elif op == JUMP_IF_FALSE:
            if not f.stack.pop():
                f.ip = arg

        elif op == JUMP:
            f.ip = arg

        else:
            raise RuntimeError(f'Unknown opcode: {op!r}')

        return None


# ─────────────────────────────────────────────────────────────────────────────
# Tracer — standard observer for dev/debug
# ─────────────────────────────────────────────────────────────────────────────

class Tracer(VMObserver):
    """
    Collects a structured execution trace and captures print output.
    Attach via vm.add_observer(Tracer(vm)).
    """

    def __init__(self, vm: VM):
        self._vm          = vm
        self.trace_log:   List[dict] = []
        self.output_lines: List[str] = []

    def handle_event(self, event_type: str, **payload):
        if event_type == 'before_opcode':
            self.trace_log.append({
                'ip':     payload['ip'],
                'op':     payload['op'],
                'arg':    str(payload['arg']),
                'stack':  [repr(v) for v in payload['stack']],
                'locals': {k: repr(v) for k, v in payload['locals'].items()
                           if not k.startswith('__')},
            })
        elif event_type == 'print_output':
            self.output_lines.append(str(payload['value']))


# ─────────────────────────────────────────────────────────────────────────────
# Convenience API
# ─────────────────────────────────────────────────────────────────────────────

def run(source: str, globals_: Optional[Dict] = None) -> Any:
    """Parse, compile, and run UL source. Returns the last expression value."""
    tokens  = tokenize(source)
    ast     = Parser(tokens).parse()
    code, consts, names = Compiler().compile(ast)
    return VM().run_code(code, consts, names, globals_=globals_ or {})


def run_traced(source: str) -> tuple[Any, Tracer]:
    """Run UL source with a Tracer attached. Returns (result, tracer)."""
    tokens  = tokenize(source)
    ast     = Parser(tokens).parse()
    code, consts, names = Compiler().compile(ast)
    vm      = VM()
    tracer  = Tracer(vm)
    vm.add_observer(tracer)
    result  = vm.run_code(code, consts, names, globals_={})
    return result, tracer


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    src = '''\
set x to 5
set y to 3

function add a b
    return a + b
end

set z to add(x, y)
print z

repeat 3 times
    print "loop"
end

set i to 0
while i < 3
    print i
    set i to i + 1
end

if z > 7
    print "big"
else
    print "small"
end
'''
    print("=== UL Language self-test ===")
    result, tracer = run_traced(src)
    print(f"\nOutput lines : {tracer.output_lines}")
    print(f"Trace entries: {len(tracer.trace_log)}")
