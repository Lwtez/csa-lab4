from isa import Opcode as O, write_code
from machine import run

program = [
    (O.JMP, 0, 0, 4),       # 0: прыжок на main
    # обработчик: читаем символ в R6
    (O.IN,  6, 0, 0),       # 1: R6 = input_port
    (O.IRET,0, 0, 0),       # 2: возврат
    (O.HALT,0, 0, 0),       # 3: заглушка
    # main:
    (O.EI,  0, 0, 0),       # 4: разрешить прерывания
    (O.LI,  1, 0, 1),       # 5
    (O.LI,  1, 0, 2),       # 6
    (O.LI,  1, 0, 3),       # 7
    (O.HALT,0, 0, 0),       # 8
]

write_code("isr_test.bin", program)
# на такте 3 приходит символ '5' (код 53)
run(program, schedule=[(3, 53)])