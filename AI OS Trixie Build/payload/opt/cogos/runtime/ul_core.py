# ul_core.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional, Union
import re
import sys

# -------------------------
# ULPayload (universal envelope)
# -------------------------
@dataclass
class ULPayload:
    source: str
    kind: str
    section: str
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

# -------------------------
# Tokenizer
# -------------------------
TOKEN_SPEC = [
    ('NUMBER',   r'\d+(\.\d+)?'),
    ('STRING',   r'"([^"\\]|\\.)*"'),
    ('NAME',     r'[A-Za-z_][A-Za-z0-9_]*'),
    ('OP',       r'==|!=|<=|>=|[+\-*/%<>=\[\]\{\}\(\),.]'),
    ('NEWLINE',  r'\n'),
    ('SKIP',     r'[ \t]+'),
    ('MISMATCH', r'.'),
]
TOK_RE = re.compile('|'.join('(?P<%s>%s)' % pair for pair in TOKEN_SPEC))

@dataclass
class Token:
    type: str
    value: str

def tokenize(code: str) -> List[Token]:
    tokens = []
    for mo in TOK_RE.finditer(code):
        kind = mo.lastgroup
        val = mo.group()
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
            raise SyntaxError(f'Unexpected token: {val}')
    tokens.append(Token('EOF', ''))
    return tokens

