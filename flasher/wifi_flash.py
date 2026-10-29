from __future__ import annotations

import dataclasses
import os
import shutil
import tempfile
from pathlib import Path

from .projects import FlashSegment, Project
from .wifi_nvs import WifiNvsError, build_wifi_nvs_image

SECRET_DIR_PREFIXES = ("wifi_nvs_", "esphome_nvs_")


def splice_region(src: Path, offset: int, data: bytes) -> Path:
    """
    Создаёт временную копию файла src, вставляя данные data по смещению offset.
    Исходный файл не изменяется.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if not data:
        raise ValueError("data must be non-empty")

    src_size = src.stat().st_size
    if src_size < offset + len(data):
        raise WifiNvsError("файл образа короче раздела NVS")

    d = tempfile.mkdtemp(prefix="wifi_nvs_")
    dst = Path(d) / src.name
    try:
        shutil.copyfile(src, dst)
        with open(dst, "r+b") as f:
            f.seek(offset)
            f.write(data)
            f.flush()
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise

    return dst


def wipe_file(path: Path) -> bool:
    """
    Заполняет файл нулями и удаляет его.
    Если родительская директория имеет секретный префикс и пуста, удаляет её.
    Никогда не бросает исключений.
    """
    try:
        if path.is_file():
            size = path.stat().st_size
            chunk_size = 1024 * 1024  # 1 MiB
            with open(path, "r+b") as f:
                for i in range(0, size, chunk_size):
                    f.seek(i)
                    f.write(b"\x00" * min(chunk_size, size - i))
                f.flush()
                os.fsync(f.fileno())
            path.unlink()
    except Exception:
        pass

    # Попытка удалить пустую родительскую директорию с секретным префиксом
    try:
        parent = path.parent
        if parent.name.startswith(SECRET_DIR_PREFIXES):
            # Проверяем, что директория пуста
            if not any(parent.iterdir()):
                parent.rmdir()
    except Exception:
        pass

    return not path.exists()


def wipe_secret_segments(segments) -> None:
    """
    Удаляет все сегменты, помеченные как секретные.
    """
    for seg in segments:
        if seg.secret:
            wipe_file(seg.path)


def apply_wifi_nvs(segments: tuple[FlashSegment, ...], nvs_offset: int, image: bytes) -> tuple[FlashSegment, ...]:
    """
    Применяет образ NVS к сегментам прошивки.
    Если NVS пересекается с одним сегментом, вставляет данные в него.
    Если не пересекается ни с одним, создаёт новый сегмент.
    """
    nvs_start = nvs_offset
    nvs_end = nvs_offset + len(image)

    intersecting = []
    for seg in segments:
        seg_size = seg.path.stat().st_size
        seg_start = seg.offset
        seg_end = seg.offset + seg_size

        # Проверка пересечения: [seg_start, seg_end) и [nvs_start, nvs_end)
        if seg_start < nvs_end and seg_end > nvs_start:
            intersecting.append(seg)

    if len(intersecting) > 1:
        raise WifiNvsError("раздел NVS пересекается с несколькими образами")

    if len(intersecting) == 1:
        seg = intersecting[0]
        seg_size = seg.path.stat().st_size
        seg_start = seg.offset
        seg_end = seg.offset + seg_size

        # Полностью содержит NVS?
        if seg_start <= nvs_start and seg_end >= nvs_end:
            # Заменяем сегмент
            new_path = splice_region(seg.path, nvs_offset - seg.offset, image)
            new_seg = FlashSegment(seg.offset, new_path, True)
            
            # Создаём новый кортеж с заменой
            new_segments = list(segments)
            for i, s in enumerate(new_segments):
                if s is seg:
                    new_segments[i] = new_seg
                    break
            return tuple(new_segments)
        else:
            raise WifiNvsError("образ перекрывает раздел NVS частично")

    # Ни один сегмент не пересекается с NVS
    d = tempfile.mkdtemp(prefix="wifi_nvs_")
    nvs_path = Path(d) / "wifi_nvs.bin"
    try:
        with open(nvs_path, "wb") as f:
            f.write(image)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise

    new_seg = FlashSegment(nvs_offset, nvs_path, True)
    return segments + (new_seg,)


def prepare_wifi_nvs(prj: Project, ssid: str, password: str, log) -> Project:
    """
    Подготавливает проект для записи Wi-Fi NVS.
    Возвращает новый Project с обновлёнными сегментами или исходный при ошибке.
    """
    if prj.wifi_nvs_offset is None:
        return prj

    ssid = ssid.strip()
    if not ssid:
        return prj

    try:
        image = build_wifi_nvs_image(ssid, password, prj.wifi_nvs_size, prj.wifi_nvs_extra_u8)
        segs = apply_wifi_nvs(prj.segments, prj.wifi_nvs_offset, image)
    except (WifiNvsError, OSError) as e:
        log(f"[wifi] не записываю сеть: {type(e).__name__}: {e}" if isinstance(e, OSError) else f"[wifi] не записываю сеть: {e}")
        return prj

    log(f"[wifi] сеть '{ssid}' будет записана в плату")
    return dataclasses.replace(prj, segments=segs)
