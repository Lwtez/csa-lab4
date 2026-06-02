from isa import decode, read_code, Opcode

def run(program, schedule=None):
    schedule = list(schedule) if schedule else []
    registers = [0]*8

    zeroFlag = False
    negativeFlag = False

    memory = [0]*1024

    pc = 0
    tick = 0
    savedPc = 0
    halted = False

    output_buffer = []

    interrupt_enabled = False
    in_interrupt = False 
    input_port = 0
    INTERRUPT_VECTOR = 1

    while not halted and tick < 200_000_000:

        if interrupt_enabled and not in_interrupt and schedule:
            sched_tick, sched_char = schedule[0]
            if tick >= sched_tick:
                schedule.pop(0)
                input_port = sched_char 
                savedPc = pc
                in_interrupt = True
                interrupt_enabled = False
                pc = INTERRUPT_VECTOR
                #print(f"такт {tick:2} | INT | === вход в прерывание, saved_pc={savedPc} ===")
                tick += 1
                continue

        if pc >= len(program):
            raise RuntimeError(f"PC={pc} вышел за пределы программы — забыли HALT?")
        opcode, rd, rs, imm = program[pc]
        mark = "INT" if in_interrupt else "   "
        print(f"такт {tick:2} | {mark} | PC={pc} | R0={registers[0]} R1={registers[1]} R2={registers[2]} R3={registers[3]} R4={registers[4]} R5={registers[5]} R6={registers[6]} R7={registers[7]}| ZF={zeroFlag} | NF={negativeFlag} |{opcode.name}")

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
            registers[rd] = input_port
        elif opcode == Opcode.OUT:
            output_buffer.append(registers[rs])
        elif opcode == Opcode.EI:
            interrupt_enabled = True
        elif opcode == Opcode.DI:
            interrupt_enabled = False
        elif opcode == Opcode.IRET:
            pc = savedPc
            in_interrupt = False
            interrupt_enabled = True
        elif opcode == Opcode.HALT:
            halted = True              
        else:
            raise ValueError(f"неизвестный опкод {opcode}")
    if tick >= 200_000_000:
        print("!!! достигнут лимит тактов, программа зависла !!!")
    return output_buffer

if __name__ == "__main__":
    import sys
    from isa import read_code
    
    if len(sys.argv) < 2:
        print("Usage: python machine.py <bin_file> [input_file]")
        sys.exit(1)
    
    bin_file = sys.argv[1]
    program = read_code(bin_file)
    
    schedule = []
    if len(sys.argv) > 2:
        input_file = sys.argv[2]
        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(maxsplit=1)
                tick = int(parts[0])
                char = parts[1]
                if char == "\\n":
                    code = 10
                elif char.isdigit() and len(char) > 1:
                    code = int(char)        
                else:
                    code = ord(char[0])    
                schedule.append((tick, code))
    
    output = run(program, schedule=schedule)
    print("".join(chr(c) if 32 <= c < 127 else f"<{c}>" for c in output))