# -------------------------
# Parser (recursive descent) - expressions + statements
# -------------------------
class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def next(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, ttype: str, val: Optional[str] = None) -> Token:
        t = self.peek()
        if t.type != ttype or (val is not None and t.value != val):
            raise SyntaxError(f'Expected {ttype} {val}, got {t.type} {t.value}')
        return self.next()

    def parse(self):
        stmts = []
        while self.peek().type != 'EOF':
            if self.peek().type == 'NEWLINE':
                self.next(); continue
            stmts.append(self.parse_stmt())
        return ('program', stmts)

    def skip_newlines(self):
        while self.peek().type == 'NEWLINE':
            self.next()

    def parse_stmt(self):
        self.skip_newlines()
        t = self.peek()
        if t.type == 'NAME' and t.value == 'set':
            self.next()
            name = self.expect('NAME').value
            self.expect('NAME', 'to')
            expr = self.parse_expr()
            return ('set', name, expr)
        if t.type == 'NAME' and t.value == 'print':
            self.next()
            expr = self.parse_expr()
            return ('print', expr)
        if t.type == 'NAME' and t.value == 'function':
            self.next()
            fname = self.expect('NAME').value
            params = []
            while self.peek().type == 'NAME':
                params.append(self.next().value)
            body = []
            self.skip_newlines()
            while not (self.peek().type == 'NAME' and self.peek().value == 'end'):
                body.append(self.parse_stmt())
                self.skip_newlines()
            self.expect('NAME', 'end')
            return ('function', fname, params, body)
        if t.type == 'NAME' and t.value == 'return':
            self.next()
            expr = self.parse_expr()
            return ('return', expr)
        if t.type == 'NAME' and t.value == 'if':
            self.next()
            cond = self.parse_expr()
            body = []
            else_body = []
            self.skip_newlines()
            while not (self.peek().type == 'NAME' and (self.peek().value in ('else', 'end'))):
                body.append(self.parse_stmt())
                self.skip_newlines()
            if self.peek().type == 'NAME' and self.peek().value == 'else':
                self.next()
                self.skip_newlines()
                while not (self.peek().type == 'NAME' and self.peek().value == 'end'):
                    else_body.append(self.parse_stmt())
                    self.skip_newlines()
            self.expect('NAME', 'end')
            return ('if', cond, body, else_body)
        if t.type == 'NAME' and t.value == 'while':
            self.next()
            cond = self.parse_expr()
            body = []
            self.skip_newlines()
            while not (self.peek().type == 'NAME' and self.peek().value == 'end'):
                body.append(self.parse_stmt())
                self.skip_newlines()
            self.expect('NAME', 'end')
            return ('while', cond, body)
        if t.type == 'NAME' and t.value == 'repeat':
            self.next()
            times = self.parse_expr()
            self.expect('NAME', 'times')
            body = []
            self.skip_newlines()
            while not (self.peek().type == 'NAME' and self.peek().value == 'end'):
                body.append(self.parse_stmt())
                self.skip_newlines()
            self.expect('NAME', 'end')
            return ('repeat', times, body)
        # expression statement
        expr = self.parse_expr()
        return ('expr', expr)

    def parse_expr(self):
        return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while self.peek().type == 'NAME' and self.peek().value == 'or':
            self.next()
            right = self.parse_and()
            node = ('or', node, right)
        return node

    def parse_and(self):
        node = self.parse_cmp()
        while self.peek().type == 'NAME' and self.peek().value == 'and':
            self.next()
            right = self.parse_cmp()
            node = ('and', node, right)
        return node

    def parse_cmp(self):
        node = self.parse_add()
        while self.peek().type == 'OP' and self.peek().value in ('==', '!=', '<', '>', '<=', '>='):
            op = self.next().value
            right = self.parse_add()
            node = ('binop', op, node, right)
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.peek().type == 'OP' and self.peek().value in ('+', '-'):
            op = self.next().value
            right = self.parse_mul()
            node = ('binop', op, node, right)
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.peek().type == 'OP' and self.peek().value in ('*', '/', '%'):
            op = self.next().value
            right = self.parse_unary()
            node = ('binop', op, node, right)
        return node

    def parse_unary(self):
        if self.peek().type == 'OP' and self.peek().value == '-':
            self.next()
            node = self.parse_unary()
            return ('unary', '-', node)
        return self.parse_primary()

    def parse_primary(self):
        t = self.peek()
        if t.type == 'NUMBER':
            self.next()
            if '.' in t.value:
                return ('number', float(t.value))
            return ('number', int(t.value))
        if t.type == 'STRING':
            self.next()
            return ('string', t.value)
        if t.type == 'NAME':
            name = self.next().value
            if name == 'true': return ('bool', True)
            if name == 'false': return ('bool', False)
            if name == 'null': return ('null', None)
            if self.peek().type == 'OP' and self.peek().value == '(':
                self.next()
                args = []
                if not (self.peek().type == 'OP' and self.peek().value == ')'):
                    args.append(self.parse_expr())
                    while self.peek().type == 'OP' and self.peek().value == ',':
                        self.next()
                        args.append(self.parse_expr())
                self.expect('OP', ')')
                return ('call', name, args)
            return ('name', name)
        if t.type == 'OP' and t.value == '[':
            self.next()
            items = []
            if not (self.peek().type == 'OP' and self.peek().value == ']'):
                items.append(self.parse_expr())
                while self.peek().type == 'OP' and self.peek().value == ',':
                    self.next()
                    items.append(self.parse_expr())
            self.expect('OP', ']')
            return ('list', items)
        if t.type == 'OP' and t.value == '{':
            self.next()
            items = []
            if not (self.peek().type == 'OP' and self.peek().value == '}'):
                while True:
                    key = self.parse_expr()
                    self.expect('OP', ':')
                    val = self.parse_expr()
                    items.append((key, val))
                    if self.peek().type == 'OP' and self.peek().value == ',':
                        self.next(); continue
                    break
            self.expect('OP', '}')
            return ('dict', items)
        if t.type == 'OP' and t.value == '(':
            self.next()
            node = self.parse_expr()
            self.expect('OP', ')')
            return node
        raise SyntaxError(f'Unexpected token in primary: {t.type} {t.value}')

# -------------------------
# Compiler to bytecode
# -------------------------
LOAD_CONST = 'LOAD_CONST'
LOAD_NAME = 'LOAD_NAME'
STORE_NAME = 'STORE_NAME'
BINARY_OP = 'BINARY_OP'
POP_TOP = 'POP_TOP'
JUMP_IF_FALSE = 'JUMP_IF_FALSE'
JUMP = 'JUMP'
CALL = 'CALL'
RETURN = 'RETURN'
MAKE_FUNCTION = 'MAKE_FUNCTION'
PRINT = 'PRINT'
BUILD_LIST = 'BUILD_LIST'
BUILD_DICT = 'BUILD_DICT'

