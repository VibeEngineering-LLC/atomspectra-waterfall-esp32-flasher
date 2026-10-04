"""Миксин окна флешера для записи NVS-настроек ESPHome (Wi-Fi, MAC)."""
from __future__ import annotations

import dataclasses as _dc
from PySide6.QtCore import QSettings
from .projects import FlashSegment, Project
from .updater import fetch_text_asset


class EsphomeNvsMixin:
    """Миксин для MainWindow: генерация NVS-сегмента ESPHome."""

    def _esphome_wifi_key(self, prj: Project) -> int | None:
        asset = self._esphome_key_asset(prj)
        if asset is None:
            self._log("[wifi] в релизе нет файла ключа, сеть не записываю")
            return None
        try:
            from .esphome_wifi import parse_pref_key
            return parse_pref_key(fetch_text_asset(asset))
        except Exception as e:
            self._log(f"[wifi] не записываю сеть: {e}")
            return None

    def _esphome_nvs_segment(self, prj: Project) -> Project:
        ssid = self.txt_wifi_ssid.text().strip()
        wifi = None

        if prj.supports_esphome_wifi and self.chk_wifi.isChecked() and ssid:
            wifi = (ssid, self.txt_wifi_pass.text())
            QSettings("VibeEngineering-LLC", "esp32-flasher").setValue("wifi/last_ssid", ssid)

        wifi_key = self._esphome_wifi_key(prj) if wifi else None
        mac = self.txt_mac.text().strip() if prj.supports_esphome_mac else ""

        try:
            from .esphome_wifi import build_esphome_nvs, esphome_nvs_entries
            entries = esphome_nvs_entries(wifi, wifi_key, mac, prj.esphome_mac_pref_key)
            if not entries:
                return prj
            nvs_path = build_esphome_nvs(entries, prj.esphome_nvs_size)
        except Exception as e:
            self._log(f"[nvs] не записываю настройки: {e}")
            return prj

        parts = []
        if wifi is not None and wifi_key is not None:
            parts.append(f"Wi-Fi «{ssid}»")
        if mac:
            parts.append("MAC прибора")

        self._log(f"[nvs] в плату будет записано: {', '.join(parts)} (NVS {hex(prj.esphome_nvs_offset)}, {hex(prj.esphome_nvs_size)})")

        return _dc.replace(prj, segments=prj.segments + (FlashSegment(prj.esphome_nvs_offset, nvs_path),))
