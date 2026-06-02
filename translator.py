import sys
import os
from isa import encode, write_code, write_listing, Opcode, INSTR_SIZE

# ---------- лексер ----------
KEYWORDS_TYPE = {
    "var": "VAR",
    "while": "WHILE",
    "if": "IF",
    "else": "ELSE",
    "print": "PRINT",
    "print_num": "PRINT_NUM",
    "print_str": "PRINT_STR",
    "read": "READ",
}

# ---------- размещение памяти ----------
# (см. карту памяти в README/комментариях)
WORD_SIZE   = 4
# Данные размещаются сильно после кода, чтобы код не пересекался с данными.
# (в этой версии раскладка статическая; адаптивную сделаем при добавлении
#  настоящей секции данных, пункт 3 плана)
DATA_BASE   = 0x1000     # переменные: 0x1000, 0x1004, 0x1008 ...
STR_BUF     = 0x1100     # буфер цифр для print_num (до 16 цифр)
N_CELL      = 0x1140     # накапливаемое число из read()
READY_CELL  = 0x1144     # флаг "ввод готов"
STR_BASE    = 0x1200     # статические/строковые данные
STACK_INIT  = 0x1800     # начало стека (растёт вверх)

SP = 7   # R7 — указатель стека

# ---------- port-mapped I/O ----------
PORT_STDIN  = 0      # клавиатура (символ доставляется по прерыванию)
PORT_STDOUT = 1      # символьный вывод


# ============================================================
#                          PARSER
# ============================================================

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def expect(self, expected_type):
        tok_type, tok_value = self.tokens[self.pos]
        if tok_type != expected_type:
            raise SyntaxError(f"ожидался {expected_type}, а тут {tok_type}")
        self.pos += 1
        return tok_value

    def parse_factor(self):
        tok_type, tok_value = self.tokens[self.pos]
        if tok_type == "NUMBER":
            self.pos += 1
            return {"type": "Num", "value": tok_value}
        elif tok_type == "IDENT":
            self.pos += 1
            return {"type": "Var", "name": tok_value}
        elif tok_type == "READ":
            self.pos += 1
            self.expect("LPAREN")
            self.expect("RPAREN")
            return {"type": "Read"}
        else:
            raise SyntaxError(f"ожидалось число или имя, а тут {tok_type}")

    def parse_term(self):
        node = self.parse_factor()
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] == "OP" and self.tokens[self.pos][1] in ("*", "/", "%"):
            op = self.tokens[self.pos][1]; self.pos += 1
            right = self.parse_factor()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return node

    def parse_add(self):
        node = self.parse_term()
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] == "OP" and self.tokens[self.pos][1] in ("+", "-"):
            op = self.tokens[self.pos][1]; self.pos += 1
            right = self.parse_term()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return node

    def parse_cmp(self):
        node = self.parse_add()
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] == "OP" and self.tokens[self.pos][1] in ("==", "!=", "<=", "<", ">=", ">"):
            op = self.tokens[self.pos][1]; self.pos += 1
            right = self.parse_add()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return node

    def parse_statement(self):
        tok_type, _ = self.tokens[self.pos]
        if tok_type == "VAR":        return self.parse_var_decl()
        elif tok_type == "WHILE":    return self.parse_while()
        elif tok_type == "IF":       return self.parse_if()
        elif tok_type == "PRINT":    return self.parse_print()
        elif tok_type == "PRINT_NUM":return self.parse_print_num()
        elif tok_type == "PRINT_STR":return self.parse_print_str()
        elif tok_type == "IDENT":    return self.parse_assign()
        else: raise SyntaxError(f"неожиданный токен {tok_type}")

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
        while self.tokens[self.pos][0] != "RBRACE":
            body.append(self.parse_statement())
        self.expect("RBRACE")
        return {"type": "While", "cond": cond, "body": body}

    def parse_if(self):
        self.expect("IF"); self.expect("LPAREN")
        cond = self.parse_cmp()
        self.expect("RPAREN"); self.expect("LBRACE")
        then_body = []
        while self.tokens[self.pos][0] != "RBRACE":
            then_body.append(self.parse_statement())
        self.expect("RBRACE")
        else_body = []
        if self.pos < len(self.tokens) and self.tokens[self.pos][0] == "ELSE":
            self.expect("ELSE"); self.expect("LBRACE")
            while self.tokens[self.pos][0] != "RBRACE":
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
        self.pos += 1
        self.expect("LPAREN")
        tok_type, value = self.tokens[self.pos]
        if tok_type != "STRING":
            raise SyntaxError(f"ожидалась строка, получено {tok_type}")
        self.pos += 1
        self.expect("RPAREN")
        return {"type": "PrintStr", "value": value}

    def parse(self):
        statements = []
        while self.pos < len(self.tokens):
            statements.append(self.parse_statement())
        return {"type": "Program", "body": statements}


