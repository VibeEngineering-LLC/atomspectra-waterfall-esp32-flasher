import pytest
import flasher.updater as updater
from flasher.projects import PROJECT_REGISTRY


class FakeResp:
    def __init__(self, payload=None, text=None, status=200):
        self.status_code = status
        self.ok = status < 400
        self.reason = "OK"
        self.content = text.encode("utf-8") if text is not None else b""
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise updater.requests.HTTPError(f"{self.status_code} {self.reason}")


def asset(name, url=None):
    return {
        "name": name,
        "browser_download_url": url or f"https://example.test/dl/{name}",
        "size": 100,
    }


def release(tag, names):
    return {
        "tag_name": tag,
        "body": "",
        "assets": [asset(n) for n in names],
    }


H1 = "a" * 64
H2 = "b" * 64


@pytest.fixture
def fake_github(monkeypatch):
    class FakeGithub:
        def __init__(self):
            self.releases = []
            self.sums = {}
            self.call_count = 0

    fg = FakeGithub()

    def fake_get(url, *a, **k):
        fg.call_count += 1
        if "api.github.com" in url:
            return FakeResp(payload=fg.releases)
        if url in fg.sums:
            return FakeResp(text=fg.sums[url])
        return FakeResp(status=404)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    return fg


def test_registry_entry_atomfast_idf():
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]
    assert p.chip == "esp32s3"
    assert p.github_repo == "VibeEngineering-LLC/atomfast-esp32"
    assert p.factory_asset_name == "atomfast_gw.factory.bin"
    assert p.segments_from_factory is True
    assert p.wifi_nvs_offset == 0x9000
    assert p.wifi_nvs_size == 0x6000
    assert p.wifi_nvs_extra_u8 == (("unver", 1),)
    assert p.sums_asset_name == "SHA256SUMS.txt"


def test_registry_radex_unchanged():
    r = PROJECT_REGISTRY["radex-gateway"]
    assert r.wifi_nvs_offset == 0x9000
    assert r.wifi_nvs_extra_u8 == ()
    assert r.sums_asset_name == ""

    s3 = PROJECT_REGISTRY["atomfast-gateway-s3"]
    assert s3.factory_asset_name == "atomfast-gw-s3.factory.bin"
    assert s3.wifi_nvs_offset is None


def test_parse_sha256sums_formats():
    text = "\n".join([
        f"{H1}  atomfast_gw.factory.bin",
        f"{H2.upper()} *atomfast_gw.bin",
        "# x",
        "",
        "zzz file",
        "a" * 63 + "  bad.bin",
    ])
    result = updater.parse_sha256sums(text)
    assert result == {
        "atomfast_gw.factory.bin": H1,
        "atomfast_gw.bin": H2,
    }


def test_fetch_filters_esphome_release(fake_github):
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]

    # ESPHome release with distinct sums URL
    esphome_release = {
        "tag_name": "v0.9.2-s3",
        "body": "",
        "assets": [
            asset("atomfast-gw-s3.factory.bin"),
            asset("atomfast-gw-s3.ota.bin"),
            asset("atomfast-gw-s3.wifi-key.json"),
            asset("SHA256SUMS.txt", url="https://example.test/esphome/SHA256SUMS.txt"),
        ],
    }

    # IDF release
    idf_release = {
        "tag_name": "v0.2.0",
        "body": "",
        "assets": [
            asset("atomfast_gw.factory.bin"),
            asset("atomfast_gw.bin"),
            asset("SHA256SUMS.txt", url="https://example.test/idf/SHA256SUMS.txt"),
        ],
    }

    fake_github.releases = [esphome_release, idf_release]
    # список ESPHome-релиза нарочно содержит и имя образа IDF: отсев должен идти по
    # ассету релиза, а не только по списку сумм
    fake_github.sums["https://example.test/esphome/SHA256SUMS.txt"] = (
        f"{H1}  atomfast-gw-s3.factory.bin\n{H1}  atomfast_gw.factory.bin")
    fake_github.sums["https://example.test/idf/SHA256SUMS.txt"] = f"{H1}  atomfast_gw.factory.bin"

    result = updater.fetch_releases(p.github_repo, p.factory_asset_name, p.sums_asset_name)
    assert [r.tag for r in result] == ["v0.2.0"]


