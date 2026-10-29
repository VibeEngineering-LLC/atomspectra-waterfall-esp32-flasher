import dataclasses
import os
import tempfile
import pytest
from pathlib import Path
import flasher.flasher as flasher_mod
from flasher.projects import FlashSegment, PROJECT_REGISTRY
from flasher.wifi_flash import splice_region, wipe_file, wipe_secret_segments, apply_wifi_nvs, prepare_wifi_nvs
from flasher.wifi_nvs import WifiNvsError, build_wifi_nvs_image

SSID = "Дом Wi-Fi 5G"
PASS = "Пароль 1 " * 4 + "abc"
FACTORY_SIZE = 0x30000
FACTORY_CONTENT = bytes((i * 7 + 3) & 0xFF for i in range(FACTORY_SIZE))
IMG = build_wifi_nvs_image(SSID, PASS)


def leftover_files(root: Path) -> list[Path]:
    """Рекурсивно собирает все файлы под корнем."""
    return [p for p in root.rglob("*") if p.is_file()]


@pytest.fixture
def tmp_secret_dir(tmp_path, monkeypatch):
    """Создаёт каталог для секретных временных файлов и перенаправляет tempfile.tempdir."""
    d = tmp_path / "sys_tmp"
    d.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(d))
    return d


@pytest.fixture
def factory(tmp_path):
    """Создаёт файл фабричного образа."""
    fw_dir = tmp_path / "fw"
    fw_dir.mkdir()
    p = fw_dir / "atomfast_gw.factory.bin"
    p.write_bytes(FACTORY_CONTENT)
    return p


def idf_project(factory):
    """Возвращает проект atomfast-gateway-idf с разрешёнными сегментами."""
    prj = PROJECT_REGISTRY["atomfast-gateway-idf"]
    return dataclasses.replace(prj, segments=prj.resolve(factory))


class FakeEsptool:
    """Имитация esptool для тестов."""
    def __init__(self, fail=False, reader=None):
        self.fail = fail
        self.reader = reader
        self.last_argv = None

    def main(self, argv):
        self.last_argv = argv
        if self.reader:
            self.reader(argv)
        if self.fail:
            raise SystemExit(2)
        return 0


def test_splice_region_pastes_at_offset(factory, tmp_secret_dir):
    """Проверяет вставку данных в указанный оффсет."""
    orig = factory.read_bytes()
    out = splice_region(factory, 0x9000, IMG)
    data = out.read_bytes()
    assert len(data) == FACTORY_SIZE
    assert data[0x9000:0x9000 + len(IMG)] == IMG
    assert data[:0x9000] == orig[:0x9000]
    assert data[0x9000 + len(IMG):] == orig[0x9000 + len(IMG):]
    assert factory.read_bytes() == orig
    assert out.parent.parent == tmp_secret_dir
    assert out.parent.name.startswith("wifi_nvs_")


def test_splice_region_rejects_short_factory(tmp_path, tmp_secret_dir):
    """Проверяет отклонение слишком короткого файла."""
    short_file = tmp_path / "short.bin"
    short_file.write_bytes(b"\x00" * (0x9000 + 0x5FFF))
    with pytest.raises(WifiNvsError):
        splice_region(short_file, 0x9000, IMG)
    
    exact_file = tmp_path / "exact.bin"
    exact_file.write_bytes(b"\x00" * (0x9000 + 0x6000))
    out = splice_region(exact_file, 0x9000, IMG)
    assert out.exists()
    wipe_file(out)  # принятая копия - не утечка отказа, убираем до проверки

    assert leftover_files(tmp_secret_dir) == []
    assert list(tmp_secret_dir.iterdir()) == []


def test_apply_replaces_covering_segment(factory, tmp_secret_dir):
    """Проверяет замену сегмента, покрывающего область NVS."""
    segs = apply_wifi_nvs((FlashSegment(0, factory),), 0x9000, IMG)
    assert len(segs) == 1
    assert segs[0].offset == 0
    assert segs[0].secret is True
    assert segs[0].path != factory
    assert segs[0].path.stat().st_size == FACTORY_SIZE


