from isa import decode, read_image, Opcode, INSTR_SIZE

MEM_SIZE = 8192          # размер единой памяти в байтах
TICK_LIMIT = 200_000_000

# Вектор прерывания: первое слово (адрес 0) занято JMP main,
# код ISR транслятор кладёт начиная с адреса 4.
INTERRUPT_VECTOR = INSTR_SIZE   # = 0x04

# ====== I/O: port-mapped =========================================
# Порты независимы от памяти. Адресуются полем imm инструкций IN/OUT.
# Port 0 — клавиатура (вход): данные приезжают по прерыванию.
# Port 1 — символьный вывод: запись добавляет байт в выходной буфер.
# Остальные порты зарезервированы; чтение/запись в них тихо игнорируются.

PORT_STDIN  = 0
PORT_STDOUT = 1


class IOController:
    def __init__(self):
        self.in_data = {PORT_STDIN: 0}   # port_num -> регистр данных входа
        self.out_buf = []                # выходной буфер символов

    def in_port(self, port_num):
        return self.in_data.get(port_num, 0)

    def out_port(self, port_num, value):
        if port_num == PORT_STDOUT:
            self.out_buf.append(value & 0xFF)
        # для остальных портов — пока no-op

    def deliver_input(self, port_num, value):
        """Снаружи (модель/расписание прерываний) кладёт байт в регистр данных порта."""
        self.in_data[port_num] = value


def _read_word(memory, addr):
    return int.from_bytes(memory[addr:addr+4], "little", signed=True)


def _write_word(memory, addr, value):
    memory[addr:addr+4] = (value & 0xFFFFFFFF).to_bytes(4, "little", signed=False)


def run(image_bytes, schedule=None, verbose=True):
    """Запускает образ памяти `image_bytes`. Возвращает буфер вывода."""
    schedule = list(schedule) if schedule else []

    # --- регистровый файл + флаги ---
    registers = [0] * 8
    zero_flag = False
    neg_flag = False

    # --- единая память (neum) ---
    memory = bytearray(MEM_SIZE)
    if len(image_bytes) > MEM_SIZE:
        raise RuntimeError(f"образ {len(image_bytes)} байт не помещается в память {MEM_SIZE}")
    memory[:len(image_bytes)] = image_bytes

    # --- состояние процессора ---
    pc = 0
    saved_pc = 0
    halted = False
    tick = 0

    interrupt_enabled = False
    in_interrupt = False
    io = IOController()

    # --- конвейерное состояние (FETCH / EXEC) ---
    stage = "FETCH"
    ir = None        # decoded instruction в IR
    ir_pc = 0        # PC инструкции, лежащей сейчас в IR (для лога)
    ir_word = 0      # сырой 32-бит код инструкции (для лога)

    def state_label():
        if halted:
            return "STOP"
        return "INT " if in_interrupt else "RUN "

    def log(stage_name, msg):
        if verbose:
            print(f"tick {tick:5} | {state_label()} | {stage_name:5} | {msg}")

    while not halted and tick < TICK_LIMIT:

        if stage == "FETCH":
            # === проверка прерывания — только на границе инструкций ===
            if interrupt_enabled and not in_interrupt and schedule:
                sched_tick, sched_char = schedule[0]
                if tick >= sched_tick:
                    schedule.pop(0)
                    io.deliver_input(PORT_STDIN, sched_char)
                    saved_pc = pc
                    in_interrupt = True
                    interrupt_enabled = False
                    pc = INTERRUPT_VECTOR
                    log("TRAP ", f"--> ISR, saved_pc=0x{saved_pc:04X}, vector=0x{INTERRUPT_VECTOR:04X}, port{PORT_STDIN}<=0x{sched_char:02X}")
                    tick += 1
                    continue

            # === FETCH: читаем 4 байта из памяти, декодируем, PC += 4 ===
            if pc + INSTR_SIZE > MEM_SIZE:
                raise RuntimeError(f"PC=0x{pc:04X} вышел за пределы памяти")
            word_bytes = bytes(memory[pc:pc+INSTR_SIZE])
            ir = decode(word_bytes)
            ir_pc = pc
            ir_word = int.from_bytes(word_bytes, "big")
            opcode, rd, rs, imm = ir
            log("FETCH", f"PC=0x{ir_pc:04X} IR=0x{ir_word:08X} ({opcode.name})")
            pc += INSTR_SIZE
            tick += 1
            stage = "EXEC"
            continue

        # === EXEC ===
        opcode, rd, rs, imm = ir
        regs_str = " ".join(f"R{i}={registers[i]}" for i in range(8))
        log("EXEC ",
            f"PC=0x{ir_pc:04X} | {regs_str} | ZF={int(zero_flag)} NF={int(neg_flag)} | {opcode.name}")

        if opcode == Opcode.ADD:
            registers[rd] = registers[rd] + registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
        elif opcode == Opcode.SUB:
            registers[rd] = registers[rd] - registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
        elif opcode == Opcode.MUL:
            registers[rd] = registers[rd] * registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
        elif opcode == Opcode.DIV:
            registers[rd] = registers[rd] // registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
        elif opcode == Opcode.MOD:
            registers[rd] = registers[rd] % registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
        elif opcode == Opcode.CMP:
            result = registers[rd] - registers[rs]
            zero_flag = (result == 0); neg_flag = (result < 0)

        elif opcode == Opcode.LD:
            addr = registers[rs] + imm
            registers[rd] = _read_word(memory, addr)
        elif opcode == Opcode.ST:
            addr = registers[rs] + imm
            _write_word(memory, addr, registers[rd])

        elif opcode == Opcode.LI:
            registers[rd] = imm

        elif opcode == Opcode.JMP:
            pc = imm
        elif opcode == Opcode.JZ:
            if zero_flag: pc = imm
        elif opcode == Opcode.JNZ:
            if not zero_flag: pc = imm
        elif opcode == Opcode.JL:
            if neg_flag: pc = imm
        elif opcode == Opcode.JLE:
            if neg_flag or zero_flag: pc = imm
        elif opcode == Opcode.JG:
            if not neg_flag and not zero_flag: pc = imm
        elif opcode == Opcode.JGE:
            if not neg_flag: pc = imm

        elif opcode == Opcode.IN:
            # imm — номер порта
            registers[rd] = io.in_port(imm)
        elif opcode == Opcode.OUT:
            io.out_port(imm, registers[rs])

        elif opcode == Opcode.EI:
            interrupt_enabled = True
        elif opcode == Opcode.DI:
            interrupt_enabled = False
        elif opcode == Opcode.IRET:
            pc = saved_pc
            in_interrupt = False
            interrupt_enabled = True

        elif opcode == Opcode.HALT:
            halted = True
        else:
            raise ValueError(f"неизвестный опкод {opcode}")

        tick += 1
        stage = "FETCH"

    if tick >= TICK_LIMIT:
        print(f"!!! достигнут лимит {TICK_LIMIT} тактов — программа зависла")

    return io.out_buf


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python machine.py <bin_file> [input_file] [--quiet]")
        sys.exit(1)

    quiet = "--quiet" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    bin_file = args[0]
    image = read_image(bin_file)

    schedule = []
    if len(args) > 1:
        input_file = args[1]
        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(maxsplit=1)
                t = int(parts[0])
                char = parts[1]
                if char == "\\n":
                    code = 10
                elif char.isdigit() and len(char) > 1:
                    code = int(char)
                else:
                    code = ord(char[0])
                schedule.append((t, code))

    output = run(image, schedule=schedule, verbose=not quiet)
    print("OUTPUT:", "".join(chr(c) if 32 <= c < 127 else f"<{c}>" for c in output))