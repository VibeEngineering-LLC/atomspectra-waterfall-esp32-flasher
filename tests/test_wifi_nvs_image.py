import struct
import zlib
import io
import pytest

from flasher import wifi_nvs
from flasher.wifi_nvs import build_wifi_nvs_image, WifiNvsError

SSID = "Дом Wi-Fi 5G"
PASS = "Пароль 1 " * 4 + "abc"


def parse_nvs(image: bytes) -> dict[tuple[str, str], tuple[str, object]]:
    """
    Независимый парсер формата NVS ESP-IDF.
    Возвращает словарь: (namespace, key) -> (type_name, value).
    """
    result = {}
    ns_map = {}  # id -> name

    page_size = 4096
    num_pages = len(image) // page_size

    for p in range(num_pages):
        page = image[p * page_size : (p + 1) * page_size]

        # Проверка заголовка страницы
        state = struct.unpack_from("<I", page, 0)[0]
        if state == 0xFFFFFFFF:
            continue

        # Проверка CRC заголовка
        header_crc = struct.unpack_from("<I", page, 28)[0]
        calc_crc = zlib.crc32(page[4:28], 0xFFFFFFFF) & 0xFFFFFFFF
        assert header_crc == calc_crc, f"Page {p} header CRC mismatch"

        # Битовая карта состояния записей
        bitmap = page[32:64]

        # Обход записей
        i = 0
        while i < 126:
            # Извлечение состояния записи (2 бита)
            byte_idx = i // 4
            bit_shift = (i % 4) * 2
            entry_state = (bitmap[byte_idx] >> bit_shift) & 3

            if entry_state != 0b10:
                break

            # Смещение записи в странице
            entry_offset = 64 + i * 32
            entry = page[entry_offset : entry_offset + 32]

            # Проверка CRC записи
            entry_crc = struct.unpack_from("<I", entry, 4)[0]
            calc_entry_crc = zlib.crc32(entry[0:4] + entry[8:32], 0xFFFFFFFF) & 0xFFFFFFFF
            assert entry_crc == calc_entry_crc, f"Entry {i} CRC mismatch"

            ns_idx = entry[0]
            type_id = entry[1]
            span = entry[2]
            key_bytes = entry[8:24]
            data = entry[24:32]

            # Обрезка ключа по NUL
            key_str = key_bytes.split(b'\x00')[0].decode('utf-8')

            # Определение имени неймспейса
            if ns_idx == 0:
                # Это запись неймспейса
                ns_id = data[0]
                ns_name = key_str
                ns_map[ns_id] = ns_name
            else:
                # Обычная запись
                ns_name = ns_map.get(ns_idx, f"ns_{ns_idx}")

                if type_id == 0x01:
                    # u8
                    value = data[0]
                    type_name = "u8"
                elif type_id == 0x21:
                    # string
                    # Длина строки (включая NUL) в data[0:2]
                    str_len = struct.unpack_from("<H", data, 0)[0]
                    # CRC строки в data[4:8]
                    str_crc = struct.unpack_from("<I", data, 4)[0]

                    # Данные строки начинаются после заголовка записи
                    # Заголовок занимает 32 байта (один слот)
                    # Данные занимают span - 1 слотов
                    # Каждый слот 32 байта
                    # Данные начинаются с entry_offset + 32
                    str_data_start = entry_offset + 32
                    # Количество байт данных = (span - 1) * 32
                    total_data_bytes = (span - 1) * 32
                    str_bytes = page[str_data_start : str_data_start + total_data_bytes]

                    # Берем только str_len байт (включая NUL)
                    actual_str_bytes = str_bytes[:str_len]

                    # Проверка CRC строки
                    calc_str_crc = zlib.crc32(actual_str_bytes, 0xFFFFFFFF) & 0xFFFFFFFF
                    assert str_crc == calc_str_crc, f"String CRC mismatch for key {key_str}"

                    # Убираем NUL и декодируем
                    if actual_str_bytes.endswith(b'\x00'):
                        actual_str_bytes = actual_str_bytes[:-1]
                    value = actual_str_bytes.decode('utf-8')
                    type_name = "string"
                else:
                    # Неизвестный тип
                    value = data
                    type_name = "raw"

                result[(ns_name, key_str)] = (type_name, value)

            # Переход к следующей записи
            i += span

    return result


def test_image_size_and_header():
    img = build_wifi_nvs_image(SSID, PASS)
    assert len(img) == 0x6000
    # Успешный парсинг означает, что все CRC корректны
    parse_nvs(img)


def test_ssid_and_pass_strings():
    img = build_wifi_nvs_image(SSID, PASS)
    parsed = parse_nvs(img)
    assert parsed[("wifi", "ssid")] == ("string", SSID)
    assert parsed[("wifi", "pass")] == ("string", PASS)
    assert len(PASS.encode()) == 63


def test_unver_u8_written():
    img = build_wifi_nvs_image(SSID, PASS, extra_u8=(("unver", 1),))
    parsed = parse_nvs(img)
    assert parsed[("wifi", "unver")] == ("u8", 1)


def test_no_unver_by_default():
    img = build_wifi_nvs_image(SSID, PASS)
    parsed = parse_nvs(img)
    assert ("wifi", "unver") not in parsed


def test_empty_password_allowed():
    img = build_wifi_nvs_image(SSID, "")
    parsed = parse_nvs(img)
    assert parsed[("wifi", "pass")] == ("string", "")


def test_ssid_limits():
    # 32 байта - допустимо
    ssid_32 = "a" * 32
    img = build_wifi_nvs_image(ssid_32, PASS)
    parsed = parse_nvs(img)
    assert parsed[("wifi", "ssid")] == ("string", ssid_32)

    # 33 байта - ошибка
    ssid_33 = "a" * 33
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image(ssid_33, PASS)

    # Пустая строка - ошибка
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image("", PASS)

    # Только пробелы - ошибка
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image("   ", PASS)


def test_password_limits():
    # 64 байта - допустимо
    pass_64 = "a" * 64
    img = build_wifi_nvs_image(SSID, pass_64)
    parsed = parse_nvs(img)
    assert parsed[("wifi", "pass")] == ("string", pass_64)

    # 65 байт - ошибка
    pass_65 = "a" * 65
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image(SSID, pass_65)


def test_bad_size_and_extra():
    # Неправильный размер 0x6001
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image(SSID, PASS, size=0x6001)

    # Неправильный размер 0x3000
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image(SSID, PASS, size=0x3000)

    # Запрещенный ключ "ssid" в extra_u8
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image(SSID, PASS, extra_u8=(("ssid", 1),))

    # Слишком длинный ключ (16 байт)
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image(SSID, PASS, extra_u8=(("k" * 16, 1),))

    # Значение вне диапазона u8 (256)
    with pytest.raises(WifiNvsError):
        build_wifi_nvs_image(SSID, PASS, extra_u8=(("unver", 256),))


def test_generator_failure_hides_password(monkeypatch):
    def fake(*a, **k):
        raise RuntimeError(PASS)

    monkeypatch.setattr(wifi_nvs._gen, "write_entry", fake)

    with pytest.raises(WifiNvsError) as ei:
        build_wifi_nvs_image(SSID, PASS)

    assert PASS not in str(ei.value)
    assert "RuntimeError" in str(ei.value)
    assert ei.value.__cause__ is None
    assert ei.value.__suppress_context__ is True


def test_no_output_to_stdout_stderr(capsys):
    build_wifi_nvs_image(SSID, PASS)
    captured = capsys.readouterr()
    assert PASS not in captured.out
    assert PASS not in captured.err
    assert captured.out == ""
    assert captured.err == ""