def test_apply_appends_when_not_covered(tmp_path, tmp_secret_dir):
    """Проверяет добавление сегмента NVS, если нет пересечения."""
    small = tmp_path / "app.bin"
    small.write_bytes(b"\x00" * 0x1000)
    segs = apply_wifi_nvs((FlashSegment(0x20000, small),), 0x9000, IMG)
    assert len(segs) == 2
    assert segs[0] == FlashSegment(0x20000, small)
    assert segs[1].offset == 0x9000
    assert segs[1].secret is True
    assert segs[1].path.read_bytes() == IMG


def test_apply_rejects_partial_overlap(tmp_path, tmp_secret_dir):
    """Проверяет отклонение частичного пересечения."""
    partial_file = tmp_path / "partial.bin"
    partial_file.write_bytes(b"\x00" * 0x9800)
    with pytest.raises(WifiNvsError):
        apply_wifi_nvs((FlashSegment(0, partial_file),), 0x9000, IMG)
    
    file1 = tmp_path / "f1.bin"
    file1.write_bytes(b"\x00" * 0x9800)
    file2 = tmp_path / "f2.bin"
    file2.write_bytes(b"\x00" * 0x1000)
    with pytest.raises(WifiNvsError):
        apply_wifi_nvs((FlashSegment(0, file1), FlashSegment(0xA000, file2)), 0x9000, IMG)
    
    assert leftover_files(tmp_secret_dir) == []


def test_wipe_file_removes_file_and_dir(tmp_secret_dir):
    """Проверяет удаление файла и родительского каталога."""
    d = Path(tempfile.mkdtemp(prefix="wifi_nvs_"))
    f = d / "x.bin"
    f.write_bytes(b"S" * 5000)
    assert wipe_file(f) is True
    assert not f.exists()
    assert not d.exists()
    assert wipe_file(f) is True
    
    other_dir = tmp_secret_dir / "other"
    other_dir.mkdir()
    y = other_dir / "y.bin"
    y.write_bytes(b"Y" * 100)
    wipe_file(y)
    assert not y.exists()
    assert other_dir.exists()


def test_wipe_zeroes_before_unlink(tmp_secret_dir, monkeypatch):
    """Проверяет обнуление содержимого перед удалением."""
    d = Path(tempfile.mkdtemp(prefix="wifi_nvs_"))
    f = d / "z.bin"
    content = b"SECRET" * 1000
    f.write_bytes(content)
    
    seen = []
    original_unlink = Path.unlink
    
    def fake_unlink(self, *args, **kwargs):
        seen.append(self.read_bytes())
        return original_unlink(self, *args, **kwargs)
    
    monkeypatch.setattr(Path, "unlink", fake_unlink)
    wipe_file(f)
    assert seen == [b"\x00" * len(content)]


def test_prepare_logs_ssid_but_not_password(factory, tmp_secret_dir, capsys):
    """Проверяет, что SSID логируется, а пароль — нет."""
    lines = []
    prj = prepare_wifi_nvs(idf_project(factory), SSID, PASS, lines.append)
    assert any(SSID in l for l in lines)
    assert all(PASS not in l for l in lines)
    out = capsys.readouterr()
    assert PASS not in out.out
    assert PASS not in out.err
    assert len(prj.segments) == 1
    assert prj.segments[0].secret


def test_prepare_failure_returns_project_unchanged(factory, tmp_secret_dir):
    """Проверяет возврат неизменённого проекта при ошибке."""
    prj = idf_project(factory)
    log1 = []
    result1 = prepare_wifi_nvs(prj, "x" * 33, PASS, log1.append)
    assert result1 is prj
    assert any("[wifi]" in l for l in log1)
    assert all(PASS not in l for l in log1)
    
    log2 = []
    result2 = prepare_wifi_nvs(prj, "", PASS, log2.append)
    assert result2 is prj
    assert len(log2) == 0
    
    radon_prj = PROJECT_REGISTRY["radon-gateway"]
    radon_prj = dataclasses.replace(radon_prj, segments=radon_prj.resolve(factory))
    log3 = []
    result3 = prepare_wifi_nvs(radon_prj, SSID, PASS, log3.append)
    assert result3 is radon_prj