def test_sha_taken_from_sums(fake_github):
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]

    rel = {
        "tag_name": "v0.2.0",
        "body": "",
        "assets": [
            asset("atomfast_gw.factory.bin"),
            asset("atomfast_gw.bin"),
            asset("SHA256SUMS.txt", url="https://example.test/idf/SHA256SUMS.txt"),
        ],
    }

    fake_github.releases = [rel]
    fake_github.sums["https://example.test/idf/SHA256SUMS.txt"] = f"{H1}  atomfast_gw.factory.bin\n{H2}  atomfast_gw.bin"

    result = updater.fetch_releases(p.github_repo, p.factory_asset_name, p.sums_asset_name)
    assert len(result) == 1
    assets = {a.name: a for a in result[0].assets}
    assert assets["atomfast_gw.factory.bin"].sha256 == H1
    assert assets["atomfast_gw.bin"].sha256 == H2


def test_release_without_sums_asset_is_dropped(fake_github):
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]

    rel = {
        "tag_name": "v0.3.0",
        "body": "",
        "assets": [
            asset("atomfast_gw.factory.bin"),
        ],
    }

    fake_github.releases = [rel]

    with pytest.raises(updater.ReleaseNotFoundError):
        updater.fetch_releases(p.github_repo, p.factory_asset_name, p.sums_asset_name)


def test_release_with_sums_missing_entry_is_dropped(fake_github):
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]

    rel = {
        "tag_name": "v0.3.0",
        "body": "",
        "assets": [
            asset("atomfast_gw.factory.bin"),
            asset("SHA256SUMS.txt", url="https://example.test/idf/SHA256SUMS.txt"),
        ],
    }

    fake_github.releases = [rel]
    fake_github.sums["https://example.test/idf/SHA256SUMS.txt"] = f"{H1}  other.bin"

    with pytest.raises(updater.ReleaseNotFoundError):
        updater.fetch_releases(p.github_repo, p.factory_asset_name, p.sums_asset_name)


def test_without_sums_asset_name_behaviour_unchanged(fake_github):
    rel = {
        "tag_name": "v1.0.0",
        "body": "",
        "assets": [
            asset("firmware.factory.bin"),
        ],
    }

    fake_github.releases = [rel]

    result = updater.fetch_releases("VibeEngineering-LLC/radex-esp32", "firmware.factory.bin")
    assert len(result) == 1
    assert result[0].tag == "v1.0.0"
    assert result[0].assets[0].sha256 is None
    assert fake_github.call_count == 1


def test_sums_download_error_propagates(fake_github):
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]

    rel = {
        "tag_name": "v0.2.0",
        "body": "",
        "assets": [
            asset("atomfast_gw.factory.bin"),
            asset("SHA256SUMS.txt", url="https://example.test/idf/SHA256SUMS.txt"),
        ],
    }

    fake_github.releases = [rel]
    # sums URL not in fake_github.sums -> FakeResp(status=404) -> raise_for_status raises HTTPError

    with pytest.raises(updater.NetworkError):
        updater.fetch_releases(p.github_repo, p.factory_asset_name, p.sums_asset_name)


def test_update_mode_app_only_keeps_nvs():
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]
    assert p.supports_update is True
    assert p.app_asset_name == "atomfast_gw.bin"
    assert p.app_offset == 0x20000
    # приложение лежит после nvs (0x9000+0x6000), значит заливка его не затирает
    assert p.app_offset >= p.wifi_nvs_offset + p.wifi_nvs_size


def test_no_board_password_in_hints():
    p = PROJECT_REGISTRY["atomfast-gateway-idf"]
    text = p.next_steps.lower()
    assert "admin" not in text and "пароль платы" not in text
    assert "без пароля" in text
