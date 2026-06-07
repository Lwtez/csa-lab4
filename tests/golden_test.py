"""Golden-тесты: транслятор + модель процессора.

Каждый YAML в tests/golden/*.yml описывает вход (in_*) и эталон (out_*).
out_* генерируются автоматически:

    pytest --update-goldens

затем их надо просмотреть глазами и закоммитить. На обычном `pytest`
значения сверяются.

Журнал процессора:
  * in_check_log: true        — сверять ПОЛНЫЙ журнал (маленькие программы);
  * in_log_max_lines: <N>     — сверять РЕПРЕЗЕНТАТИВНЫЙ срез (голова+хвост)
                                для тяжёлых алгоритмов, где полный журнал —
                                сотни килобайт;
  * ни того, ни другого       — журнал не проверяется.
"""
import io
import logging
from contextlib import redirect_stdout

import pytest

import machine
import translator

# Формат журнала ровно как в CLI: "DEBUG   machine:simulation    TICK: ..."
LOG_FMT = "%(levelname)-7s %(name)s    %(message)s"


def trim_log(text, max_lines, tail=15):
    """Репрезентативный срез журнала: большая «голова» (настройка + первые
    прерывания + начало вычислений) и короткий «хвост» (завершение/halt),
    между ними — маркер с числом пропущенных строк."""
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text
    head = max_lines - tail
    skipped = len(lines) - head - tail
    return (
        "".join(lines[:head])
        + f"... (пропущено {skipped} строк журнала) ...\n"
        + "".join(lines[-tail:])
    )


@pytest.mark.golden_test("golden/*.yml")
def test_translator_and_machine(golden):
    check_log = bool(golden.get("in_check_log"))
    max_lines = golden.get("in_log_max_lines")
    want_log = check_log or max_lines is not None

    # Свой перехватчик журнала с фиксированным форматом (стабильно для golden)
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setFormatter(logging.Formatter(LOG_FMT))
    logger = logging.getLogger("machine:simulation")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        image, listing, _ast = translator.translate_source(golden["in_source"])
        schedule = machine.parse_schedule(golden.get("in_stdin") or "")
        with redirect_stdout(io.StringIO()) as out:
            out_buf = machine.run(image, schedule=schedule, verbose=want_log)
    finally:
        logger.removeHandler(handler)

    program_output = "".join(
        chr(c) if 32 <= c < 127 else f"<{c}>" for c in out_buf
    )

    assert image == golden.out["out_code"]
    assert listing == golden.out["out_listing"]
    assert program_output == golden.out["out_output"]
    assert out.getvalue() == golden.out["out_stdout"]
    if check_log:
        assert log_buf.getvalue() == golden.out["out_log"]
    elif max_lines is not None:
        assert trim_log(log_buf.getvalue(), max_lines) == golden.out["out_log"]