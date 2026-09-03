"""
Генерирует NVS-раздел для ESP32 с учётными данными Wi-Fi.
Использует namespace 'wifi' и ключи 'ssid', 'pass'.
Созданный образ можно прошить в раздел NVS для автоматического подключения.
"""
from __future__ import annotations
import csv
import io
import tempfile
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from esp_idf_nvs_partition_gen.nvs_partition_gen import generate


class WifiNvsError(Exception):
    pass


def build_wifi_nvs(ssid: str, password: str, size: int = 0x6000) -> Path:
    ssid = ssid.strip()
    if not ssid:
        raise WifiNvsError("SSID не задан")
    if len(ssid.encode('utf-8')) > 32:
        raise WifiNvsError("SSID превышает 32 байта")
    if len(password.encode('utf-8')) > 64:
        raise WifiNvsError("Пароль превышает 64 байта")

    tmp_dir = tempfile.mkdtemp(prefix="wifi_nvs_")
    csv_path = os.path.join(tmp_dir, "wifi.csv")
    bin_path = os.path.join(tmp_dir, "wifi_nvs.bin")

    try:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['key', 'type', 'encoding', 'value'])
            writer.writerow(['wifi', 'namespace', '', ''])
            writer.writerow(['ssid', 'data', 'string', ssid])
            writer.writerow(['pass', 'data', 'string', password])

        args = SimpleNamespace(
            input=csv_path,
            output=bin_path,
            size=hex(size),
            version=2,
            outdir=tmp_dir
        )

        try:
            # Пакет-генератор печатает служебные сообщения в stdout, а сборка
            # GUI идёт с console=False — консоли нет, вывод подавляем.
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                generate(args)
        except Exception as e:
            raise WifiNvsError(f"не удалось создать образ NVS: {e}") from e

        if not os.path.exists(bin_path):
            raise WifiNvsError("Не удалось создать файл NVS")

        actual_size = os.path.getsize(bin_path)
        if actual_size != size:
            raise WifiNvsError(f"Размер NVS-файла {actual_size} не соответствует ожидаемому {size}")

        return Path(bin_path)

    finally:
        try:
            os.remove(csv_path)
        except Exception:
            pass
