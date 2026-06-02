from enum import IntEnum

INSTR_SIZE = 4   # длина инструкции в байтах (фиксированная, RISC)


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
    EI = 21
    DI = 22


_BRANCH_OPS = {Opcode.JMP, Opcode.JZ, Opcode.JNZ, Opcode.JL,
               Opcode.JLE, Opcode.JG, Opcode.JGE}
_MEM_OPS = {Opcode.LD, Opcode.ST}
_NO_OPERAND_OPS = {Opcode.HALT, Opcode.IRET, Opcode.EI, Opcode.DI}


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


def mnemonic(opcode, rd, rs, imm):
    """Человекочитаемая запись инструкции для листинга."""
    name = opcode.name.lower()
    if opcode in _NO_OPERAND_OPS:
        return name
    if opcode in _BRANCH_OPS:
        return f"{name} 0x{imm & 0xFFFF:04X}"
    if opcode in _MEM_OPS:
        sign = "+" if imm >= 0 else "-"
        return f"{name} r{rd}, [r{rs}{sign}0x{abs(imm):X}]"
    if opcode == Opcode.LI:
        return f"{name} r{rd}, #{imm}"
    if opcode == Opcode.IN:
        return f"{name} r{rd}, port#{imm}"
    if opcode == Opcode.OUT:
        return f"{name} r{rs}, port#{imm}"
    # ALU: ADD/SUB/MUL/DIV/MOD/CMP
    return f"{name} r{rd}, r{rs}"


def write_code(filename, program):
    """Пишет образ памяти: по 4 байта на инструкцию, подряд.
    program — список кортежей (opcode, rd, rs, imm)."""
    with open(filename, "wb") as f:
        for opcode, rd, rs, imm in program:
            f.write(encode(opcode, rd, rs, imm))


def write_listing(filename, program, start_addr=0):
    """Отладочный листинг: <addr> - <HEXCODE> - <mnemonic>"""
    with open(filename, "w", encoding="utf-8") as f:
        for i, (opcode, rd, rs, imm) in enumerate(program):
            raw = encode(opcode, rd, rs, imm)
            hexcode = raw.hex().upper()
            addr = start_addr + i * INSTR_SIZE
            f.write(f"{addr:04X} - {hexcode} - {mnemonic(opcode, rd, rs, imm)}\n")


def read_image(filename):
    """Читает .bin как сырой образ памяти (bytes)."""
    with open(filename, "rb") as f:
        return f.read()


# Старое API оставляем для совместимости со старыми тестами
def read_code(filename):
    """[deprecated] Возвращает список декодированных инструкций.
    Машина теперь грузит образ через read_image и декодирует на лету при FETCH."""
    program = []
    with open(filename, "rb") as f:
        while True:
            chunk = f.read(INSTR_SIZE)
            if not chunk:
                break
            program.append(decode(chunk))
    return program