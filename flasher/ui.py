"""Минимальный UI AtomSpectra Flasher. Один экран."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

_PROGRESS_RE = re.compile(r"\((\d{1,3})\s*%\)")

from . import __version__
from .ports import list_candidates, pick_default
from .projects import Project, all_projects
from .worker import FlashWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"AtomSpectra Waterfall Flasher {__version__}")
        self.resize(720, 460)
        self._worker: FlashWorker | None = None
        self._active_project: Project | None = None
        self._projects: list[Project] = all_projects()
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        self._build_row_project(root)
        self._build_row_port(root)
        self._build_row_erase(root)
        self._build_row_install(root)
        self._build_row_progress(root)
        self._build_log(root)
        self._refresh_ports()

    def _build_row_project(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Проект:"))
        self.cbo_project = QComboBox()
        for p in self._projects:
            self.cbo_project.addItem(p.title, p)
        row.addWidget(self.cbo_project, 1)
        root.addLayout(row)

    def _build_row_port(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("COM-порт:"))
        self.cbo_port = QComboBox()
        row.addWidget(self.cbo_port, 1)
        btn = QPushButton("Обновить")
        btn.clicked.connect(self._refresh_ports)
        row.addWidget(btn)
        root.addLayout(row)

    def _build_row_erase(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self.chk_erase = QCheckBox(
            "Полный сброс перед прошивкой "
            "(стереть настройки WiFi, ~30-60с дольше)")
        self.chk_erase.setChecked(False)
        row.addWidget(self.chk_erase)
        row.addStretch(1)
        root.addLayout(row)

    def _build_row_install(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self.btn_install = QPushButton("Установить")
        self.btn_install.setMinimumHeight(44)
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        self.btn_install.setFont(f)
        self.btn_install.clicked.connect(self._on_install)
        row.addWidget(self.btn_install, 1)
        root.addLayout(row)

    def _build_row_progress(self, root: QVBoxLayout) -> None:
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("готов")
        root.addWidget(self.progress)

    def _build_log(self, root: QVBoxLayout) -> None:
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(5000)
        mono = QFont("Consolas", 9)
        mono.setStyleHint(QFont.Monospace)
        self.txt_log.setFont(mono)
        root.addWidget(self.txt_log, 1)

    def _log(self, s: str) -> None:
        self.txt_log.appendPlainText(s)
        m = _PROGRESS_RE.search(s)
        if m:
            v = int(m.group(1))
            if 0 <= v <= 100:
                self.progress.setValue(v)
                self.progress.setFormat(f"{v}%")

    def _refresh_ports(self) -> None:
        self.cbo_port.clear()
        items = list_candidates()
        shown = 0
        for pi in items:
            if pi.is_blacklisted:
                self._log(f"[ports] skip {pi.device}: {pi.display}")
                continue
            self.cbo_port.addItem(pi.display, pi)
            shown += 1
        default = pick_default(items)
        if default is not None:
            for i in range(self.cbo_port.count()):
                if self.cbo_port.itemData(i).device == default.device:
                    self.cbo_port.setCurrentIndex(i)
                    break
        self._log(f"[ports] показано: {shown} (всего {len(items)})")

    def _on_install(self) -> None:
        self.btn_install.setEnabled(False)
        pi = self.cbo_port.currentData()
        prj = self.cbo_project.currentData()
        if pi is None or prj is None:
            self.btn_install.setEnabled(True)
            QMessageBox.warning(self, "Установка", "Выбери проект и COM-порт.")
            return
        if pi.is_blacklisted:
            self.btn_install.setEnabled(True)
            QMessageBox.critical(self, "Установка",
                                 f"Порт {pi.device} — не ESP-устройство. Отказ.")
            return
        if not pi.is_esp_likely:
            r = QMessageBox.question(self, "Установка",
                                     f"Порт {pi.device} не похож на ESP.\n"
                                     "Всё равно прошить?")
            if r != QMessageBox.Yes:
                self.btn_install.setEnabled(True)
                return
        self._start_flash(prj, pi.device)

    def _start_flash(self, prj: Project, port: str) -> None:
        self.cbo_project.setEnabled(False)
        self.cbo_port.setEnabled(False)
        self.chk_erase.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setFormat("прошивка…")
        erase = self.chk_erase.isChecked()
        mode = "полный сброс + прошивка" if erase else "прошивка"
        self._log(f"=== {mode.capitalize()} «{prj.title}» на {port} ===")
        self._active_project = prj
        self._worker = FlashWorker(prj, port, erase_first=erase)
        self._worker.log.connect(self._log)
        self._worker.phase.connect(self._on_phase)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_phase(self, kind: str) -> None:
        if kind == "erase":
            self.progress.setRange(0, 0)
            self.progress.setFormat("стирание…")
        elif kind == "write":
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("прошивка…")

    def _on_done(self, ok: bool) -> None:
        self.btn_install.setEnabled(True)
        self.cbo_project.setEnabled(True)
        self.cbo_port.setEnabled(True)
        self.chk_erase.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if ok:
            self.progress.setValue(100)
            self.progress.setFormat("готово")
            self._log("=== Готово. Плата прошита. ===")
            steps = (self._active_project.next_steps or "").strip()
            if steps:
                self._log("")
                for line in steps.splitlines():
                    self._log(line)
            body = "Плата прошита.\n\n" + (steps if steps else "")
            QMessageBox.information(self, "Установка", body.rstrip())
        else:
            self.progress.setFormat("ошибка")
            self._log("=== Ошибка при прошивке. См. лог. ===")
            QMessageBox.critical(self, "Установка",
                                 "Ошибка при прошивке. См. лог.")

    def closeEvent(self, e: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            r = QMessageBox.question(
                self, "Выход",
                "Прошивка ещё идёт.\n"
                "Прервать сейчас — плата может остаться с битой прошивкой.\n"
                "Всё равно выйти?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self._worker.wait(5000)
        super().closeEvent(e)
