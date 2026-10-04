import pathlib

import pytest

from flasher.esphome_wifi import (
    build_esphome_nvs,
    build_esphome_wifi_nvs,
    pack_mac_blob,
    pack_wifi_blob,
    parse_mac,
)
from flasher.wifi_nvs import WifiNvsError


def test_parse_mac_standard():
    assert parse_mac("A0:00:00:00:00:01") == 0xA00000000001


def test_parse_mac_lowercase_spaces_hyphens():
    assert parse_mac("  a0-00-00-00-00-01 ") == 0xA00000000001


def test_pack_mac_blob_a0():
    assert pack_mac_blob("A0:00:00:00:00:01") == bytes([0x01, 0, 0, 0, 0, 0xA0, 0, 0])


def test_pack_mac_blob_123456789ABC():
    assert pack_mac_blob("12:34:56:78:9A:BC") == bytes.fromhex("bc9a785634120000")


@pytest.mark.parametrize(
    "bad_mac",
    [
        "",
        "A0:00:00:00:00",
        "A0:00:00:00:00:01:02",
        "G0:00:00:00:00:01",
        "A000:00:00:00:01",
        "A0.00.00.00.00.01",
        "00:00:00:00:00:00",
    ],
)
def test_parse_mac_invalid(bad_mac):
    with pytest.raises(WifiNvsError):
        parse_mac(bad_mac)


def test_build_esphome_nvs_mac_only():
    path = build_esphome_nvs({2763962759: pack_mac_blob("12:34:56:78:9A:BC")}, size=0x5000)
    try:
        assert path.exists()
        assert path.stat().st_size == 0x5000
        data = path.read_bytes()
        assert bytes.fromhex("bc9a785634120000") in data
        assert b"esphome\x00" in data
        assert b"2763962759\x00" in data
    finally:
        path.unlink()


def test_build_esphome_nvs_wifi_and_mac():
    entries = {
        1418929972: pack_wifi_blob("Home-24", "pass1234"),
        2763962759: pack_mac_blob("12:34:56:78:9A:BC"),
    }
    path = build_esphome_nvs(entries, size=0x6000)
    try:
        assert path.stat().st_size == 0x6000
        data = path.read_bytes()
        assert pack_wifi_blob("Home-24", "pass1234") in data
        assert pack_mac_blob("12:34:56:78:9A:BC") in data
        assert b"1418929972\x00" in data
        assert b"2763962759\x00" in data
    finally:
        path.unlink()


def test_build_esphome_nvs_empty_raises():
    with pytest.raises(WifiNvsError):
        build_esphome_nvs({})


@pytest.mark.parametrize("bad_key", [0, True, 2**32])
def test_build_esphome_nvs_invalid_key_raises(bad_key):
    with pytest.raises(WifiNvsError):
        build_esphome_nvs({bad_key: b"x"})


def test_build_esphome_nvs_empty_value_raises():
    with pytest.raises(WifiNvsError):
        build_esphome_nvs({5: b""})


def test_build_esphome_wifi_nvs_compat():
    path = build_esphome_wifi_nvs("Home-24", "p", 1418929972)
    try:
        assert path.stat().st_size == 0x5000
        data = path.read_bytes()
        assert pack_wifi_blob("Home-24", "p") in data
    finally:
        path.unlink()


def test_build_esphome_wifi_nvs_invalid_key_raises():
    with pytest.raises(WifiNvsError):
        build_esphome_wifi_nvs("Home-24", "p", 0)
