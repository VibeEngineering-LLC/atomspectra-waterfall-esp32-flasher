"""Минимальный UI AtomSpectra Flasher. Один экран."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

_PROGRESS_RE = re.compile(r"\((\d{1,3})\s*%\)")

from . import __version__
from .ports import list_candidates, pick_default
from .projects import Project, all_projects
from .worker import FlashWorker, RebootWorker
from .updater import (FirmwareRelease, NetworkError, ReleaseNotFoundError,
                      fetch_releases, get_cached_or_download)


class FetchWorker(QThread):
    """Фоновый поток: GET списка релизов с GitHub API."""
    done = Signal(object)   # list[FirmwareRelease], новые первыми
    error = Signal(str)

    def __init__(self, owner_repo: str, asset_name: str) -> None:
        super().__init__()
        self._owner_repo = owner_repo
        self._asset_name = asset_name

    def run(self) -> None:
        try:
            releases = fetch_releases(self._owner_repo, self._asset_name)
            self.done.emit(releases)
        except (NetworkError, ReleaseNotFoundError) as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"AtomSpectra Waterfall Flasher {__version__}")
        self.resize(720, 460)
        self._worker: FlashWorker | None = None
        self._reboot_worker: RebootWorker | None = None
        self._active_project: Project | None = None
        self._projects: list[Project] = all_projects()
        self._release: FirmwareRelease | None = None
        self._fetch_worker: FetchWorker | None = None
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        self._build_row_project(root)
        self._build_row_firmware(root)
        self._build_row_port(root)
        self._build_row_erase(root)
        self._build_row_reboot(root)
        self._build_row_wifi(root)
        self._build_row_install(root)
        self._build_row_progress(root)
        self._build_log(root)
        self._refresh_ports()
        self._on_project_changed(0)

    def _build_row_project(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Проект:"))
        self.cbo_project = QComboBox()
        for p in self._projects:
            self.cbo_project.addItem(p.title, p)
        self.cbo_project.currentIndexChanged.connect(self._on_project_changed)
        row.addWidget(self.cbo_project, 1)
        root.addLayout(row)

    def _build_row_firmware(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Версия:"))
        self.cbo_version = QComboBox()
        self.cbo_version.setEnabled(False)
        self.cbo_version.currentIndexChanged.connect(self._on_version_changed)
        row.addWidget(self.cbo_version, 1)
        self.lbl_firmware = QLabel("загрузка...")
        row.addWidget(self.lbl_firmware)
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

    def _build_row_reboot(self, root: QVBoxLayout) -> None:
        # Опциональный шаг для проектов с pre_flash_http_reboot=True
        # (сейчас — только atomspectra-waterfall-esp32). Скрыт по умолчанию,
        # показывается в _on_project_changed.
        self.row_reboot = QWidget()
        row = QHBoxLayout(self.row_reboot)
        row.setContentsMargins(0, 0, 0, 0)
        self.chk_net_reboot = QCheckBox(
            "Перезагрузить плату по сети перед прошивкой "
            "(сохранить открытый сегмент)")
        self.chk_net_reboot.setChecked(True)
        row.addWidget(self.chk_net_reboot)
        row.addWidget(QLabel("IP платы:"))
        self.txt_ip = QLineEdit()
        self.txt_ip.setPlaceholderText("192.168.x.x")
        self.txt_ip.setMaximumWidth(140)
        settings = QSettings("VibeEngineering-LLC", "esp32-flasher")
        last_ip = settings.value("atomspectra/last_ip", "", type=str)
        if last_ip:
            self.txt_ip.setText(last_ip)
        row.addWidget(self.txt_ip)
        row.addStretch(1)
        root.addWidget(self.row_reboot)
        self.row_reboot.setVisible(False)

    def _build_row_wifi(self, root: QVBoxLayout) -> None:
        # Строка ввода Wi-Fi сети для записи в плату
        self.row_wifi = QWidget()
        row = QHBoxLayout(self.row_wifi)
        row.setContentsMargins(0, 0, 0, 0)
        self.chk_wifi = QCheckBox("Записать домашнюю сеть в плату (без настройки с телефона)")
        self.chk_wifi.setChecked(True)
        row.addWidget(self.chk_wifi)
        row.addWidget(QLabel("Сеть:"))
        self.txt_wifi_ssid = QLineEdit()
        self.txt_wifi_ssid.setPlaceholderText("имя сети Wi-Fi")
        self.txt_wifi_ssid.setMaximumWidth(200)
        settings = QSettings("VibeEngineering-LLC", "esp32-flasher")
        last_ssid = settings.value("wifi/last_ssid", "", type=str)
        if last_ssid:
            self.txt_wifi_ssid.setText(last_ssid)
        row.addWidget(self.txt_wifi_ssid)
        row.addWidget(QLabel("Пароль:"))
        self.txt_wifi_pass = QLineEdit()
        self.txt_wifi_pass.setPlaceholderText("пароль")
        self.txt_wifi_pass.setMaximumWidth(200)
        self.txt_wifi_pass.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(self.txt_wifi_pass)
        row.addStretch(1)
        root.addWidget(self.row_wifi)
        self.row_wifi.setVisible(False)

    def _wifi_nvs_segment(self, prj: Project) -> Project:
        # Добавляет в проект сегмент NVS с Wi-Fi сетью, если нужно
        if prj.wifi_nvs_offset is None:
            return prj
        if not self.chk_wifi.isChecked():
            return prj
        ssid = self.txt_wifi_ssid.text().strip()
        if not ssid:
            return prj
        password = self.txt_wifi_pass.text()
        settings = QSettings("VibeEngineering-LLC", "esp32-flasher")
        settings.setValue("wifi/last_ssid", ssid)
        # Импорт вне try: иначе при неудачном импорте (пакета нет в сборке)
        # имя WifiNvsError не определено и except падает с NameError.
        try:
            from .wifi_nvs import build_wifi_nvs, WifiNvsError
        except Exception as e:
            self._log(f"[wifi] генератор NVS недоступен, сеть не записываю: {e}")
            return prj
        try:
            nvs_path = build_wifi_nvs(ssid, password)
        except WifiNvsError as e:
            self._log(f"[wifi] не записываю сеть: {e}")
            return prj
        self._log(f"[wifi] сеть '{ssid}' будет записана в плату")
        import dataclasses as _dc
        from .projects import FlashSegment
        return _dc.replace(prj, segments=prj.segments + (FlashSegment(prj.wifi_nvs_offset, nvs_path),))

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

    def _on_project_changed(self, _index: int = 0) -> None:
        prj: Project | None = self.cbo_project.currentData()
        if prj is None:
            return
        self._release = None
        self.cbo_version.blockSignals(True)
        self.cbo_version.clear()
        self.cbo_version.blockSignals(False)
        self.cbo_version.setEnabled(False)
        self.btn_install.setEnabled(True)
        self.row_reboot.setVisible(bool(prj.pre_flash_http_reboot))
        self.row_wifi.setVisible(prj.wifi_nvs_offset is not None)
        if prj.pre_flash_http_reboot:
            self.chk_net_reboot.setChecked(bool(self.txt_ip.text().strip()))
        if not prj.github_repo:
            self.lbl_firmware.setText("-")
            return
        self.lbl_firmware.setText("загрузка...")
        if self._fetch_worker is not None:
            # Отцепляем сигналы: если wait не дождётся, отставший done/error
            # старого воркера не должен перезаписать результаты нового проекта
            self._fetch_worker.done.disconnect()
            self._fetch_worker.error.disconnect()
            if self._fetch_worker.isRunning():
                self._fetch_worker.quit()
                self._fetch_worker.wait(1000)
        self._fetch_worker = FetchWorker(prj.github_repo, prj.factory_asset_name)
        self._fetch_worker.done.connect(self._on_fetch_done)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _on_fetch_done(self, releases: object) -> None:
        releases_list: list[FirmwareRelease] = releases  # type: ignore[assignment]
        if not releases_list:
            self._on_fetch_error("пустой список релизов")
            return
        self.cbo_version.blockSignals(True)
        self.cbo_version.clear()
        for i, rel in enumerate(releases_list):
            label = rel.tag + (" (последняя)" if i == 0 else "")
            self.cbo_version.addItem(label, rel)
        self.cbo_version.setCurrentIndex(0)
        self.cbo_version.blockSignals(False)
        self.cbo_version.setEnabled(True)
        self._release = releases_list[0]
        self.lbl_firmware.setText(f"релизов: {len(releases_list)}")
        self.btn_install.setEnabled(True)

    def _on_version_changed(self, _index: int = 0) -> None:
        rel = self.cbo_version.currentData()
        if rel is not None:
            self._release = rel

    def _on_fetch_error(self, msg: str) -> None:
        self._release = None
        self.lbl_firmware.setText("нет соединения")
        self._log(f"[fetch] ошибка: {msg}")
        QMessageBox.critical(
            self, "Нет соединения",
            "Нет соединения с GitHub. Проверьте интернет-подключение.\n"
            "Прошивка недоступна без сети.")
        self.btn_install.setEnabled(False)

    def _on_install(self) -> None:
        self.btn_install.setEnabled(False)
        pi = self.cbo_port.currentData()
        prj: Project | None = self.cbo_project.currentData()
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
        if self._release is None:
            self.btn_install.setEnabled(True)
            QMessageBox.critical(self, "Установка",
                                 "Прошивка не загружена. Проверьте соединение.")
            return
        asset = next(
            (a for a in self._release.assets if a.name == prj.factory_asset_name),
            None,
        )
        if asset is None:
            self.btn_install.setEnabled(True)
            QMessageBox.critical(
                self, "Установка",
                f"Asset '{prj.factory_asset_name}' не найден в релизе {self._release.tag}.")
            return
        self._start_flash(prj, pi.device, asset)

    def _start_flash(self, prj: Project, port: str, asset: object) -> None:
        self.cbo_project.setEnabled(False)
        self.cbo_version.setEnabled(False)
        self.cbo_port.setEnabled(False)
        self.chk_erase.setEnabled(False)
        self.row_reboot.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setFormat("прошивка…")
        erase = self.chk_erase.isChecked()
        mode = "полный сброс + прошивка" if erase else "прошивка"
        self._log(f"=== {mode.capitalize()} «{prj.title}» на {port} ===")
        import dataclasses as _dc
        self.progress.setFormat("загрузка прошивки...")
        tag = self._release.tag if self._release else "?"
        self._log(f"=== Загрузка {prj.factory_asset_name} ({tag}) ===")
        try:
            bin_path = get_cached_or_download(
                prj.github_repo,
                tag,
                asset,  # type: ignore[arg-type]
                progress_cb=self._on_download_progress,
            )
        except Exception as e:
            self._log(f"[download] ошибка: {e}")
            self.progress.setFormat("ошибка загрузки")
            self.btn_install.setEnabled(True)
            self.cbo_project.setEnabled(True)
            self.cbo_version.setEnabled(True)
            self.cbo_port.setEnabled(True)
            self.chk_erase.setEnabled(True)
            self.row_reboot.setEnabled(True)
            QMessageBox.critical(self, "Загрузка", f"Не удалось загрузить прошивку:\n{e}")
            return
        prj = _dc.replace(prj, segments=prj.resolve(bin_path))
        prj = self._wifi_nvs_segment(prj)
        self._active_project = prj
        self._maybe_network_reboot(prj, port, erase)

    def _maybe_network_reboot(self, prj: Project, port: str, erase: bool) -> None:
        ip = self.txt_ip.text().strip() if prj.pre_flash_http_reboot else ""
        do_reboot = (prj.pre_flash_http_reboot
                     and self.chk_net_reboot.isChecked() and bool(ip))
        if not do_reboot:
            self._launch_flash_worker(prj, port, erase)
            return
        settings = QSettings("VibeEngineering-LLC", "esp32-flasher")
        settings.setValue("atomspectra/last_ip", ip)
        self.progress.setRange(0, 0)
        self.progress.setFormat("сетевой ребут платы...")
        self._log(f"=== Сетевой ребут платы {ip} перед прошивкой ===")
        self._reboot_worker = RebootWorker(ip)
        self._reboot_worker.log.connect(self._log)
        self._reboot_worker.done.connect(
            lambda ok, p=prj, prt=port, er=erase: self._on_reboot_done(ok, p, prt, er))
        self._reboot_worker.start()

    def _on_download_progress(self, done: int, total: int) -> None:
        if total > 0:
            pct = int(done * 100 / total)
            self.progress.setValue(pct)
            self.progress.setFormat(f"загрузка {pct}%")

    def _on_phase(self, kind: str) -> None:
        if kind == "erase":
            self.progress.setRange(0, 0)
            self.progress.setFormat("стирание…")
        elif kind == "write":
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("прошивка…")

    def _on_reboot_done(self, ok: bool, prj: Project, port: str, erase: bool) -> None:
        # Best-effort: независимо от ok (плата ответила или нет) прошивку
        # продолжаем — при неудаче лог уже объяснил причину и что дальше
        # будет аппаратный сброс.
        if self._reboot_worker is not None:
            self._reboot_worker.deleteLater()
            self._reboot_worker = None
        self.progress.setRange(0, 100)
        self._launch_flash_worker(prj, port, erase)

    def _launch_flash_worker(self, prj: Project, port: str, erase: bool) -> None:
        self.progress.setValue(0)
        self.progress.setFormat("прошивка...")
        self._worker = FlashWorker(prj, port, erase_first=erase)
        self._worker.log.connect(self._log)
        self._worker.phase.connect(self._on_phase)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool) -> None:
        self.btn_install.setEnabled(True)
        self.cbo_project.setEnabled(True)
        self.cbo_version.setEnabled(True)
        self.cbo_port.setEnabled(True)
        self.chk_erase.setEnabled(True)
        self.row_reboot.setEnabled(True)
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
        if self._reboot_worker is not None and self._reboot_worker.isRunning():
            self._reboot_worker.wait(5000)
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
        if self._fetch_worker is not None:
            self._fetch_worker.done.disconnect()
            self._fetch_worker.error.disconnect()
            if self._fetch_worker.isRunning():
                self._fetch_worker.quit()
                self._fetch_worker.wait(2000)
        super().closeEvent(e)
