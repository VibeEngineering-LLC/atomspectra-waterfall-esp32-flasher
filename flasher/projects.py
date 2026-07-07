"""Реестр проектов прошивки. Пока только atomspectra-waterfall-esp32."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FlashSegment:
    offset: int
    path: Path


@dataclass(frozen=True)
class Project:
    key: str
    title: str
    chip: str
    flash_mode: str
    flash_freq: str
    flash_size: str
    before: str
    after: str
    stub: bool
    segments: tuple[FlashSegment, ...]
    next_steps: str = ""


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "firmware"
    return Path(__file__).resolve().parent.parent / "firmware"


ATOMSPECTRA_NEXT_STEPS = (
    "Дальше:\n"
    "1. Отключи плату от USB и снова подключи (или нажми RESET).\n"
    "2. На телефоне/ноутбуке найди WiFi-сеть «AtomSpectra-Setup» и подключись\n"
    "   (пароль не нужен).\n"
    "3. Откроется страница настройки. Если нет — открой в браузере\n"
    "   http://192.168.4.1/\n"
    "4. Выбери свою домашнюю WiFi 2.4 ГГц, введи пароль, нажми «Сохранить».\n"
    "5. Плата подключится к твоей сети. Открой в браузере:\n"
    "     http://atomspectra.local/\n"
    "   Если не открывается — посмотри IP платы в настройках роутера\n"
    "   (устройство «atomspectra») и открой http://<IP>/."
)


def _load_from_flasher_args(key: str, title: str, next_steps: str = "") -> Project:
    root = _bundle_root() / key
    data = json.loads((root / "flasher_args.json").read_text(encoding="utf-8"))
    files = data["flash_files"]
    segs = tuple(FlashSegment(int(off, 16), root / Path(rel).name)
                 for off, rel in sorted(files.items(), key=lambda kv: int(kv[0], 16)))
    extra = data["extra_esptool_args"]
    fs = data["flash_settings"]
    return Project(key=key, title=title, chip=extra["chip"],
                   flash_mode=fs["flash_mode"], flash_freq=fs["flash_freq"],
                   flash_size=fs["flash_size"], before=extra["before"],
                   after=extra["after"], stub=bool(extra.get("stub", True)),
                   segments=segs, next_steps=next_steps)


def all_projects() -> list[Project]:
    return [_load_from_flasher_args("atomspectra-waterfall-esp32",
                                     "AtomSpectra Waterfall (ESP32-S3)",
                                     ATOMSPECTRA_NEXT_STEPS)]