# ============================================================
#                         CODEGEN
# ============================================================

class CodeGen:
    def __init__(self):
        self.code = []                  # элементы: ('ref', op, label) или (op, rd, rs, imm)
        self.vars = {}                  # имя -> байтовый адрес
        self.next_var_offset = 0        # смещение следующей переменной в DATA_BASE
        self.labels = {}                # имя -> байтовый адрес
        self.label_counter = 0
        self.next_str_addr = STR_BASE   # байтовый адрес следующей строки
        self.data_section = {}          # байтовый адрес -> bytes (статические данные)

    # --- инфраструктура ---
    def new_label(self, base):
        self.label_counter += 1
        return f"{base}_{self.label_counter}"

    def place_label(self, name):
        # адрес = (индекс инструкции) * 4 — байтовый
        self.labels[name] = len(self.code) * INSTR_SIZE

    def emit_jump(self, opcode, label):
        self.code.append(("ref", opcode, label))

    def var_addr(self, name):
        if name not in self.vars:
            self.vars[name] = DATA_BASE + self.next_var_offset
            self.next_var_offset += WORD_SIZE
        return self.vars[name]

    def emit(self, opcode, rd=0, rs=0, imm=0):
        self.code.append((opcode, rd, rs, imm))

    # --- стек (для вычисления выражений) ---
    def push(self, reg):
        self.emit(Opcode.ST, rd=reg, rs=SP, imm=0)
        self.emit(Opcode.LI, rd=3, imm=WORD_SIZE)
        self.emit(Opcode.ADD, rd=SP, rs=3)

    def pop(self, reg):
        self.emit(Opcode.LI, rd=3, imm=WORD_SIZE)
        self.emit(Opcode.SUB, rd=SP, rs=3)
        self.emit(Opcode.LD, rd=reg, rs=SP, imm=0)

    # --- выражения ---
    def gen_expr(self, node):
        if node["type"] == "Num":
            self.emit(Opcode.LI, rd=1, imm=node["value"])
            self.push(1)

        elif node["type"] == "Var":
            addr = self.var_addr(node["name"])
            self.emit(Opcode.LD, rd=1, rs=0, imm=addr)
            self.push(1)

        elif node["type"] == "BinOp":
            self.gen_expr(node["left"])
            self.gen_expr(node["right"])
            self.pop(2)
            self.pop(1)
            self.gen_binop(node["op"])
            self.push(1)

        elif node["type"] == "Read":
            # сброс N_CELL и READY_CELL, EI, ждём в спин-цикле, DI, читаем N_CELL
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
        else:
            raise ValueError(f"не умею вычислять {node['type']}")

    def gen_binop(self, op):
        arith = {"+": Opcode.ADD, "-": Opcode.SUB, "*": Opcode.MUL,
                 "/": Opcode.DIV, "%": Opcode.MOD}
        if op in arith:
            self.emit(arith[op], rd=1, rs=2)
            return

        cmp_jumps = {
            "==": Opcode.JZ,  "!=": Opcode.JNZ,
            "<":  Opcode.JL,  "<=": Opcode.JLE,
            ">":  Opcode.JG,  ">=": Opcode.JGE,
        }
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

    # --- операторы ---
    def gen_statement(self, node):
        t = node["type"]
        if t == "VarDecl":
            self.gen_expr(node["value"])
            self.pop(1)
            addr = self.var_addr(node["name"])
            self.emit(Opcode.ST, rd=1, rs=0, imm=addr)

        elif t == "Assign":
            self.gen_expr(node["value"])
            self.pop(1)
            addr = self.var_addr(node["name"])
            self.emit(Opcode.ST, rd=1, rs=0, imm=addr)

        elif t == "While":
            top = self.new_label("while_top")
            end = self.new_label("while_end")
            self.place_label(top)
            self.gen_expr(node["cond"])
            self.pop(1)
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
            self.gen_expr(node["cond"])
            self.pop(1)
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
            self.gen_expr(node["expr"])
            self.pop(1)
            self.emit(Opcode.OUT, rd=0, rs=1, imm=PORT_STDOUT)

        elif t == "PrintNum":
            self.gen_expr(node["expr"])
            self.pop(1)
            self.gen_print_num()

        elif t == "PrintStr":
            self.gen_print_str(node["value"])

    # --- print_num: число в r1 -> печать в десятичном виде ---
    def gen_print_num(self):
        zero_skip = self.new_label("pn_zero_skip")
        end_lbl   = self.new_label("pn_end")

        self.emit(Opcode.LI, rd=2, imm=0)
        self.emit(Opcode.CMP, rd=1, rs=2)
        self.emit_jump(Opcode.JNZ, zero_skip)
        # n == 0 → выводим '0'
        self.emit(Opcode.LI, rd=2, imm=48)
        self.emit(Opcode.OUT, rd=0, rs=2, imm=PORT_STDOUT)
        self.emit_jump(Opcode.JMP, end_lbl)

        # извлечение цифр в STR_BUF, r4 — байтовое смещение
        self.place_label(zero_skip)
        self.emit(Opcode.LI, rd=4, imm=0)

        extract_top = self.new_label("pn_ext_top")
        extract_end = self.new_label("pn_ext_end")
        self.place_label(extract_top)
        self.emit(Opcode.LI, rd=2, imm=0)
        self.emit(Opcode.CMP, rd=1, rs=2)
        self.emit_jump(Opcode.JZ, extract_end)

        # r3 = (n % 10) + '0'
        self.emit(Opcode.LI, rd=3, imm=0)
        self.emit(Opcode.ADD, rd=3, rs=1)
        self.emit(Opcode.LI, rd=2, imm=10)
        self.emit(Opcode.MOD, rd=3, rs=2)
        self.emit(Opcode.LI, rd=2, imm=48)
        self.emit(Opcode.ADD, rd=3, rs=2)

        # STR_BUF[r4] = r3 (r4 — байтовое смещение)
        self.emit(Opcode.ST, rd=3, rs=4, imm=STR_BUF)

        # r4 += 4  (следующее слово)
        self.emit(Opcode.LI, rd=2, imm=WORD_SIZE)
        self.emit(Opcode.ADD, rd=4, rs=2)

        # n /= 10
        self.emit(Opcode.LI, rd=2, imm=10)
        self.emit(Opcode.DIV, rd=1, rs=2)
        self.emit_jump(Opcode.JMP, extract_top)
        self.place_label(extract_end)

        # вывод цифр в обратном порядке
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

    # --- print_str: строка лежит в секции данных (pstr: [length, ch, ch, ...]) ---
    def gen_print_str(self, s):
        length = len(s)
        base = self.next_str_addr
        self.next_str_addr += (length + 1) * WORD_SIZE

        # === статика: пишем в секцию данных, БЕЗ инициализирующих инструкций ===
        # длина (1 слово), затем по слову на символ — это и есть pstr
        self.data_section[base] = length.to_bytes(WORD_SIZE, "little", signed=False)
        for i, ch in enumerate(s):
            self.data_section[base + (i + 1) * WORD_SIZE] = \
                ord(ch).to_bytes(WORD_SIZE, "little", signed=False)

        # === код: только цикл вывода ===
        # r4 — байтовый счётчик (0, 4, 8, ...), r5 — длина в байтах
        self.emit(Opcode.LI, rd=4, imm=0)
        self.emit(Opcode.LD, rd=5, rs=0, imm=base)              # r5 = length (в символах)
        self.emit(Opcode.LI, rd=2, imm=WORD_SIZE)
        self.emit(Opcode.MUL, rd=5, rs=2)                        # r5 = length * 4 (в байтах)

        loop_top = self.new_label("strp_top")
        loop_end = self.new_label("strp_end")
        self.place_label(loop_top)
        self.emit(Opcode.CMP, rd=4, rs=5)
        self.emit_jump(Opcode.JGE, loop_end)
        self.emit(Opcode.LD, rd=3, rs=4, imm=base + WORD_SIZE)   # символ по r4 + (base+4)
        self.emit(Opcode.OUT, rd=0, rs=3, imm=PORT_STDOUT)
        self.emit(Opcode.LI, rd=2, imm=WORD_SIZE)
        self.emit(Opcode.ADD, rd=4, rs=2)
        self.emit_jump(Opcode.JMP, loop_top)
        self.place_label(loop_end)

    # --- ISR: накапливает цифры в N_CELL, по '\n' выставляет READY_CELL ---
    def gen_isr(self):
        is_newline = self.new_label("isr_nl")
        isr_ret    = self.new_label("isr_ret")

        self.emit(Opcode.IN, rd=6, rs=0, imm=PORT_STDIN)         # символ -> r6
        self.emit(Opcode.LI, rd=5, imm=10)
        self.emit(Opcode.CMP, rd=6, rs=5)
        self.emit_jump(Opcode.JZ, is_newline)

        # цифра: N_CELL = N_CELL*10 + (c - '0')
        self.emit(Opcode.LI, rd=5, imm=48)
        self.emit(Opcode.SUB, rd=6, rs=5)               # r6 = c - '0'
        self.emit(Opcode.LD, rd=5, rs=0, imm=N_CELL)    # r5 = N_CELL
        self.emit(Opcode.LI, rd=4, imm=10)
        self.emit(Opcode.MUL, rd=5, rs=4)               # r5 *= 10
        self.emit(Opcode.ADD, rd=5, rs=6)               # r5 += r6
        self.emit(Opcode.ST, rd=5, rs=0, imm=N_CELL)
        self.emit_jump(Opcode.JMP, isr_ret)

        self.place_label(is_newline)
        self.emit(Opcode.LI, rd=5, imm=1)
        self.emit(Opcode.ST, rd=5, rs=0, imm=READY_CELL)

        self.place_label(isr_ret)
        self.emit(Opcode.IRET)

    def generate(self, program):
        # Адрес 0x0000: JMP main
        self.emit_jump(Opcode.JMP, "__main__")
        # Адрес 0x0004 и далее: тело ISR (это и есть INTERRUPT_VECTOR в machine.py)
        self.gen_isr()
        # main:
        self.place_label("__main__")
        self.emit(Opcode.LI, rd=SP, imm=STACK_INIT)
        for stmt in program["body"]:
            self.gen_statement(stmt)
        self.emit(Opcode.HALT)
        return self.link()

    def link(self):
        linked = []
        for item in self.code:
            if isinstance(item, tuple) and len(item) == 3 and item[0] == "ref":
                _, op, label = item
                if label not in self.labels:
                    raise RuntimeError(f"метка '{label}' не определена")
                addr_byte = self.labels[label]   # уже в байтах
                linked.append((op, 0, 0, addr_byte))
            else:
                linked.append(item)
        return linked


