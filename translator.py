import sys
import os
from isa import encode, write_code, mnemonic as _mnemonic, Opcode, INSTR_SIZE


# ============================================================
#                          ЛЕКСЕР
# ============================================================

KEYWORDS_TYPE = {
    "var": "VAR",
    "while": "WHILE",
    "if": "IF",
    "else": "ELSE",
    "print": "PRINT",
    "print_num": "PRINT_NUM",
    "print_str": "PRINT_STR",
    "read": "READ",
    "function": "FUNCTION",
    "return": "RETURN",
}


# ---------- размещение памяти ----------
WORD_SIZE   = 4
DATA_BASE   = 0x1000     # bump-аллокатор для глобалок и фреймов функций
STR_BUF     = 0x1300     # буфер цифр для print_num
N_CELL      = 0x1340     # накапливаемое число из read()
READY_CELL  = 0x1344     # флаг "ввод готов"
STR_BASE    = 0x1400     # статические pstr-строки
STACK_INIT  = 0x1800     # начало стека (растёт вверх)

SP = 7   # R7 — указатель стека

# ---------- port-mapped I/O ----------
PORT_STDIN  = 0
PORT_STDOUT = 1


def tokenize(text):
    tokens = []
    pos = 0
    while pos < len(text):
        ch = text[pos]
        # пропуск пробелов
        if ch in " \t\n\r":
            pos += 1; continue
        # комментарий `//` до конца строки
        if pos + 1 < len(text) and text[pos:pos+2] == "//":
            while pos < len(text) and text[pos] != "\n":
                pos += 1
            continue
        # строковый литерал
        if ch == '"':
            pos += 1
            start = pos
            while pos < len(text) and text[pos] != '"':
                pos += 1
            if pos >= len(text):
                raise SyntaxError("незакрытая строка")
            value = text[start:pos]
            pos += 1
            tokens.append(("STRING", value)); continue
        # число
        if ch.isdigit():
            start = pos
            while pos < len(text) and text[pos].isdigit():
                pos += 1
            tokens.append(("NUMBER", int(text[start:pos]))); continue
        # идентификатор/ключевое слово
        if ch.isalpha() or ch == "_":
            start = pos
            while pos < len(text) and (text[pos].isalnum() or text[pos] == "_"):
                pos += 1
            word = text[start:pos]
            if word in KEYWORDS_TYPE:
                tokens.append((KEYWORDS_TYPE[word], word))
            else:
                tokens.append(("IDENT", word))
            continue
        # двухсимвольные операторы
        if pos + 1 < len(text) and text[pos:pos+2] in ("==", "!=", "<=", ">="):
            tokens.append(("OP", text[pos:pos+2])); pos += 2; continue
        # односимвольные операторы и знаки
        if ch in "+-*/%<>":
            tokens.append(("OP", ch)); pos += 1; continue
        if ch == "=": tokens.append(("ASSIGN", "=")); pos += 1; continue
        if ch == "(": tokens.append(("LPAREN", ch)); pos += 1; continue
        if ch == ")": tokens.append(("RPAREN", ch)); pos += 1; continue
        if ch == "{": tokens.append(("LBRACE", ch)); pos += 1; continue
        if ch == "}": tokens.append(("RBRACE", ch)); pos += 1; continue
        if ch == ",": tokens.append(("COMMA", ch)); pos += 1; continue
        raise SyntaxError(f"непонятный символ: {ch!r}")
    return tokens


# ============================================================
#                          ПАРСЕР
# ============================================================