class Compiler:
    def __init__(self):
        self.consts = []
        self.names = []
        self.code = []

    def add_const(self, v):
        if v in self.consts:
            return self.consts.index(v)
        self.consts.append(v)
        return len(self.consts) - 1

    def add_name(self, n):
        if n in self.names:
            return self.names.index(n)
        self.names.append(n)
        return len(self.names) - 1

    def emit(self, op, arg=None):
        self.code.append((op, arg))

    def compile(self, node):
        kind = node[0]
        if kind == 'program':
            for s in node[1]:
                self.compile(s)
            return self.code, self.consts, self.names
        if kind == 'set':
            _, name, expr = node
            self.compile(expr)
            self.emit(STORE_NAME, self.add_name(name))
            return
        if kind == 'print':
            _, expr = node
            self.compile(expr)
            self.emit(PRINT, None)
            return
        if kind == 'number':
            idx = self.add_const(node[1])
            self.emit(LOAD_CONST, idx); return
        if kind == 'string':
            idx = self.add_const(node[1])
            self.emit(LOAD_CONST, idx); return
        if kind == 'bool':
            idx = self.add_const(node[1])
            self.emit(LOAD_CONST, idx); return
        if kind == 'null':
            idx = self.add_const(None)
            self.emit(LOAD_CONST, idx); return
        if kind == 'name':
            idx = self.add_name(node[1])
            self.emit(LOAD_NAME, idx); return
        if kind == 'binop':
            _, op, left, right = node
            self.compile(left); self.compile(right)
            self.emit(BINARY_OP, op); return
        if kind == 'call':
            _, fname, args = node
            for a in args: self.compile(a)
            self.emit(CALL, (fname, len(args))); return
        if kind == 'function':
            _, fname, params, body = node
            sub = Compiler()
            for s in body:
                sub.compile(s)
            sub.emit(RETURN, None)
            func_obj = ('code', sub.code, sub.consts, sub.names, params)
            idx = self.add_const(func_obj)
            self.emit(MAKE_FUNCTION, (idx, fname)); return
        if kind == 'return':
            _, expr = node
            self.compile(expr)
            self.emit(RETURN, None); return
        if kind == 'if':
            _, cond, body, else_body = node
            self.compile(cond)
            jfalse_pos = len(self.code); self.emit(JUMP_IF_FALSE, None)
            for s in body: self.compile(s)
            if else_body:
                jpos = len(self.code); self.emit(JUMP, None)
                self.code[jfalse_pos] = (JUMP_IF_FALSE, len(self.code))
                for s in else_body: self.compile(s)
                self.code[jpos] = (JUMP, len(self.code))
            else:
                self.code[jfalse_pos] = (JUMP_IF_FALSE, len(self.code))
            return
        if kind == 'while':
            _, cond, body = node
            start = len(self.code)
            self.compile(cond)
            jfalse_pos = len(self.code); self.emit(JUMP_IF_FALSE, None)
            for s in body: self.compile(s)
            self.emit(JUMP, start)
            self.code[jfalse_pos] = (JUMP_IF_FALSE, len(self.code))
            return
        if kind == 'repeat':
            _, times, body = node
            self.compile(times)
            self.emit(STORE_NAME, self.add_name('__repeat_counter'))
            start = len(self.code)
            self.emit(LOAD_NAME, self.add_name('__repeat_counter'))
            self.emit(LOAD_CONST, self.add_const(0))
            self.emit(BINARY_OP, '>')          # counter > 0  →  keep looping
            jfalse_pos = len(self.code); self.emit(JUMP_IF_FALSE, None)
            for s in body: self.compile(s)
            self.emit(LOAD_NAME, self.add_name('__repeat_counter'))
            self.emit(LOAD_CONST, self.add_const(1))
            self.emit(BINARY_OP, '-')
            self.emit(STORE_NAME, self.add_name('__repeat_counter'))
            self.emit(JUMP, start)
            self.code[jfalse_pos] = (JUMP_IF_FALSE, len(self.code))
            return
        if kind == 'list':
            _, items = node
            for it in items: self.compile(it)
            self.emit(BUILD_LIST, len(items)); return
        if kind == 'dict':
            _, items = node
            for k, v in items:
                self.compile(k); self.compile(v)
            self.emit(BUILD_DICT, len(items)); return
        if kind == 'expr':
            self.compile(node[1]); self.emit(POP_TOP, None); return
        raise NotImplementedError(f'Compile not implemented for {kind}')

