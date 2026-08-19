"""QThread обёртка для esptool. Прогресс/лог/итог через сигналы."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .board_reboot import reboot_before_flash
from .flasher import flash
from .projects import Project


class FlashWorker(QThread):
    log = Signal(str)
    phase = Signal(str)
    done = Signal(bool)

    def __init__(self, project: Project, port: str, baud: int = 921600,
                 erase_first: bool = False) -> None:
        super().__init__()
        self._project = project
        self._port = port
        self._baud = baud
        self._erase = erase_first

    def run(self) -> None:
        ok = flash(self._project, self._port, self.log.emit, self._baud,
                   erase_first=self._erase, phase=self.phase.emit)
        self.done.emit(ok)


class RebootWorker(QThread):
    """Фоновый поток: грациозный ребут платы по сети ПЕРЕД прошивкой.

    Best-effort — done всегда приходит (True/False), вызывающий код обязан
    продолжить прошивку в любом случае.
    """
    log = Signal(str)
    done = Signal(bool)

    def __init__(self, ip: str, timeout: float = 5.0) -> None:
        super().__init__()
        self._ip = ip
        self._timeout = timeout

    def run(self) -> None:
        ok = reboot_before_flash(self._ip, self.log.emit, timeout=self._timeout)
        self.done.emit(ok)
