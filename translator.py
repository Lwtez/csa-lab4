import sys
from isa import encode, write_code, Opcode

KEYWORDS = {"var"}
ASSIGN = {"="}
OP = {"+", "-", "/", "%", "*"}
SP = 7

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
        else:
            raise SyntaxError(f"ожидалось число или имя, а тут {tok_type}")
    
    def parse_term(self):
        node = self.parse_factor()                 
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] == "OP" and self.tokens[self.pos][1] in ("*", "/", "%"):  
            op = self.tokens[self.pos][1]
            self.pos += 1
            right = self.parse_factor()             
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return node
    
    def parse_add(self):
        node = self.parse_term()                    
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] == "OP" and self.tokens[self.pos][1] in ("+", "-"):
            op = self.tokens[self.pos][1]
            self.pos += 1
            right = self.parse_term()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
 
        return node

    def parse_statement(self):
        self.expect("VAR")
        name = self.expect("IDENT")
        self.expect("ASSIGN")
        value = self.parse_add()
        return {"type": "VarDecl", "name": name, "value": value}

    def parse(self):
        statements = []
        while self.pos < len(self.tokens):
            statements.append(self.parse_statement())
        return {"type": "Program", "body": statements}

class CodeGen:
    def __init__(self):
        self.code = []          
        self.vars = {}         
        self.next_addr = 0

    def var_addr(self, name):
        
        if name not in self.vars:
            self.vars[name] = self.next_addr
            self.next_addr += 1
        return self.vars[name]

    def emit(self, opcode, rd=0, rs=0, imm=0):
        self.code.append((opcode, rd, rs, imm))

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

        else:
            raise ValueError(f"не умею вычислять {node['type']}")

    def gen_statement(self, node):
        if node["type"] == "VarDecl":
            self.gen_expr(node["value"])
            self.pop(1)
            addr = self.var_addr(node["name"])
            self.emit(Opcode.ST, rd=1, imm=addr)

    def generate(self, program):
        self.emit(Opcode.LI, rd=SP, imm=32)
        for stmt in program["body"]:
            self.gen_statement(stmt)
        self.emit(Opcode.HALT)
        return self.code

    def push(self, reg):

        self.emit(Opcode.ST, rd=reg, rs=SP, imm=0)   
        self.emit(Opcode.LI, rd=3, imm=1)
        self.emit(Opcode.ADD, rd=SP, rs=3)           

    def pop(self, reg):

        self.emit(Opcode.LI, rd=3, imm=1)
        self.emit(Opcode.SUB, rd=SP, rs=3)           
        self.emit(Opcode.LD, rd=reg, rs=SP, imm=0) 
    
    def gen_binop(self, op):
        if op == "+":
            self.emit(Opcode.ADD, rd=1, rs=2)
        elif op == "-":
            self.emit(Opcode.SUB, rd=1, rs=2)
        elif op == "*":
            self.emit(Opcode.MUL, rd=1, rs=2)
        elif op == "/":
            self.emit(Opcode.DIV, rd=1, rs=2)
        elif op == "%":
            self.emit(Opcode.MOD, rd=1, rs=2)
        else:
            raise ValueError(f"неизвестная операция {op}")

def tokenize(text):
    tokens = []                      
    parts = text.split()

    for part in parts:
        if part in KEYWORDS:
            tokens.append(("VAR", part))      
        elif part in ASSIGN:
            tokens.append(("ASSIGN", part))
        elif part in OP:
            tokens.append(("OP", part))
        elif part.isdigit():
            tokens.append(("NUMBER", int(part)))
        else:
            tokens.append(("IDENT", part))

    return tokens 

def parse(tokens):
    return Parser(tokens).parse()

def translate_file(source_path, output_path):

    with open(source_path, "r", encoding="utf-8") as f:
        text = f.read()

    tokens = tokenize(text)
    tree = parse(tokens)
    cg = CodeGen()
    code = cg.generate(tree)


    write_code(output_path, code)
    print(f"Готово: {source_path} -> {output_path} ({len(code)} инструкций)")

if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "prog.alg"
    output = sys.argv[2] if len(sys.argv) > 2 else "prog.bin"
    translate_file(source, output)