_STMT_STARTERS = {"VAR", "WHILE", "IF", "ELSE", "PRINT", "PRINT_NUM",
                  "PRINT_STR", "RETURN", "FUNCTION"}


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self, k=0):
        if self.pos + k < len(self.tokens):
            return self.tokens[self.pos + k]
        return ("EOF", None)

    def expect(self, expected_type):
        tok_type, tok_value = self.peek()
        if tok_type != expected_type:
            raise SyntaxError(f"ожидался {expected_type}, а тут {tok_type}={tok_value!r}")
        self.pos += 1
        return tok_value

    # --- выражения (приоритеты снизу вверх) ---

    def parse_factor(self):
        tok_type, tok_value = self.peek()
        if tok_type == "NUMBER":
            self.pos += 1
            return {"type": "Num", "value": tok_value}
        if tok_type == "LPAREN":
            self.pos += 1
            node = self.parse_cmp()
            self.expect("RPAREN")
            return node
        if tok_type == "READ":
            self.pos += 1
            self.expect("LPAREN")
            self.expect("RPAREN")
            return {"type": "Read"}
        if tok_type == "IDENT":
            self.pos += 1
            # вызов функции?
            if self.peek()[0] == "LPAREN":
                self.pos += 1
                args = []
                if self.peek()[0] != "RPAREN":
                    args.append(self.parse_cmp())
                    while self.peek()[0] == "COMMA":
                        self.pos += 1
                        args.append(self.parse_cmp())
                self.expect("RPAREN")
                return {"type": "FuncCall", "name": tok_value, "args": args}
            return {"type": "Var", "name": tok_value}
        raise SyntaxError(f"ожидалось число/имя/'(', а тут {tok_type}")

    def parse_term(self):
        node = self.parse_factor()
        while self.peek()[0] == "OP" and self.peek()[1] in ("*", "/", "%"):
            op = self.peek()[1]; self.pos += 1
            right = self.parse_factor()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return node

    def parse_add(self):
        node = self.parse_term()
        while self.peek()[0] == "OP" and self.peek()[1] in ("+", "-"):
            op = self.peek()[1]; self.pos += 1
            right = self.parse_term()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return node

    def parse_cmp(self):
        node = self.parse_add()
        while self.peek()[0] == "OP" and self.peek()[1] in ("==", "!=", "<=", "<", ">=", ">"):
            op = self.peek()[1]; self.pos += 1
            right = self.parse_add()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return node

    # --- операторы ---

    def parse_statement(self):
        tok_type, _ = self.peek()
        if tok_type == "VAR":        return self.parse_var_decl()
        if tok_type == "WHILE":      return self.parse_while()
        if tok_type == "IF":         return self.parse_if()
        if tok_type == "PRINT":      return self.parse_print()
        if tok_type == "PRINT_NUM":  return self.parse_print_num()
        if tok_type == "PRINT_STR":  return self.parse_print_str()
        if tok_type == "RETURN":     return self.parse_return()
        if tok_type == "IDENT":
            # f(args) как statement vs assign
            if self.peek(1)[0] == "LPAREN":
                call = self.parse_factor()    # вернёт FuncCall
                return {"type": "CallStmt", "call": call}
            return self.parse_assign()
        raise SyntaxError(f"неожиданный токен {tok_type}")

    def parse_var_decl(self):
        self.expect("VAR")
        name = self.expect("IDENT")
        self.expect("ASSIGN")
        value = self.parse_cmp()
        return {"type": "VarDecl", "name": name, "value": value}

    def parse_assign(self):
        name = self.expect("IDENT")
        self.expect("ASSIGN")
        value = self.parse_cmp()
        return {"type": "Assign", "name": name, "value": value}

    def parse_while(self):
        self.expect("WHILE"); self.expect("LPAREN")
        cond = self.parse_cmp()
        self.expect("RPAREN"); self.expect("LBRACE")
        body = []
        while self.peek()[0] != "RBRACE":
            body.append(self.parse_statement())
        self.expect("RBRACE")
        return {"type": "While", "cond": cond, "body": body}

    def parse_if(self):
        self.expect("IF"); self.expect("LPAREN")
        cond = self.parse_cmp()
        self.expect("RPAREN"); self.expect("LBRACE")
        then_body = []
        while self.peek()[0] != "RBRACE":
            then_body.append(self.parse_statement())
        self.expect("RBRACE")
        else_body = []
        if self.peek()[0] == "ELSE":
            self.expect("ELSE"); self.expect("LBRACE")
            while self.peek()[0] != "RBRACE":
                else_body.append(self.parse_statement())
            self.expect("RBRACE")
        return {"type": "If", "cond": cond, "then": then_body, "else": else_body}

    def parse_print(self):
        self.expect("PRINT"); self.expect("LPAREN")
        expr = self.parse_cmp(); self.expect("RPAREN")
        return {"type": "Print", "expr": expr}

    def parse_print_num(self):
        self.expect("PRINT_NUM"); self.expect("LPAREN")
        expr = self.parse_cmp(); self.expect("RPAREN")
        return {"type": "PrintNum", "expr": expr}

    def parse_print_str(self):
        self.expect("PRINT_STR"); self.expect("LPAREN")
        tok_type, value = self.peek()
        if tok_type != "STRING":
            raise SyntaxError(f"ожидалась строка, получено {tok_type}")
        self.pos += 1
        self.expect("RPAREN")
        return {"type": "PrintStr", "value": value}

    def parse_return(self):
        self.expect("RETURN")
        # return может быть без значения: если следующий токен — конец блока или
        # начало нового statement'а, у return нет выражения.
        nxt = self.peek()[0]
        if nxt in _STMT_STARTERS or nxt in ("RBRACE", "EOF"):
            return {"type": "Return", "value": None}
        return {"type": "Return", "value": self.parse_cmp()}

    def parse_function_decl(self):
        self.expect("FUNCTION")
        name = self.expect("IDENT")
        self.expect("LPAREN")
        params = []
        if self.peek()[0] != "RPAREN":
            params.append(self.expect("IDENT"))
            while self.peek()[0] == "COMMA":
                self.pos += 1
                params.append(self.expect("IDENT"))
        self.expect("RPAREN"); self.expect("LBRACE")
        body = []
        while self.peek()[0] != "RBRACE":
            body.append(self.parse_statement())
        self.expect("RBRACE")
        return {"type": "FuncDecl", "name": name, "params": params, "body": body}

    def parse(self):
        functions = []
        statements = []
        while self.pos < len(self.tokens):
            if self.peek()[0] == "FUNCTION":
                functions.append(self.parse_function_decl())
            else:
                statements.append(self.parse_statement())
        return {"type": "Program", "functions": functions, "body": statements}


