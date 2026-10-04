"""Модуль записи Wi-Fi и MAC-адреса прибора в NVS-раздел ESPHome.

Генерирует бинарный образ NVS-раздела с namespace `esphome`,
в который записываются учётные данные Wi-Fi и/или MAC BLE-прибора.
Используется при флешинге ESP32 для предварительной настройки прошивки.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import re
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace

from esp_idf_nvs_partition_gen.nvs_partition_gen import generate
from flasher.wifi_nvs import WifiNvsError

_MAC_RE = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")


def pack_wifi_blob(ssid: str, password: str) -> bytes:
    """Упаковывает SSID и пароль в 98-байтовый blob для NVS."""
    ssid = ssid.strip()
    if not ssid:
        raise WifiNvsError("SSID не задан")
    s = ssid.encode("utf-8")
    if len(s) > 32:
        raise WifiNvsError("SSID превышает 32 байта")
    p = password.encode("utf-8")
    if len(p) > 64:
        raise WifiNvsError("Пароль превышает 64 байта")
    return s.ljust(33, b"\x00") + p.ljust(65, b"\x00")


def parse_mac(text: str) -> int:
    """Разбирает строку MAC-адреса в беззнаковое 64-битное число."""
    t = text.strip().upper().replace("-", ":")
    if not _MAC_RE.match(t):
        raise WifiNvsError("MAC должен быть в формате AA:BB:CC:DD:EE:FF")
    v = int(t.replace(":", ""), 16)
    if v == 0:
        raise WifiNvsError("MAC не может быть нулевым")
    return v


def pack_mac_blob(mac: str) -> bytes:
    """Упаковывает MAC-адрес в 8-байтовый blob little-endian."""
    return parse_mac(mac).to_bytes(8, "little")


def parse_pref_key(text: str) -> int:
    """Извлекает ключ Wi-Fi из JSON-строки релиза."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise WifiNvsError("файл ключа Wi-Fi повреждён") from None
    if not isinstance(data, dict):
        raise WifiNvsError("в файле нет корректного ключа Wi-Fi")
    v = data.get("esphome_wifi_pref_key")
    if isinstance(v, bool) or not isinstance(v, int) or not (0 < v <= 0xFFFFFFFF):
        raise WifiNvsError("в файле нет корректного ключа Wi-Fi")
    return v


def _check_key(k: int) -> None:
    """Проверяет корректность ключа NVS."""
    if isinstance(k, bool) or not isinstance(k, int) or not (0 < k <= 0xFFFFFFFF):
        raise WifiNvsError("некорректный ключ NVS")


def build_esphome_nvs(entries: dict[int, bytes], size: int = 0x5000) -> pathlib.Path:
    """Создаёт бинарный образ NVS-раздела ESPHome из заданных записей."""
    if not entries:
        raise WifiNvsError("нечего записывать в NVS")
    for k, v in entries.items():
        _check_key(k)
        if not isinstance(v, bytes) or len(v) < 1:
            raise WifiNvsError("пустое значение NVS")

    tmp_dir = tempfile.mkdtemp(prefix="esphome_nvs_")
    csv_path = pathlib.Path(tmp_dir) / "nvs.csv"
    bin_path = pathlib.Path(tmp_dir) / "esphome_nvs.bin"

    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["key", "type", "encoding", "value"])
            w.writerow(["esphome", "namespace", "", ""])
            for k in sorted(entries):
                w.writerow([str(k), "data", "hex2bin", entries[k].hex()])

        args = SimpleNamespace(
            input=str(csv_path),
            output=str(bin_path),
            size=hex(size),
            version=2,
            outdir=tmp_dir,
        )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                generate(args)
            except Exception as e:
                raise WifiNvsError(f"не удалось создать образ NVS: {e}") from e

        if not bin_path.exists():
            raise WifiNvsError("Не удалось создать файл NVS")
        actual = bin_path.stat().st_size
        if actual != size:
            raise WifiNvsError(f"Размер NVS-файла {actual} не соответствует ожидаемому {size}")
        return bin_path
    finally:
        csv_path.unlink(missing_ok=True)


def esphome_nvs_entries(wifi: tuple[str, str] | None, wifi_key: int | None,
                        mac: str, mac_key: int | None) -> dict[int, bytes]:
    """Собирает записи NVS: Wi-Fi (если есть пара и ключ) и MAC (если не пуст)."""
    entries: dict[int, bytes] = {}
    if wifi is not None and wifi_key is not None:
        _check_key(wifi_key)
        entries[wifi_key] = pack_wifi_blob(wifi[0], wifi[1])
    if mac.strip():
        if mac_key is None:
            raise WifiNvsError("проект не поддерживает запись MAC")
        _check_key(mac_key)
        entries[mac_key] = pack_mac_blob(mac)
    return entries


def build_esphome_wifi_nvs(ssid: str, password: str, pref_key: int, size: int = 0x5000) -> pathlib.Path:
    """Создаёт NVS-образ только с Wi-Fi-данными (совместимость)."""
    try:
        _check_key(pref_key)
    except WifiNvsError:
        raise WifiNvsError("в файле нет корректного ключа Wi-Fi") from None
    return build_esphome_nvs({pref_key: pack_wifi_blob(ssid, password)}, size)