# -------------------------
# VM
# -------------------------
class Frame:
    def __init__(self, code, consts, names, globals_, ip=0):
        self.code = code
        self.consts = consts
        self.names = names
        self.stack = []
        self.ip = ip
        self.locals = {}
        self.globals = globals_

class VMObserver:
    """Base class for VM observers. Override handle_event to react to opcodes."""
    def handle_event(self, event_type: str, **payload):
        pass


class VM:
    """
    Stack-based VM with observer hooks.

    All opcode semantics live in _exec_opcode — nowhere else.
    Tracing, governance checks, and instrumentation attach via add_observer().
    No subclass should ever re-implement opcode logic.
    """

    def __init__(self):
        self.frames: List[Frame] = []
        self._observers: List[VMObserver] = []
        self.builtins = {
            'print': lambda *a: print(*a),
            'len': lambda x: len(x),
            'append': lambda lst, v: lst.append(v) or None,
            'pop': lambda lst: lst.pop(),
            'str': lambda x: str(x),
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
        result = self.run_frame(frame)
        for k, v in frame.locals.items():
            if isinstance(v, dict) and v.get('type') == 'function':
                globals_[k] = v
        return result

    def run_frame(self, f: Frame):
        while f.ip < len(f.code):
            op, arg = f.code[f.ip]
            ip_before = f.ip
            stack_before = list(f.stack)
            locals_before = dict(f.locals)
            f.ip += 1

            self._emit('before_opcode',
                       ip=ip_before, op=op, arg=arg,
                       stack=stack_before, locals=locals_before, frame=f)

            ret_signal = self._exec_opcode(f, op, arg)

            self._emit('after_opcode',
                       ip=ip_before, op=op, arg=arg,
                       stack=list(f.stack), locals=dict(f.locals), frame=f)

            if ret_signal == '__RETURN__':
                return f._return_val

        self.frames.pop() if self.frames else None
        return None

    # ── Canonical opcode semantics ────────────────────────────────────────────
    # This is the only place opcode behaviour is defined.

    def _exec_opcode(self, f: Frame, op: str, arg) -> Optional[str]:
        """
        Execute one opcode.  Returns '__RETURN__' when the frame should end,
        None otherwise.
        """
        if op == LOAD_CONST:
            f.stack.append(f.consts[arg])

        elif op == LOAD_NAME:
            name = f.names[arg]
            if name in f.locals:       f.stack.append(f.locals[name])
            elif name in f.globals:    f.stack.append(f.globals[name])
            elif name in self.builtins: f.stack.append(self.builtins[name])
            else: raise NameError(name)

        elif op == STORE_NAME:
            f.locals[f.names[arg]] = f.stack.pop()

        elif op == BINARY_OP:
            b = f.stack.pop(); a = f.stack.pop()
            if   arg == '+':  f.stack.append(a + b)
            elif arg == '-':  f.stack.append(a - b)
            elif arg == '*':  f.stack.append(a * b)
            elif arg == '/':  f.stack.append(a / b)
            elif arg == '%':  f.stack.append(a % b)
            elif arg == '==': f.stack.append(a == b)
            elif arg == '!=': f.stack.append(a != b)
            elif arg == '<':  f.stack.append(a < b)
            elif arg == '>':  f.stack.append(a > b)
            elif arg == '<=': f.stack.append(a <= b)
            elif arg == '>=': f.stack.append(a >= b)
            else: raise RuntimeError('Unknown binop ' + arg)

        elif op == PRINT:
            # Route through builtins['print'] so Tracer can capture output
            val = f.stack.pop()
            self.builtins['print'](val)

        elif op == POP_TOP:
            f.stack.pop()

        elif op == BUILD_LIST:
            items = [f.stack.pop() for _ in range(arg)][::-1]
            f.stack.append(items)

        elif op == BUILD_DICT:
            d = {}
            for _ in range(arg):
                v = f.stack.pop(); k = f.stack.pop(); d[k] = v
            f.stack.append(d)

        elif op == CALL:
            fname, argc = arg
            args = [f.stack.pop() for _ in range(argc)][::-1]
            if fname in f.locals and isinstance(f.locals[fname], dict) and f.locals[fname].get('type') == 'function':
                func = f.locals[fname]
            elif fname in f.globals and isinstance(f.globals[fname], dict) and f.globals[fname].get('type') == 'function':
                func = f.globals[fname]
            elif fname in self.builtins:
                f.stack.append(self.builtins[fname](*args))
                return None
            else:
                raise NameError(f'Function {fname} not found')
            new_frame = Frame(func['code'], func['consts'], func['names'], f.globals)
            for i, p in enumerate(func['params']):
                new_frame.locals[p] = args[i] if i < len(args) else None
            self.frames.append(new_frame)
            f.stack.append(self.run_frame(new_frame))

        elif op == MAKE_FUNCTION:
            idx, fname = arg
            _, code_obj, consts, names, params = f.consts[idx]
            func_def = {'type': 'function', 'code': code_obj,
                        'consts': consts, 'names': names, 'params': params}
            f.locals[fname] = func_def
            f.globals[fname] = func_def

        elif op == RETURN:
            f._return_val = f.stack.pop() if f.stack else None
            self.frames.pop() if self.frames else None
            return '__RETURN__'

        elif op == JUMP_IF_FALSE:
            if not f.stack.pop(): f.ip = arg

        elif op == JUMP:
            f.ip = arg

        else:
            raise RuntimeError('Unknown opcode ' + str(op))

        return None


# ── Tracer observer (replaces TracingVM entirely) ─────────────────────────────

class Tracer(VMObserver):
    """
    Records every opcode step.  Attach with vm.add_observer(Tracer()).
    Also captures print output by patching the VM's print builtin.
    """

    def __init__(self, vm: VM):
        self.trace_log: List[dict] = []
        self.output_lines: List[str] = []
        # Patch print so we capture output without losing it
        orig_print = vm.builtins['print']
        def capturing_print(*args):
            line = ' '.join(str(a) for a in args)
            self.output_lines.append(line)
            orig_print(*args)
        vm.builtins['print'] = capturing_print

    def handle_event(self, event_type: str, **payload):
        if event_type == 'before_opcode':
            frame = payload['frame']
            entry = {
                'ip':          payload['ip'],
                'op':          payload['op'],
                'arg':         str(payload['arg']) if payload['arg'] is not None else None,
                'stack_before': [repr(v) for v in payload['stack']],
                'stack_after':  None,   # filled in after_opcode
                'locals':       {k: repr(v) for k, v in payload['locals'].items()
                                 if not k.startswith('__')},
            }
            self.trace_log.append(entry)
        elif event_type == 'after_opcode' and self.trace_log:
            self.trace_log[-1]['stack_after'] = [repr(v) for v in payload['stack']]

# -------------------------
# Convenience API
# -------------------------
def compile_and_run(source: str, payload: Optional[ULPayload] = None):
    tokens = tokenize(source)
    parser = Parser(tokens)
    ast = parser.parse()
    comp = Compiler()
    code, consts, names = comp.compile(ast) or (comp.code, comp.consts, comp.names)
    vm = VM()
    return vm.run_code(code, consts, names, globals_={})

# -------------------------
# Example program
# -------------------------
if __name__ == '__main__':
    src = '''
set x to 5
set y to 3
function add a b
    return a + b
end
set z to add( x , y )
print z
repeat 3 times
    print "loop"
end
'''
    print("Running UL program:")
    compile_and_run(src)