def parse(tokens):
    return Parser(tokens).parse()


# ============================================================
#                         КОДГЕН
# ============================================================

class CodeGen:
    def __init__(self):
        self.code = []                  # элементы: (op, rd, rs, imm) или (op, rd, rs, label_str)
        self.global_vars = {}           # name -> byte addr
        self.functions = {}             # name -> dict
        self.next_data_addr = DATA_BASE
        self.labels = {}                # label_name -> byte addr
        self.label_counter = 0
        self.next_str_addr = STR_BASE
        self.data_section = {}          # static data: addr -> bytes
        self.current_function = None    # имя текущей функции при кодгене её тела

    # ---------- инфраструктура ----------

    def new_label(self, base):
        self.label_counter += 1
        return f"{base}_{self.label_counter}"

    def place_label(self, name):
        self.labels[name] = len(self.code) * INSTR_SIZE

    def emit(self, opcode, rd=0, rs=0, imm=0):
        # imm может быть int или строка (метка) — разрешится при link()
        self.code.append((opcode, rd, rs, imm))

    def emit_jump(self, opcode, label):
        self.emit(opcode, rd=0, rs=0, imm=label)

    def link(self):
        linked = []
        for op, rd, rs, imm in self.code:
            if isinstance(imm, str):
                if imm not in self.labels:
                    raise RuntimeError(f"метка '{imm}' не определена")
                imm = self.labels[imm]
            linked.append((op, rd, rs, imm))
        return linked

    # ---------- работа с переменными (scope: local → global) ----------

    def _alloc_slot(self):
        addr = self.next_data_addr
        self.next_data_addr += WORD_SIZE
        if self.next_data_addr > STR_BUF:
            raise RuntimeError("переполнение области данных (variables + frames)")
        return addr

    def declare_local(self, name):
        fn = self.functions[self.current_function]
        if name not in fn["locals"]:
            fn["locals"][name] = self._alloc_slot()
        return fn["locals"][name]

    def declare_global(self, name):
        if name not in self.global_vars:
            self.global_vars[name] = self._alloc_slot()
        return self.global_vars[name]

    def var_addr(self, name):
        """Поиск: сначала локальные текущей функции, потом глобалы.
        Если нигде нет — создаём как глобал."""
        if self.current_function:
            fn = self.functions[self.current_function]
            if name in fn["locals"]:
                return fn["locals"][name]
        return self.declare_global(name)

    # ---------- стек (для вычисления выражений) ----------

    def push(self, reg):
        self.emit(Opcode.ST, rd=reg, rs=SP, imm=0)
        self.emit(Opcode.LI, rd=3, imm=WORD_SIZE)
        self.emit(Opcode.ADD, rd=SP, rs=3)

    def pop(self, reg):
        self.emit(Opcode.LI, rd=3, imm=WORD_SIZE)
        self.emit(Opcode.SUB, rd=SP, rs=3)
        self.emit(Opcode.LD, rd=reg, rs=SP, imm=0)

    # ---------- выражения ----------

    def gen_expr(self, node):
        t = node["type"]
        if t == "Num":
            self.emit(Opcode.LI, rd=1, imm=node["value"])
            self.push(1)
        elif t == "Var":
            addr = self.var_addr(node["name"])
            self.emit(Opcode.LD, rd=1, rs=0, imm=addr)
            self.push(1)
        elif t == "BinOp":
            self.gen_expr(node["left"])
            self.gen_expr(node["right"])
            self.pop(2)
            self.pop(1)
            self.gen_binop(node["op"])
            self.push(1)
        elif t == "Read":
            self.emit(Opcode.LI, rd=1, imm=0)
            self.emit(Opcode.ST, rd=1, rs=0, imm=N_CELL)
            self.emit(Opcode.ST, rd=1, rs=0, imm=READY_CELL)
            self.emit(Opcode.EI)
            wait_top = self.new_label("read_wait")
            self.place_label(wait_top)
            self.emit(Opcode.LD, rd=1, rs=0, imm=READY_CELL)
            self.emit(Opcode.LI, rd=2, imm=0)
            self.emit(Opcode.CMP, rd=1, rs=2)
            self.emit_jump(Opcode.JZ, wait_top)
            self.emit(Opcode.DI)
            self.emit(Opcode.LD, rd=1, rs=0, imm=N_CELL)
            self.push(1)
        elif t == "FuncCall":
            self.gen_call(node)
        else:
            raise ValueError(f"не умею вычислять {t}")

    def gen_binop(self, op):
        arith = {"+": Opcode.ADD, "-": Opcode.SUB, "*": Opcode.MUL,
                 "/": Opcode.DIV, "%": Opcode.MOD}
        if op in arith:
            self.emit(arith[op], rd=1, rs=2); return
        cmp_jumps = {"==": Opcode.JZ, "!=": Opcode.JNZ,
                     "<":  Opcode.JL, "<=": Opcode.JLE,
                     ">":  Opcode.JG, ">=": Opcode.JGE}
        jump_op = cmp_jumps[op]
        true_lbl = self.new_label("cmp_true")
        end_lbl  = self.new_label("cmp_end")
        self.emit(Opcode.CMP, rd=1, rs=2)
        self.emit_jump(jump_op, true_lbl)
        self.emit(Opcode.LI, rd=1, imm=0)
        self.emit_jump(Opcode.JMP, end_lbl)
        self.place_label(true_lbl)
        self.emit(Opcode.LI, rd=1, imm=1)
        self.place_label(end_lbl)

    def gen_call(self, node):
        """Вызов функции как выражение: оставляет возвращаемое значение на стеке."""
        name = node["name"]
        if name not in self.functions:
            raise RuntimeError(f"вызов неизвестной функции '{name}'")
        fn = self.functions[name]
        if len(node["args"]) != len(fn["params"]):
            raise RuntimeError(
                f"функция {name} ждёт {len(fn['params'])} аргументов, передано {len(node['args'])}")

        # вычисляем аргументы и пишем в ячейки фрейма (param-сначала-в-стек, потом в ячейку)
        for arg, param_name in zip(node["args"], fn["params"]):
            self.gen_expr(arg)
            self.pop(1)
            self.emit(Opcode.ST, rd=1, rs=0, imm=fn["locals"][param_name])

        # адрес возврата → в RA-ячейку фрейма
        ret_lbl = self.new_label(f"ret_from_{name}")
        self.emit(Opcode.LI, rd=1, imm=ret_lbl)        # imm = строковая метка, разрешится в link
        self.emit(Opcode.ST, rd=1, rs=0, imm=fn["ra_addr"])

        # прыгаем в функцию
        self.emit_jump(Opcode.JMP, fn["entry_label"])
        # точка возврата
        self.place_label(ret_lbl)

        # читаем возвращаемое значение и кладём на стек
        self.emit(Opcode.LD, rd=1, rs=0, imm=fn["rv_addr"])
        self.push(1)

    # ---------- операторы ----------

    def gen_statement(self, node):
        t = node["type"]
        if t == "VarDecl":
            self.gen_expr(node["value"]); self.pop(1)
            if self.current_function:
                addr = self.declare_local(node["name"])
            else:
                addr = self.declare_global(node["name"])
            self.emit(Opcode.ST, rd=1, rs=0, imm=addr)

        elif t == "Assign":
            self.gen_expr(node["value"]); self.pop(1)
            addr = self.var_addr(node["name"])
            self.emit(Opcode.ST, rd=1, rs=0, imm=addr)

        elif t == "While":
            top = self.new_label("while_top")
            end = self.new_label("while_end")
            self.place_label(top)
            self.gen_expr(node["cond"]); self.pop(1)
            self.emit(Opcode.LI, rd=2, imm=0)
            self.emit(Opcode.CMP, rd=1, rs=2)
            self.emit_jump(Opcode.JZ, end)
            for stmt in node["body"]:
                self.gen_statement(stmt)
            self.emit_jump(Opcode.JMP, top)
            self.place_label(end)

        elif t == "If":
            else_lbl = self.new_label("if_else")
            end_lbl  = self.new_label("if_end")
            self.gen_expr(node["cond"]); self.pop(1)
            self.emit(Opcode.LI, rd=2, imm=0)
            self.emit(Opcode.CMP, rd=1, rs=2)
            self.emit_jump(Opcode.JZ, else_lbl)
            for stmt in node["then"]:
                self.gen_statement(stmt)
            self.emit_jump(Opcode.JMP, end_lbl)
            self.place_label(else_lbl)
            for stmt in node["else"]:
                self.gen_statement(stmt)
            self.place_label(end_lbl)

        elif t == "Print":
            self.gen_expr(node["expr"]); self.pop(1)
            self.emit(Opcode.OUT, rd=0, rs=1, imm=PORT_STDOUT)

        elif t == "PrintNum":
            self.gen_expr(node["expr"]); self.pop(1)
            self.gen_print_num()

        elif t == "PrintStr":
            self.gen_print_str(node["value"])

        elif t == "CallStmt":
            # вычисляем вызов как выражение, отбрасываем результат
            self.gen_expr(node["call"])
            self.pop(1)

        elif t == "Return":
            self.gen_return(node)

        else:
            raise ValueError(f"не умею компилировать оператор {t}")

    def gen_return(self, node):
        if self.current_function is None:
            raise RuntimeError("return вне функции")
        fn = self.functions[self.current_function]
        if node["value"] is not None:
            self.gen_expr(node["value"])
            self.pop(1)
        else:
            self.emit(Opcode.LI, rd=1, imm=0)
        self.emit(Opcode.ST, rd=1, rs=0, imm=fn["rv_addr"])
        self.emit(Opcode.LD, rd=1, rs=0, imm=fn["ra_addr"])
        self.emit(Opcode.JR, rd=0, rs=1, imm=0)

    # ---------- print_num: число в r1 → печать десятичное ----------
    def gen_print_num(self):
        zero_skip = self.new_label("pn_zero_skip")
        end_lbl   = self.new_label("pn_end")
        self.emit(Opcode.LI, rd=2, imm=0)
        self.emit(Opcode.CMP, rd=1, rs=2)
        self.emit_jump(Opcode.JNZ, zero_skip)
        self.emit(Opcode.LI, rd=2, imm=48)
        self.emit(Opcode.OUT, rd=0, rs=2, imm=PORT_STDOUT)
        self.emit_jump(Opcode.JMP, end_lbl)
        self.place_label(zero_skip)
        self.emit(Opcode.LI, rd=4, imm=0)
        extract_top = self.new_label("pn_ext_top")
        extract_end = self.new_label("pn_ext_end")
        self.place_label(extract_top)
        self.emit(Opcode.LI, rd=2, imm=0)
        self.emit(Opcode.CMP, rd=1, rs=2)
        self.emit_jump(Opcode.JZ, extract_end)
        self.emit(Opcode.LI, rd=3, imm=0)
        self.emit(Opcode.ADD, rd=3, rs=1)
        self.emit(Opcode.LI, rd=2, imm=10)
        self.emit(Opcode.MOD, rd=3, rs=2)
        self.emit(Opcode.LI, rd=2, imm=48)
        self.emit(Opcode.ADD, rd=3, rs=2)
        self.emit(Opcode.ST, rd=3, rs=4, imm=STR_BUF)
        self.emit(Opcode.LI, rd=2, imm=WORD_SIZE)
        self.emit(Opcode.ADD, rd=4, rs=2)
        self.emit(Opcode.LI, rd=2, imm=10)
        self.emit(Opcode.DIV, rd=1, rs=2)
        self.emit_jump(Opcode.JMP, extract_top)
        self.place_label(extract_end)
        print_top = self.new_label("pn_prn_top")
        print_end = self.new_label("pn_prn_end")
        self.place_label(print_top)
        self.emit(Opcode.LI, rd=2, imm=0)
        self.emit(Opcode.CMP, rd=4, rs=2)
        self.emit_jump(Opcode.JZ, print_end)
        self.emit(Opcode.LI, rd=2, imm=WORD_SIZE)
        self.emit(Opcode.SUB, rd=4, rs=2)
        self.emit(Opcode.LD, rd=3, rs=4, imm=STR_BUF)
        self.emit(Opcode.OUT, rd=0, rs=3, imm=PORT_STDOUT)
        self.emit_jump(Opcode.JMP, print_top)
        self.place_label(print_end)
        self.place_label(end_lbl)

    # ---------- print_str: статическая pstr-строка в секции данных ----------
    def gen_print_str(self, s):
        length = len(s)
        base = self.next_str_addr
        self.next_str_addr += (length + 1) * WORD_SIZE
        self.data_section[base] = length.to_bytes(WORD_SIZE, "little", signed=False)
        for i, ch in enumerate(s):
            self.data_section[base + (i + 1) * WORD_SIZE] = \
                ord(ch).to_bytes(WORD_SIZE, "little", signed=False)
        self.emit(Opcode.LI, rd=4, imm=0)
        self.emit(Opcode.LD, rd=5, rs=0, imm=base)
        self.emit(Opcode.LI, rd=2, imm=WORD_SIZE)
        self.emit(Opcode.MUL, rd=5, rs=2)
        loop_top = self.new_label("strp_top")
        loop_end = self.new_label("strp_end")
        self.place_label(loop_top)
        self.emit(Opcode.CMP, rd=4, rs=5)
        self.emit_jump(Opcode.JGE, loop_end)
        self.emit(Opcode.LD, rd=3, rs=4, imm=base + WORD_SIZE)
        self.emit(Opcode.OUT, rd=0, rs=3, imm=PORT_STDOUT)
        self.emit(Opcode.LI, rd=2, imm=WORD_SIZE)
        self.emit(Opcode.ADD, rd=4, rs=2)
        self.emit_jump(Opcode.JMP, loop_top)
        self.place_label(loop_end)

    # ---------- ISR ----------
    def gen_isr(self):
        is_newline = self.new_label("isr_nl")
        isr_ret    = self.new_label("isr_ret")
        self.emit(Opcode.IN, rd=6, rs=0, imm=PORT_STDIN)
        self.emit(Opcode.LI, rd=5, imm=10)
        self.emit(Opcode.CMP, rd=6, rs=5)
        self.emit_jump(Opcode.JZ, is_newline)
        self.emit(Opcode.LI, rd=5, imm=48)
        self.emit(Opcode.SUB, rd=6, rs=5)
        self.emit(Opcode.LD, rd=5, rs=0, imm=N_CELL)
        self.emit(Opcode.LI, rd=4, imm=10)
        self.emit(Opcode.MUL, rd=5, rs=4)
        self.emit(Opcode.ADD, rd=5, rs=6)
        self.emit(Opcode.ST, rd=5, rs=0, imm=N_CELL)
        self.emit_jump(Opcode.JMP, isr_ret)
        self.place_label(is_newline)
        self.emit(Opcode.LI, rd=5, imm=1)
        self.emit(Opcode.ST, rd=5, rs=0, imm=READY_CELL)
        self.place_label(isr_ret)
        self.emit(Opcode.IRET)

    # ---------- регистрация функции (выделение ячеек фрейма) ----------
    def register_function(self, fn_decl):
        name = fn_decl["name"]
        if name in self.functions:
            raise RuntimeError(f"функция '{name}' уже объявлена")
        locals_map = {}
        for p in fn_decl["params"]:
            locals_map[p] = self._alloc_slot()
        ra_addr = self._alloc_slot()
        rv_addr = self._alloc_slot()
        self.functions[name] = {
            "params": fn_decl["params"],
            "locals": locals_map,
            "ra_addr": ra_addr,
            "rv_addr": rv_addr,
            "entry_label": f"func_{name}",
            "ast": fn_decl,
        }

    def gen_function(self, name):
        fn = self.functions[name]
        self.current_function = name
        self.place_label(fn["entry_label"])
        for stmt in fn["ast"]["body"]:
            self.gen_statement(stmt)
        # неявный return 0, если функция не сделала это сама
        self.emit(Opcode.LI, rd=1, imm=0)
        self.emit(Opcode.ST, rd=1, rs=0, imm=fn["rv_addr"])
        self.emit(Opcode.LD, rd=1, rs=0, imm=fn["ra_addr"])
        self.emit(Opcode.JR, rd=0, rs=1, imm=0)
        self.current_function = None

    def generate(self, program):
        # 1-й проход: регистрируем все функции (резервируем ячейки фреймов).
        for fn_decl in program["functions"]:
            self.register_function(fn_decl)

        # Layout:
        #  0x0000:        JMP __main__
        #  0x0004:        тело ISR
        #  __main__:      инициализация SP + main-код + HALT
        #  func_<name>:   тела функций
        self.emit_jump(Opcode.JMP, "__main__")
        self.gen_isr()
        self.place_label("__main__")
        self.emit(Opcode.LI, rd=SP, imm=STACK_INIT)
        for stmt in program["body"]:
            self.gen_statement(stmt)
        self.emit(Opcode.HALT)

        for fn_decl in program["functions"]:
            self.gen_function(fn_decl["name"])

        return self.link()


