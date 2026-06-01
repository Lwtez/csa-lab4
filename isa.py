from enum import IntEnum

class Opcode(IntEnum):
    ADD = 1
    SUB = 2
    MUL = 3
    DIV = 4
    MOD = 5
    CMP = 6
    LD = 7
    ST = 8
    LI = 9
    JMP = 10
    JZ = 11
    JNZ = 12
    JL = 13
    JLE = 14
    JG = 15
    JGE = 16
    IN = 17
    OUT = 18
    HALT = 19
    IRET = 20

def encode(opcode, rd, rs, imm):
    if not -32768 <= imm <= 32767:
        raise ValueError(f"imm {imm} не влезает в 16 бит")
    word = (opcode << 24) | (rd << 20) | (rs << 16) | (imm & 0xFFFF)
    return bytes([(word >> 24) & 0xFF, (word >> 16) & 0xFF,
                  (word >> 8) & 0xFF, word & 0xFF])

def decode(data):
    word = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
    opcode = Opcode((word >> 24) & 0xFF)
    rd = (word >> 20) & 0x0F
    rs = (word >> 16) & 0x0F
    imm = word & 0xFFFF
    if imm & 0x8000:
        imm -= 0x10000
    return opcode, rd, rs, imm

def read_code(filename):
    program = []
    with open(filename, "rb") as f:
        while True:
            chunk = f.read(4)
            if not chunk:
                break
            program.append(decode(chunk))
    return program

def write_code(filename, program):
    """program — список кортежей (opcode, rd, rs, imm)."""
    with open(filename, "wb") as f:          # "wb" = write binary
        for opcode, rd, rs, imm in program:
            f.write(encode(opcode, rd, rs, imm))  # пишем 4 байта на инструкцию