# ============================================================
#                          TOKENIZER
# ============================================================

def tokenize(text):
    tokens = []
    pos = 0
    while pos < len(text):
        ch = text[pos]
        if ch in " \t\n\r":
            pos += 1; continue
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
        if ch.isdigit():
            start = pos
            while pos < len(text) and text[pos].isdigit():
                pos += 1
            tokens.append(("NUMBER", int(text[start:pos]))); continue
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
        if pos + 1 < len(text) and text[pos:pos+2] in ("==", "!=", "<=", ">="):
            tokens.append(("OP", text[pos:pos+2])); pos += 2; continue
        if ch in "+-*/%<>":
            tokens.append(("OP", ch)); pos += 1; continue
        if ch == "=":
            tokens.append(("ASSIGN", "=")); pos += 1; continue
        if ch == "(": tokens.append(("LPAREN", ch)); pos += 1; continue
        if ch == ")": tokens.append(("RPAREN", ch)); pos += 1; continue
        if ch == "{": tokens.append(("LBRACE", ch)); pos += 1; continue
        if ch == "}": tokens.append(("RBRACE", ch)); pos += 1; continue
        raise SyntaxError(f"непонятный символ: {ch!r}")
    return tokens


def parse(tokens):
    return Parser(tokens).parse()


# ============================================================
#                       ENTRY POINT
# ============================================================

