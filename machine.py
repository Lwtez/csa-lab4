from isa import decode, read_image, Opcode, INSTR_SIZE, mnemonic

MEM_SIZE = 8192          # размер единой памяти в байтах
TICK_LIMIT = 200_000_000

# === таблица векторов прерываний ================================
# Адрес обработчика для вектора N лежит в cell INTR_VECTOR_TABLE + N*4.
# По умолчанию все cell'ы = 0 (т.к. память bytearray занулена).
# Программист устанавливает обработчик через set_interrupt_handler(N, fn).
INTR_VECTOR_TABLE = 0x12F0
KEYBOARD_VEC      = 0    # вектор клавиатуры

# ====== состояния процессора =====================================
STATE_STOP = "STOP"
STATE_RUN  = "RUN "
STATE_INT  = "INT "

# ====== фазы такта ===============================================
PHASE_FETCH = "FETCH"
PHASE_EXEC  = "EXEC "
PHASE_TRAP  = "TRAP "

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


def run(image_bytes, schedule=None, verbose=True, log_stream=None):
    """Запускает образ памяти `image_bytes`. Возвращает буфер вывода.

    verbose=True   — печатать журнал каждого такта (FETCH/EXEC/TRAP)
    log_stream     — куда писать журнал (по умолчанию stdout)
    """
    import sys
    if log_stream is None:
        log_stream = sys.stdout
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
    saved_regs = None          # снимок регистров на момент входа в прерывание
    saved_flags = (False, False)
    halted = False
    tick = 0
    instr_count = 0
    trap_count = 0

    interrupt_enabled = False
    in_interrupt = False
    io = IOController()

    # --- конвейерное состояние ---
    stage = PHASE_FETCH
    ir = None
    ir_pc = 0
    ir_word = 0

    def cpu_state():
        if halted: return STATE_STOP
        return STATE_INT if in_interrupt else STATE_RUN

    def log(phase, message):
        if not verbose:
            return
        print(f"[tick {tick:6}] {cpu_state()} {phase} | {message}", file=log_stream)

    def _char_repr(c):
        return f"'{chr(c)}'" if 32 <= c < 127 else f"\\x{c:02X}"

    def _mem_read_word(addr):
        return int.from_bytes(memory[addr:addr+4], "little", signed=True)

    def _mem_write_word(addr, value):
        memory[addr:addr+4] = (value & 0xFFFFFFFF).to_bytes(4, "little", signed=False)

    while not halted and tick < TICK_LIMIT:

        if stage == PHASE_FETCH:
            # === проверка прерывания — только на границе инструкций ===
            if interrupt_enabled and not in_interrupt and schedule:
                sched_tick, sched_char = schedule[0]
                if tick >= sched_tick:
                    # читаем адрес обработчика из таблицы векторов
                    vec_addr = INTR_VECTOR_TABLE + KEYBOARD_VEC * 4
                    handler_pc = _mem_read_word(vec_addr)
                    if handler_pc == 0:
                        raise RuntimeError(
                            f"прерывание сработало (port#{PORT_STDIN}), "
                            f"но обработчик не установлен — вызовите "
                            f"set_interrupt_handler({KEYBOARD_VEC}, ...) до enable_interrupts()")
                    schedule.pop(0)
                    io.deliver_input(PORT_STDIN, sched_char)
                    # === сохраняем контекст: PC, все регистры, флаги ===
                    saved_pc = pc
                    saved_regs = list(registers)
                    saved_flags = (zero_flag, neg_flag)
                    in_interrupt = True
                    interrupt_enabled = False
                    pc = handler_pc
                    trap_count += 1
                    log(PHASE_TRAP,
                        f"interrupt vec={KEYBOARD_VEC}: saved_pc=0x{saved_pc:04X}, "
                        f"handler=0x{handler_pc:04X}, port#{PORT_STDIN}<={sched_char:#04x} ({_char_repr(sched_char)})")
                    tick += 1
                    continue

            # === FETCH ===
            if pc + INSTR_SIZE > MEM_SIZE:
                raise RuntimeError(f"PC=0x{pc:04X} вышел за пределы памяти")
            word_bytes = bytes(memory[pc:pc+INSTR_SIZE])
            ir = decode(word_bytes)
            ir_pc = pc
            ir_word = int.from_bytes(word_bytes, "big")
            opcode, rd, rs, imm = ir
            log(PHASE_FETCH,
                f"PC=0x{ir_pc:04X} | IR=0x{ir_word:08X} ({mnemonic(opcode, rd, rs, imm)})")
            pc += INSTR_SIZE
            tick += 1
            stage = PHASE_EXEC
            continue

        # === EXEC ===
        opcode, rd, rs, imm = ir
        instr_count += 1
        mnem = mnemonic(opcode, rd, rs, imm)
        effect = ""    # описание эффекта инструкции для лога

        if opcode == Opcode.ADD:
            registers[rd] = registers[rd] + registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
            effect = f"R{rd} := {registers[rd]}"
        elif opcode == Opcode.SUB:
            registers[rd] = registers[rd] - registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
            effect = f"R{rd} := {registers[rd]}"
        elif opcode == Opcode.MUL:
            registers[rd] = registers[rd] * registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
            effect = f"R{rd} := {registers[rd]}"
        elif opcode == Opcode.DIV:
            registers[rd] = registers[rd] // registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
            effect = f"R{rd} := {registers[rd]}"
        elif opcode == Opcode.MOD:
            registers[rd] = registers[rd] % registers[rs]
            zero_flag = (registers[rd] == 0); neg_flag = (registers[rd] < 0)
            effect = f"R{rd} := {registers[rd]}"
        elif opcode == Opcode.CMP:
            result = registers[rd] - registers[rs]
            zero_flag = (result == 0); neg_flag = (result < 0)
            effect = f"R{rd} - R{rs} = {result}"

        elif opcode == Opcode.LD:
            addr = registers[rs] + imm
            value = _mem_read_word(addr)
            registers[rd] = value
            effect = f"R{rd} := mem[0x{addr:04X}] = {value}"
        elif opcode == Opcode.ST:
            addr = registers[rs] + imm
            _mem_write_word(addr, registers[rd])
            effect = f"mem[0x{addr:04X}] := {registers[rd]}"

        elif opcode == Opcode.LI:
            registers[rd] = imm
            effect = f"R{rd} := {imm}"

        elif opcode == Opcode.JMP:
            pc = imm
            effect = f"PC := 0x{imm:04X}"
        elif opcode == Opcode.JR:
            pc = registers[rs]
            effect = f"JR, PC := 0x{pc:04X}"
        elif opcode in (Opcode.JZ, Opcode.JNZ, Opcode.JL, Opcode.JLE, Opcode.JG, Opcode.JGE):
            cond_map = {
                Opcode.JZ:  zero_flag,
                Opcode.JNZ: not zero_flag,
                Opcode.JL:  neg_flag,
                Opcode.JLE: neg_flag or zero_flag,
                Opcode.JG:  not neg_flag and not zero_flag,
                Opcode.JGE: not neg_flag,
            }
            if cond_map[opcode]:
                pc = imm
                effect = f"taken, PC := 0x{imm:04X}"
            else:
                effect = "not taken"

        elif opcode == Opcode.IN:
            value = io.in_port(imm)
            registers[rd] = value
            effect = f"R{rd} := port#{imm} = 0x{value:02X} ({_char_repr(value)})"
        elif opcode == Opcode.OUT:
            value = registers[rs] & 0xFF
            io.out_port(imm, registers[rs])
            effect = f"port#{imm} <= 0x{value:02X} ({_char_repr(value)})"

        elif opcode == Opcode.EI:
            interrupt_enabled = True
            effect = "interrupts enabled"
        elif opcode == Opcode.DI:
            interrupt_enabled = False
            effect = "interrupts disabled"
        elif opcode == Opcode.IRET:
            pc = saved_pc
            # восстанавливаем контекст: регистры + флаги
            if saved_regs is not None:
                registers[:] = saved_regs
                zero_flag, neg_flag = saved_flags
            in_interrupt = False
            interrupt_enabled = True
            effect = f"IRET, PC := 0x{saved_pc:04X}, regs+flags restored"

        elif opcode == Opcode.HALT:
            halted = True
            effect = "(stop)"
        else:
            raise ValueError(f"неизвестный опкод {opcode}")

        flags = f"ZF={int(zero_flag)} NF={int(neg_flag)}"
        log(PHASE_EXEC,
            f"PC=0x{ir_pc:04X} | {mnem:<28} | {effect:<40} | {flags}")

        tick += 1
        stage = PHASE_FETCH

    # === финальная сводка ===
    if verbose:
        print(f"\n--- summary ---", file=log_stream)
        print(f"ticks executed: {tick}", file=log_stream)
        print(f"instructions:   {instr_count}", file=log_stream)
        print(f"interrupts:     {trap_count}", file=log_stream)
        print(f"output ({len(io.out_buf)} bytes): "
              f"{''.join(chr(c) if 32 <= c < 127 else f'<{c:02X}>' for c in io.out_buf)}",
              file=log_stream)
        regs_dump = ' '.join(f"R{i}={registers[i]}" for i in range(8))
        print(f"final regs:     {regs_dump}", file=log_stream)
        print(f"final flags:    ZF={int(zero_flag)} NF={int(neg_flag)}", file=log_stream)

    if tick >= TICK_LIMIT:
        print(f"!!! достигнут лимит {TICK_LIMIT} тактов — программа зависла",
              file=log_stream)

    return io.out_buf


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python machine.py <bin_file> [input_file] [--quiet] [--log <file>]")
        sys.exit(1)

    quiet = "--quiet" in sys.argv
    log_path = None
    if "--log" in sys.argv:
        idx = sys.argv.index("--log")
        if idx + 1 >= len(sys.argv):
            print("--log требует имя файла")
            sys.exit(1)
        log_path = sys.argv[idx + 1]
    # отфильтровываем флаги, оставляем позиционные
    positional = []
    skip = False
    for a in sys.argv[1:]:
        if skip:
            skip = False; continue
        if a == "--quiet":
            continue
        if a == "--log":
            skip = True; continue
        positional.append(a)

    bin_file = positional[0]
    image = read_image(bin_file)

    schedule = []
    if len(positional) > 1:
        input_file = positional[1]
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

    log_stream = None
    if log_path:
        log_stream = open(log_path, "w", encoding="utf-8")

    output = run(image, schedule=schedule, verbose=not quiet, log_stream=log_stream)

    if log_stream:
        log_stream.close()
        print(f"журнал записан в: {log_path}")

    print("OUTPUT:", "".join(chr(c) if 32 <= c < 127 else f"<{c}>" for c in output))