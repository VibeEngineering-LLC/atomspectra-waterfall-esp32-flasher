"""QThread обёртка для esptool. Прогресс/лог/итог через сигналы."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .flasher import flash
from .projects import Project


class FlashWorker(QThread):
    log = Signal(str)
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
                   erase_first=self._erase)
        self.done.emit(ok)
