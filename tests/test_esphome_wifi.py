import pathlib

import pytest

from flasher.esphome_wifi import (
    build_esphome_wifi_nvs,
    pack_wifi_blob,
    parse_pref_key,
)
from flasher.wifi_nvs import WifiNvsError


def test_pack_wifi_blob_basic():
    blob = pack_wifi_blob("Home-24", "pass1234")
    assert len(blob) == 98
    assert blob[:7] == b"Home-24"
    assert blob[7:33] == b"\x00" * 26
    assert blob[33:41] == b"pass1234"
    assert blob[41:] == b"\x00" * 57


def test_pack_wifi_blob_strips_whitespace_ssid():
    blob = pack_wifi_blob("  Дача ", "x")
    assert blob[:8] == "Дача".encode()
    assert blob[8] == 0


def test_pack_wifi_blob_cyrillic_password():
    blob = pack_wifi_blob("a", "пароль")
    assert blob[33:45] == "пароль".encode("utf-8")


def test_pack_wifi_blob_ssid_max_32_bytes():
    blob = pack_wifi_blob("s" * 32, "p")
    assert blob[32] == 0


def test_pack_wifi_blob_ssid_33_bytes_raises():
    with pytest.raises(WifiNvsError):
        pack_wifi_blob("s" * 33, "p")


def test_pack_wifi_blob_password_max_64_bytes():
    blob = pack_wifi_blob("a", "p" * 64)
    assert blob[97] == 0


def test_pack_wifi_blob_password_65_bytes_raises():
    with pytest.raises(WifiNvsError):
        pack_wifi_blob("a", "p" * 65)


def test_pack_wifi_blob_empty_ssid_raises():
    with pytest.raises(WifiNvsError):
        pack_wifi_blob("", "p")


def test_pack_wifi_blob_whitespace_ssid_raises():
    with pytest.raises(WifiNvsError):
        pack_wifi_blob("   ", "p")


def test_pack_wifi_blob_empty_password_ok():
    blob = pack_wifi_blob("a", "")
    assert blob[33:] == b"\x00" * 65


def test_parse_pref_key_valid():
    assert parse_pref_key('{"esphome_wifi_pref_key": 1418929972}') == 1418929972


@pytest.mark.parametrize(
    "text",
    [
        "не json",
        "[]",
        "{}",
        '{"esphome_wifi_pref_key": "1418929972"}',
        '{"esphome_wifi_pref_key": 0}',
        '{"esphome_wifi_pref_key": -5}',
        '{"esphome_wifi_pref_key": 4294967296}',
        '{"esphome_wifi_pref_key": true}',
        '{"esphome_wifi_pref_key": 1.5}',
    ],
)
def test_parse_pref_key_invalid(text):
    with pytest.raises(WifiNvsError):
        parse_pref_key(text)


def test_parse_pref_key_max_uint32():
    assert parse_pref_key('{"esphome_wifi_pref_key": 4294967295}') == 4294967295


def test_build_esphome_wifi_nvs_basic():
    path = build_esphome_wifi_nvs("Home-24", "pass1234", 1418929972)
    try:
        assert path.exists()
        assert path.stat().st_size == 0x5000
        data = path.read_bytes()
        assert pack_wifi_blob("Home-24", "pass1234") in data
        assert b"esphome\x00" in data
        assert b"1418929972\x00" in data
    finally:
        path.unlink()


def test_build_esphome_wifi_nvs_custom_size():
    path = build_esphome_wifi_nvs("Home-24", "p", 1418929972, size=0x6000)
    try:
        assert path.stat().st_size == 0x6000
    finally:
        path.unlink()


@pytest.mark.parametrize(
    "pref_key",
    [0, True, -1, 2**32],
)
def test_build_esphome_wifi_nvs_invalid_pref_key(pref_key):
    with pytest.raises(WifiNvsError):
        build_esphome_wifi_nvs("Home-24", "p", pref_key)


def test_build_esphome_wifi_nvs_different_pref_keys():
    path1 = build_esphome_wifi_nvs("Home-24", "p", 1)
    path2 = build_esphome_wifi_nvs("Home-24", "p", 2)
    try:
        data2 = path2.read_bytes()
        assert b"1418929972" not in data2
        assert b"2\x00" in data2
    finally:
        path1.unlink()
        path2.unlink()
