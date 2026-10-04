import pytest
from pathlib import Path
import dataclasses

from flasher import esphome_nvs_ui
from flasher.esphome_nvs_ui import EsphomeNvsMixin
from flasher.esphome_wifi import esphome_nvs_entries
from flasher.projects import PROJECT_REGISTRY, FlashSegment
from flasher.wifi_nvs import WifiNvsError

WIFI_KEY = 1111111111
MAC_KEY = 2763962759
MAC = "A0:00:00:00:00:01"


# --- Part 1: esphome_nvs_entries ---

def test_entries_only_mac():
    result = esphome_nvs_entries(None, None, MAC, MAC_KEY)
    assert result == {MAC_KEY: bytes.fromhex("0100000000a00000")}


def test_entries_only_wifi():
    result = esphome_nvs_entries(("net", "secret"), WIFI_KEY, "", None)
    assert set(result.keys()) == {WIFI_KEY}
    val = result[WIFI_KEY]
    assert len(val) == 98
    assert val[:33].rstrip(b"\0") == b"net"
    assert val[33:].rstrip(b"\0") == b"secret"


def test_entries_both():
    result = esphome_nvs_entries(("net", "secret"), WIFI_KEY, MAC, MAC_KEY)
    assert set(result.keys()) == {WIFI_KEY, MAC_KEY}
    assert result[MAC_KEY] == bytes.fromhex("0100000000a00000")
    assert len(result[WIFI_KEY]) == 98


def test_entries_neither():
    result = esphome_nvs_entries(None, None, "", None)
    assert result == {}


def test_entries_wifi_no_key():
    result = esphome_nvs_entries(("net", "secret"), None, "", None)
    assert result == {}


def test_entries_invalid_mac():
    with pytest.raises(WifiNvsError):
        esphome_nvs_entries(None, None, "ZZ", MAC_KEY)


def test_entries_mac_no_key():
    with pytest.raises(WifiNvsError):
        esphome_nvs_entries(None, None, MAC, None)


def test_entries_whitespace_mac():
    result = esphome_nvs_entries(None, None, "   ", None)
    assert result == {}


# --- Part 2: Registry ---

def test_registry_atomfast():
    prj = PROJECT_REGISTRY["atomfast-gateway-s3"]
    assert prj.esphome_mac_pref_key == 2763962759
    assert prj.supports_esphome_mac is True
    assert prj.esphome_nvs_offset is not None


# --- Part 3: EsphomeNvsMixin ---

class FakeText:
    def __init__(self, value=""):
        self._value = value

    def text(self):
        return self._value


class FakeCheck:
    def __init__(self, checked=False):
        self._checked = checked

    def isChecked(self):
        return self._checked


class FakeSettings:
    saved = []

    def __init__(self, *a, **k):
        pass

    def setValue(self, key, value):
        FakeSettings.saved.append((key, value))


class FakeWindow(EsphomeNvsMixin):
    def __init__(self, ssid="", password="", mac="", wifi_on=False, asset=None):
        self.txt_wifi_ssid = FakeText(ssid)
        self.txt_wifi_pass = FakeText(password)
        self.txt_mac = FakeText(mac)
        self.chk_wifi = FakeCheck(wifi_on)
        self.logs = []
        self._asset = asset

    def _log(self, msg):
        self.logs.append(msg)

    def _esphome_key_asset(self, prj):
        return self._asset


def get_prj():
    return PROJECT_REGISTRY["atomfast-gateway-s3"]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(esphome_nvs_ui, "QSettings", FakeSettings)
    FakeSettings.saved.clear()
    monkeypatch.setattr(
        esphome_nvs_ui,
        "fetch_text_asset",
        lambda asset: '{"esphome_wifi_pref_key": 1111111111}'
    )
    yield


def test_mixin_mac_only(env):
    prj = get_prj()
    w = FakeWindow(mac=MAC, wifi_on=False)
    result = w._esphome_nvs_segment(prj)

    assert len(result.segments) == len(prj.segments) + 1
    last_seg = result.segments[-1]
    assert isinstance(last_seg, FlashSegment)
    assert last_seg.offset == prj.esphome_nvs_offset

    # path exists and size matches
    p = Path(last_seg.path)
    assert p.exists()
    assert p.stat().st_size == prj.esphome_nvs_size

    # exactly one segment with that offset
    count = sum(1 for s in result.segments if s.offset == prj.esphome_nvs_offset)
    assert count == 1

    # original unchanged
    assert len(prj.segments) == len(get_prj().segments)
    assert result is not prj

    # log check
    log_str = "\n".join(w.logs)
    assert any(line.startswith("[nvs] в плату будет записано") for line in w.logs)
    assert "MAC прибора" in log_str


def test_mixin_empty(env):
    prj = get_prj()
    w = FakeWindow(mac="", wifi_on=False)
    result = w._esphome_nvs_segment(prj)
    assert result is prj
    assert w.logs == []


def test_mixin_invalid_mac(env):
    prj = get_prj()
    w = FakeWindow(mac="not-a-mac", wifi_on=False)
    result = w._esphome_nvs_segment(prj)
    assert result is prj
    assert any(line.startswith("[nvs]") for line in w.logs)
    assert len(result.segments) == len(prj.segments)


def test_mixin_secrets_not_in_logs(env):
    prj = get_prj()
    sentinel = object()
    w = FakeWindow(
        ssid="MyNet",
        password="TopSecretPass123",
        mac=MAC,
        wifi_on=True,
        asset=sentinel
    )
    result = w._esphome_nvs_segment(prj)

    log_str = "\n".join(w.logs)
    assert MAC not in log_str
    assert MAC.lower() not in log_str
    assert "a000" not in log_str
    assert "TopSecretPass123" not in log_str

    assert len(result.segments) == len(prj.segments) + 1
    assert FakeSettings.saved == [("wifi/last_ssid", "MyNet")]


def test_mixin_secrets_failure_path(env):
    prj = get_prj()
    sentinel = object()
    w = FakeWindow(
        ssid="MyNet",
        password="TopSecretPass123",
        mac="A0:00:00:00:00:ZZ",
        wifi_on=True,
        asset=sentinel
    )
    result = w._esphome_nvs_segment(prj)

    log_str = "\n".join(w.logs)
    assert "A0:00:00:00:00:ZZ" not in log_str
    assert "TopSecretPass123" not in log_str


def test_mixin_wifi_no_asset(env):
    prj = get_prj()
    w = FakeWindow(ssid="MyNet", mac="", wifi_on=True, asset=None)
    result = w._esphome_nvs_segment(prj)
    assert result is prj
    assert any(line.startswith("[wifi]") for line in w.logs)


def test_mixin_wifi_and_mac(env):
    prj = get_prj()
    sentinel = object()
    w = FakeWindow(
        ssid="MyNet",
        password="pass",
        mac=MAC,
        wifi_on=True,
        asset=sentinel
    )
    result = w._esphome_nvs_segment(prj)
    assert len(result.segments) == len(prj.segments) + 1
    log_str = "\n".join(w.logs)
    assert "Wi-Fi" in log_str
    assert "MAC прибора" in log_str


def test_mixin_wifi_checked_empty_ssid(env):
    prj = get_prj()
    w = FakeWindow(ssid="", mac="", wifi_on=True)
    result = w._esphome_nvs_segment(prj)
    assert result is prj
    assert FakeSettings.saved == []
