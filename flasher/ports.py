"""Автодетект COM-портов ESP32.

Фильтр по chip-keyword в описании (CH340/CP210/FTDI/CH343). Блэклист — по keyword
в description (sound/audio/blaster/printer/mouse/wacom), не по номеру порта.
На разных машинах номера COM у SoundBlaster/принтеров/мышей отличаются.
"""
from __future__ import annotations

from dataclasses import dataclass

import serial.tools.list_ports


BLACKLIST_KEYWORDS = ("sound", "audio", "blaster", "printer", "mouse", "wacom")
ESP_KEYWORDS = ("ch340", "ch343", "cp210", "cp2102", "ftdi", "ft232",
                "usb serial", "silicon labs", "wch")


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    is_esp_likely: bool
    is_blacklisted: bool

    @property
    def display(self) -> str:
        tag = " (не ESP?)" if not self.is_esp_likely else ""
        return f"{self.device} — {self.description}{tag}"


def _classify(desc_lower: str) -> tuple[bool, bool]:
    is_esp = any(k in desc_lower for k in ESP_KEYWORDS)
    blk = any(k in desc_lower for k in BLACKLIST_KEYWORDS)
    return is_esp, blk


def list_candidates() -> list[PortInfo]:
    out: list[PortInfo] = []
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "") + " " + (p.manufacturer or "")
        esp, blk = _classify(desc.lower())
        out.append(PortInfo(p.device, p.description or "?", esp, blk))
    out.sort(key=lambda x: (x.is_blacklisted, not x.is_esp_likely, x.device))
    return out


def pick_default(items: list[PortInfo]) -> PortInfo | None:
    for p in items:
        if p.is_esp_likely and not p.is_blacklisted:
            return p
    return None
