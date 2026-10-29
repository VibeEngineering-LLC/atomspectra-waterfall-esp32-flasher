from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from esp_idf_nvs_partition_gen import nvs_partition_gen as _gen


class WifiNvsError(Exception):
    """Ошибка при создании образа NVS для Wi-Fi."""


def build_wifi_nvs_image(
    ssid: str,
    password: str,
    size: int = 0x6000,
    extra_u8: tuple[tuple[str, int], ...] = (),
) -> bytes:
    """
    Создает образ раздела NVS ESP-IDF в памяти.

    Параметры:
        ssid: Имя сети Wi-Fi (не более 32 байт в UTF-8).
        password: Пароль Wi-Fi (не более 64 байт в UTF-8).
        size: Размер раздела в байтах (кратен 0x1000, минимум 0x4000).
        extra_u8: Кортеж дополнительных полей (ключ, значение u8).

    Возвращает:
        Байты образа NVS.

    Исключения:
        WifiNvsError: При некорректных входных данных или ошибке генерации.
    """
    # Валидация SSID
    ssid = ssid.strip()
    if not ssid:
        raise WifiNvsError("SSID не задан")
    if len(ssid.encode("utf-8")) > 32:
        raise WifiNvsError("SSID превышает 32 байта")

    # Валидация пароля
    if len(password.encode("utf-8")) > 64:
        raise WifiNvsError("Пароль превышает 64 байта")

    # Валидация размера раздела
    if not isinstance(size, int) or isinstance(size, bool) or size < 0x4000 or size % 0x1000 != 0:
        raise WifiNvsError("некорректный размер раздела NVS")

    # Валидация дополнительных полей
    for key, value in extra_u8:
        if not isinstance(key, str) or not key or len(key) > 15:
            raise WifiNvsError("некорректное дополнительное поле NVS")
        if key in ("ssid", "pass"):
            raise WifiNvsError("некорректное дополнительное поле NVS")
        if not isinstance(value, int) or isinstance(value, bool) or not (0 <= value <= 255):
            raise WifiNvsError("некорректное дополнительное поле NVS")

    # Генерация образа NVS
    buf = io.BytesIO()
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            # Генератор резервирует одну страницу 4 KiB, поэтому передаем size - 0x1000
            nvs = _gen.nvs_open(buf, size - 0x1000, _gen.Page.VERSION2)
            _gen.write_entry(nvs, "wifi", "namespace", "", None)
            _gen.write_entry(nvs, "ssid", "data", "string", ssid)
            _gen.write_entry(nvs, "pass", "data", "string", password)
            for key, value in extra_u8:
                _gen.write_entry(nvs, key, "data", "u8", str(value))
            _gen.nvs_close(nvs)
    except (Exception, SystemExit) as e:
        # Не включаем str(e) в сообщение, чтобы не раскрыть пароль
        raise WifiNvsError(f"не удалось создать образ NVS: {type(e).__name__}") from None

    data = buf.getvalue()
    if len(data) != size:
        raise WifiNvsError(f"Размер образа NVS {len(data)} не соответствует ожидаемому {size}")

    return bytes(data)