# ============================================================
#                        ВЫХОДНЫЕ ФАЙЛЫ
# ============================================================

def write_listing_full(filename, code, data_section, start_addr=0):
    with open(filename, "w", encoding="utf-8") as f:
        f.write("== CODE ==\n")
        for i, (opcode, rd, rs, imm) in enumerate(code):
            raw = encode(opcode, rd, rs, imm)
            addr = start_addr + i * INSTR_SIZE
            f.write(f"{addr:04X} - {raw.hex().upper()} - {_mnemonic(opcode, rd, rs, imm)}\n")
        if data_section:
            f.write("\n== DATA ==\n")
            for addr in sorted(data_section.keys()):
                blob = data_section[addr]
                if len(blob) == WORD_SIZE:
                    val = int.from_bytes(blob, "little", signed=False)
                    descr = f".word {val}  ; '{chr(val)}'" if 32 <= val < 127 else f".word {val}"
                else:
                    descr = f".bytes len={len(blob)}"
                f.write(f"{addr:04X} - {blob.hex().upper()} - {descr}\n")


def translate_file(source_path, output_path):
    with open(source_path, "r", encoding="utf-8") as f:
        text = f.read()
    tokens = tokenize(text)
    tree = parse(tokens)

    cg = CodeGen()
    code = cg.generate(tree)
    data = cg.data_section

    code_size = len(code) * INSTR_SIZE
    if data:
        max_data_end = max(addr + len(blob) for addr, blob in data.items())
        image_size = max(code_size, max_data_end)
    else:
        image_size = code_size

    image = bytearray(image_size)
    for i, (opcode, rd, rs, imm) in enumerate(code):
        image[i * INSTR_SIZE:(i + 1) * INSTR_SIZE] = encode(opcode, rd, rs, imm)
    for addr, blob in data.items():
        image[addr:addr + len(blob)] = blob

    with open(output_path, "wb") as f:
        f.write(image)

    listing_path = os.path.splitext(output_path)[0] + ".lst"
    write_listing_full(listing_path, code, data)

    data_bytes = sum(len(b) for b in data.values())
    print(f"OK: {source_path} -> {output_path}  "
          f"(код: {len(code)} инструкций / {code_size} B, "
          f"данные: {data_bytes} B, образ: {image_size} B, "
          f"функций: {len(cg.functions)}), листинг: {listing_path}")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "prog.alg"
    output = sys.argv[2] if len(sys.argv) > 2 else "prog.bin"
    translate_file(source, output)