import sys
from isa import encode, write_code, Opcode

KEYWORDS = {"var", "while", "if", "else"}
ASSIGN = {"="}
OP = {"+", "-", "/", "%", "*", "==", "!=", "<", "<=", ">", ">="}
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

    def parse_cmp(self):
        node = self.parse_add()                    
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] == "OP" and self.tokens[self.pos][1] in ("==", "!=", "<=", "<", ">=", ">"):
            op = self.tokens[self.pos][1]
            self.pos += 1
            right = self.parse_add()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
 
        return node

    def parse_statement(self):
        tok_type, _ = self.tokens[self.pos]
        if tok_type == "VAR":
            return self.parse_var_decl()
        elif tok_type == "WHILE":
            return self.parse_while()
        elif tok_type == "IF":
            return self.parse_if()
        elif tok_type == "IDENT":
            return self.parse_assign()
        else:
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
        self.expect("WHILE")
        self.expect("LPAREN")
        cond = self.parse_cmp()      
        self.expect("RPAREN")
        self.expect("LBRACE")
        body = []
        while self.tokens[self.pos][0] != "RBRACE":
            body.append(self.parse_statement())
        self.expect("RBRACE")
        return {"type": "While", "cond": cond, "body": body}
    
    def parse_if(self):
        self.expect("IF")
        self.expect("LPAREN")
        cond = self.parse_cmp()
        self.expect("RPAREN")
        self.expect("LBRACE")
        then_body = []
        while self.tokens[self.pos][0] != "RBRACE":
            then_body.append(self.parse_statement())
        self.expect("RBRACE")

        # else опционален
        else_body = []
        if self.pos < len(self.tokens) and self.tokens[self.pos][0] == "ELSE":
            self.expect("ELSE")
            self.expect("LBRACE")
            while self.tokens[self.pos][0] != "RBRACE":
                else_body.append(self.parse_statement())
            self.expect("RBRACE")

        return {"type": "If", "cond": cond, "then": then_body, "else": else_body}

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
        self.labels = {}
        self.label_counter = 0

    def new_label(self, base):
        self.label_counter += 1
        return f"{base}_{self.label_counter}"

    def place_label(self, name):
        self.labels[name] = len(self.code)

    def emit_jump(self, opcode, label):
        self.code.append(("ref", opcode, label))

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
        elif node["type"] == "Assign":
            self.gen_expr(node["value"])
            self.pop(1)
            addr = self.var_addr(node["name"])     
            self.emit(Opcode.ST, rd=1, rs=0, imm=addr)
        elif node["type"] == "While":
            top_lbl = self.new_label("while_top")
            end_lbl = self.new_label("while_end")
            self.place_label(top_lbl)
            self.gen_expr(node["cond"])               
            self.pop(1)
            self.emit(Opcode.LI, rd=2, imm=0)
            self.emit(Opcode.CMP, rd=1, rs=2)        
            self.emit_jump(Opcode.JZ, end_lbl)        
            for stmt in node["body"]:
                self.gen_statement(stmt)
            self.emit_jump(Opcode.JMP, top_lbl)       
            self.place_label(end_lbl)
        elif node["type"] == "If":
            else_lbl = self.new_label("if_else")
            end_lbl = self.new_label("if_end")

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

    def generate(self, program):
        self.emit(Opcode.LI, rd=SP, imm=32)
        for stmt in program["body"]:
            self.gen_statement(stmt)
        self.emit(Opcode.HALT)
        return self.link()

    def link(self):
        linked = []
        for item in self.code:
            if isinstance(item, tuple) and len(item) == 3 and item[0] == "ref":
                _, op, label = item
                addr = self.labels[label]
                linked.append((op, 0, 0, addr))
            else:
                linked.append(item)
        return linked

    def push(self, reg):

        self.emit(Opcode.ST, rd=reg, rs=SP, imm=0)   
        self.emit(Opcode.LI, rd=3, imm=1)
        self.emit(Opcode.ADD, rd=SP, rs=3)           

    def pop(self, reg):

        self.emit(Opcode.LI, rd=3, imm=1)
        self.emit(Opcode.SUB, rd=SP, rs=3)           
        self.emit(Opcode.LD, rd=reg, rs=SP, imm=0) 
    
    def gen_binop(self, op):
        arith = {"+": Opcode.ADD, "-": Opcode.SUB, "*": Opcode.MUL,
             "/": Opcode.DIV, "%": Opcode.MOD}
        if op in arith:
            self.emit(arith[op], rd=1, rs=2)
            return

        cmp_jumps = {
            "==": Opcode.JZ, "!=": Opcode.JNZ,
            "<": Opcode.JL, "<=": Opcode.JLE,
            ">": Opcode.JG, ">=": Opcode.JGE,
        }
        jump_op = cmp_jumps[op]
        true_lbl = self.new_label("cmp_true")
        end_lbl = self.new_label("cmp_end")

        self.emit(Opcode.CMP, rd=1, rs=2)       
        self.emit_jump(jump_op, true_lbl)         
        self.emit(Opcode.LI, rd=1, imm=0)         
        self.emit_jump(Opcode.JMP, end_lbl)        
        self.place_label(true_lbl)
        self.emit(Opcode.LI, rd=1, imm=1)      
        self.place_label(end_lbl)

def tokenize(text):
    tokens = []                      
    parts = text.split()

    for part in parts:
        if part in KEYWORDS:
            if part == "var":
                tokens.append(("VAR", part)) 
            elif part == "while":
                tokens.append(("WHILE", part))
            elif part == "if":
                tokens.append(("IF", part))
            elif part == "else":
                tokens.append(("ELSE", part))          
        elif part in ASSIGN:
            tokens.append(("ASSIGN", part))
        elif part in OP:
            tokens.append(("OP", part))
        elif part.isdigit():
            tokens.append(("NUMBER", int(part)))
        elif part == "(":
            tokens.append(("LPAREN", part))
        elif part == ")":
            tokens.append(("RPAREN", part))
        elif part == "{":
            tokens.append(("LBRACE", part))
        elif part == "}":
            tokens.append(("RBRACE", part))
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
    print(tree)
    cg = CodeGen()
    code = cg.generate(tree)


    write_code(output_path, code)
    print(f"Готово: {source_path} -> {output_path} ({len(code)} инструкций)")

if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "prog.alg"
    output = sys.argv[2] if len(sys.argv) > 2 else "prog.bin"
    translate_file(source, output)