def test_flash_argv_single_segment_without_overlap(factory, tmp_secret_dir, monkeypatch):
    """Проверяет формирование argv и отсутствие пересечений."""
    prj = prepare_wifi_nvs(idf_project(factory), SSID, PASS, lambda s: None)
    argv = flasher_mod._build_argv(prj, "COM_TEST", 921600)
    
    idx = argv.index("write_flash")
    pairs = []
    i = idx + 1
    while i < len(argv):
        if argv[i].startswith("--"):
            i += 2
        else:
            offset_str = argv[i]
            path_str = argv[i + 1]
            pairs.append((int(offset_str, 16), Path(path_str)))
            i += 2
    
    assert len(pairs) == 1
    assert pairs[0][0] == 0
    assert pairs[0][1].stat().st_size == FACTORY_SIZE
    
    def check_overlap(pairs):
        sorted_pairs = sorted(pairs, key=lambda x: x[0])
        for i in range(1, len(sorted_pairs)):
            prev_off, prev_path = sorted_pairs[i - 1]
            curr_off, curr_path = sorted_pairs[i]
            prev_size = prev_path.stat().st_size
            assert curr_off >= prev_off + prev_size
    
    check_overlap(pairs)
    
    radex_prj = PROJECT_REGISTRY["radex-gateway"]
    radex_prj = dataclasses.replace(radex_prj, segments=radex_prj.resolve(factory))
    radex_prj = prepare_wifi_nvs(radex_prj, SSID, PASS, lambda s: None)
    argv2 = flasher_mod._build_argv(radex_prj, "COM_TEST", 921600)
    idx2 = argv2.index("write_flash")
    pairs2 = []
    i = idx2 + 1
    while i < len(argv2):
        if argv2[i].startswith("--"):
            i += 2
        else:
            offset_str = argv2[i]
            path_str = argv2[i + 1]
            pairs2.append((int(offset_str, 16), Path(path_str)))
            i += 2
    check_overlap(pairs2)


def test_flash_wipes_secret_files_on_success_and_failure(factory, tmp_secret_dir, tmp_path, monkeypatch):
    """Проверяет очистку секретных файлов при успехе и ошибке."""
    for fail in (False, True):
        fake = FakeEsptool(fail=fail)
        monkeypatch.setattr(flasher_mod, "esptool", fake)
        prj = prepare_wifi_nvs(idf_project(factory), SSID, PASS, lambda s: None)
        logs = []
        result = flasher_mod.flash(prj, "COM_TEST", logs.append)
        assert result is (not fail)
        assert leftover_files(tmp_secret_dir) == []
        assert list(tmp_secret_dir.iterdir()) == []
        assert all(PASS not in l for l in logs)
        assert factory.exists()
        assert factory.read_bytes() == FACTORY_CONTENT
    
    prj = prepare_wifi_nvs(idf_project(factory), SSID, PASS, lambda s: None)
    missing = tmp_path / "missing.bin"
    prj2 = dataclasses.replace(prj, segments=prj.segments + (FlashSegment(0x300000, missing),))
    fake = FakeEsptool(fail=False)
    monkeypatch.setattr(flasher_mod, "esptool", fake)
    logs = []
    result = flasher_mod.flash(prj2, "COM_TEST", logs.append)
    assert result is False
    assert leftover_files(tmp_secret_dir) == []
    
    for f in tmp_path.rglob("*"):
        if f.is_file():
            content = f.read_bytes()
            assert PASS.encode("utf-8") not in content


def test_fake_esptool_sees_password_only_in_temp_copy(factory, tmp_secret_dir, monkeypatch):
    """Проверяет, что пароль виден только во временной копии."""
    state = {"found": False, "parent_name": ""}
    
    def reader(argv):
        idx = argv.index("write_flash")
        i = idx + 1
        while i < len(argv):
            if argv[i].startswith("--"):
                i += 2
            else:
                offset_str = argv[i]
                path_str = argv[i + 1]
                if int(offset_str, 16) == 0:
                    p = Path(path_str)
                    state["found"] = PASS.encode("utf-8") in p.read_bytes()
                    state["parent_name"] = p.parent.name
                i += 2
    
    fake = FakeEsptool(fail=False, reader=reader)
    monkeypatch.setattr(flasher_mod, "esptool", fake)
    prj = prepare_wifi_nvs(idf_project(factory), SSID, PASS, lambda s: None)
    logs = []
    flasher_mod.flash(prj, "COM_TEST", logs.append)
    
    assert state["found"] is True
    assert state["parent_name"].startswith("wifi_nvs_")
    # удаление копии проверяет test_flash_wipes_secret_files_on_success_and_failure