def write_listing_full(filename, code, data_section, start_addr=0):
    """Расширенный листинг: секция кода + секция данных."""
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
                    if 32 <= val < 127:
                        descr = f".word {val}  ; '{chr(val)}'"
                    else:
                        descr = f".word {val}"
                else:
                    descr = f".bytes len={len(blob)}"
                f.write(f"{addr:04X} - {blob.hex().upper()} - {descr}\n")


# мнемонику тащим из isa, но в listing_full нужно её локально вызывать
from isa import mnemonic as _mnemonic


def translate_file(source_path, output_path):
    with open(source_path, "r", encoding="utf-8") as f:
        text = f.read()
    tokens = tokenize(text)
    tree = parse(tokens)

    cg = CodeGen()
    code = cg.generate(tree)
    data = cg.data_section

    # === собираем образ памяти ===
    code_size = len(code) * INSTR_SIZE
    if data:
        max_data_end = max(addr + len(blob) for addr, blob in data.items())
        image_size = max(code_size, max_data_end)
    else:
        image_size = code_size

    image = bytearray(image_size)
    # код в начале (с адреса 0)
    for i, (opcode, rd, rs, imm) in enumerate(code):
        image[i * INSTR_SIZE:(i + 1) * INSTR_SIZE] = encode(opcode, rd, rs, imm)
    # статические данные на своих байтовых адресах
    for addr, blob in data.items():
        image[addr:addr + len(blob)] = blob

    with open(output_path, "wb") as f:
        f.write(image)

    listing_path = os.path.splitext(output_path)[0] + ".lst"
    write_listing_full(listing_path, code, data, start_addr=0)

    data_bytes = sum(len(b) for b in data.values())
    print(f"OK: {source_path} -> {output_path}  "
          f"(код: {len(code)} инструкций / {code_size} B, "
          f"данные: {data_bytes} B, образ: {image_size} B), "
          f"листинг: {listing_path}")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "prog.alg"
    output = sys.argv[2] if len(sys.argv) > 2 else "prog.bin"
    translate_file(source, output)