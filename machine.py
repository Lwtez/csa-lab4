from isa import decode, read_code, Opcode

def run(program):
    
    registers = [0]*8

    zeroFlag = False
    negativeFlag = False

    memory = [0]*64

    pc = 0
    tick = 0
    savedPc = 0
    halted = False

    output_buffer = []

    while not halted:
        if pc >= len(program):
            raise RuntimeError(f"PC={pc} вышел за пределы программы — забыли HALT?")
        opcode, rd, rs, imm = program[pc]
        print(f"такт {tick:2} | PC={pc} | R0={registers[0]} R1={registers[1]} R2={registers[2]} R3={registers[3]} R4={registers[4]} R5={registers[5]} R6={registers[6]} R7={registers[7]}| ZF={zeroFlag} | NF={negativeFlag} |{opcode.name}")

        pc = pc + 1
        tick += 1

        if opcode == Opcode.ADD:
            registers[rd] = registers[rd] + registers[rs]
            zeroFlag = (registers[rd] == 0)
            negativeFlag = (registers[rd] < 0)

        elif opcode == Opcode.SUB:
            registers[rd] = registers[rd] - registers[rs]
            zeroFlag = (registers[rd] == 0)
            negativeFlag = (registers[rd] < 0)

        elif opcode == Opcode.MUL:
            registers[rd] = registers[rd] * registers[rs]
            zeroFlag = (registers[rd] == 0)
            negativeFlag = (registers[rd] < 0)

        elif opcode == Opcode.DIV:
            registers[rd] = registers[rd] // registers[rs]
            zeroFlag = (registers[rd] == 0)
            negativeFlag = (registers[rd] < 0)

        elif opcode == Opcode.MOD:
            registers[rd] = registers[rd] % registers[rs]
            zeroFlag = (registers[rd] == 0)
            negativeFlag = (registers[rd] < 0)

        elif opcode == Opcode.CMP:
            result = registers[rd] - registers[rs]
            zeroFlag = (result == 0)
            negativeFlag = (result < 0)

        elif opcode == Opcode.LD:
            addr = registers[rs] + imm
            registers[rd] = memory[addr]

        elif opcode == Opcode.ST:
            addr = registers[rs] + imm
            memory[addr] = registers[rd]

        elif opcode == Opcode.LI:
            registers[rd] = imm

        elif opcode == Opcode.JMP:
            pc = imm

        elif opcode == Opcode.JZ:
            if zeroFlag:
                pc = imm
        elif opcode == Opcode.JNZ:
            if not zeroFlag:
                pc = imm
        elif opcode == Opcode.JL:
            if negativeFlag:
                pc = imm
        elif opcode == Opcode.JLE:
            if negativeFlag or zeroFlag:
                pc = imm
        elif opcode == Opcode.JG:
            if not negativeFlag and not zeroFlag:
                pc = imm
        elif opcode == Opcode.JGE:
            if not negativeFlag:
                pc = imm
        elif opcode == Opcode.IN:
            pass
        elif opcode == Opcode.OUT:
            output_buffer.append(registers[rs])
        elif opcode == Opcode.IRET:
            pc = savedPc
        elif opcode == Opcode.HALT:
            halted = True              
        else:
            raise ValueError(f"неизвестный опкод {opcode}")
    return output_buffer

if __name__ == "__main__":
    program = read_code("prog.bin")
    output = run(program)
    print("Output as chars:", "".join(chr(c) if 32 <= c < 127 else f"<{c}>" for c in output))