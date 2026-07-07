"""esptool обёртка. Запуск в отдельном потоке, лог через callback."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from typing import Callable

try:
    import esptool
except ImportError:
    esptool = None

from .projects import Project

LogCB = Callable[[str], None]


class _LineWriter(io.TextIOBase):
    def __init__(self, cb: LogCB) -> None:
        super().__init__()
        self._cb = cb
        self._tail = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        parts = (self._tail + s).splitlines(keepends=True)
        if parts and parts[-1][-1:] not in ("\r", "\n"):
            self._tail = parts.pop()
        else:
            self._tail = ""
        for p in parts:
            line = p.rstrip("\r\n")
            if line:
                self._cb(line)
        return len(s)

    def flush(self) -> None:
        if self._tail.strip():
            self._cb(self._tail.strip())
        self._tail = ""


def _build_argv(project: Project, port: str, baud: int) -> list[str]:
    argv = ["--chip", project.chip, "--port", port, "--baud", str(baud),
            "--before", project.before, "--after", project.after]
    if not project.stub:
        argv.append("--no-stub")
    argv += ["write_flash", "--flash_mode", project.flash_mode,
             "--flash_freq", project.flash_freq,
             "--flash_size", project.flash_size]
    for seg in project.segments:
        argv += [hex(seg.offset), str(seg.path)]
    return argv


def _run_esptool(argv: list[str], log: LogCB) -> bool:
    if esptool is None:
        log("[ОШИБКА] esptool не установлен")
        return False
    writer = _LineWriter(log)
    try:
        with redirect_stdout(writer), redirect_stderr(writer):
            rc = esptool.main(argv)
    except SystemExit as e:
        writer.flush()
        code = int(e.code or 0)
        log(f"[esptool] exit={code}")
        return code == 0
    except Exception as e:
        writer.flush()
        log(f"[ОШИБКА esptool] {type(e).__name__}: {e}")
        return False
    writer.flush()
    if isinstance(rc, int):
        log(f"[esptool] rc={rc}")
        return rc == 0
    return True


def _erase_argv(project: Project, port: str, baud: int) -> list[str]:
    return ["--chip", project.chip, "--port", port, "--baud", str(baud),
            "--before", project.before, "--after", "no_reset", "erase_flash"]


def erase(project: Project, port: str, log: LogCB, baud: int = 460800) -> bool:
    argv = _erase_argv(project, port, baud)
    log(f"[esptool] {' '.join(argv)}")
    return _run_esptool(argv, log)


def flash(project: Project, port: str, log: LogCB, baud: int = 921600,
          erase_first: bool = False,
          phase: LogCB | None = None) -> bool:
    for seg in project.segments:
        if not seg.path.is_file():
            log(f"[ОШИБКА] нет файла: {seg.path}")
            return False
    if erase_first:
        if phase is not None:
            phase("erase")
        log("[flasher] полный сброс: стираю всю flash-память (~30-60с)…")
        if not erase(project, port, log, baud=460800):
            return False
    if phase is not None:
        phase("write")
    argv = _build_argv(project, port, baud)
    log(f"[esptool] {' '.join(argv)}")
    return _run_esptool(argv, log)
