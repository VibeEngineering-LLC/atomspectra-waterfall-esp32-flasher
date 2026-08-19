"""Сетевой (грациозный) ребут платы AtomSpectra перед прошивкой esptool.

Аппаратный сброс, который делает esptool через RTS/DTR, обрывает запись
открытого сегмента водопада на середине — файл не финализируется. Штатный
HTTP-эндпоинт прошивки `/api/reboot-esp` (защищён CSRF-токеном с
`/api/csrf-token`) делает то же самое ГРАЦИОЗНО: сначала дописывает и
закрывает открытый сегмент, потом перезагружается сама.

Это ЛУЧШИЙ ЭФФОРТ, не обязательный шаг. Любая сетевая ошибка (платы нет в
сети, не тот IP, таймаут, неожиданный ответ) логируется по-русски и НЕ
бросается наружу — вызывающий код обязан продолжить прошивку в любом случае
(аппаратным путём, как раньше).

Только stdlib — без новых зависимостей.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable

LogCB = Callable[[str], None]

_CSRF_URL = "http://{ip}/api/csrf-token"
_REBOOT_URL = "http://{ip}/api/reboot-esp"
_POST_REBOOT_DELAY_S = 2.5

_FALLBACK_MSG = (
    "[reboot] плата недоступна по сети, шью напрямую "
    "(аппаратный сброс, открытый сегмент может потеряться)"
)


def reboot_before_flash(ip: str, log: LogCB, timeout: float = 5.0) -> bool:
    """Грациозный ребут платы по сети перед прошивкой esptool.

    Возвращает True, если команда ребута принята платой и мы подождали,
    пока она закроет сегмент. Возвращает False при ЛЮБОЙ сетевой ошибке —
    это best-effort шаг, падать он не должен.
    """
    ip = (ip or "").strip()
    if not ip:
        log("[reboot] IP платы не задан — пропускаю сетевой ребут")
        return False

    try:
        log(f"[reboot] запрашиваю CSRF-токен у {ip}...")
        req = urllib.request.Request(_CSRF_URL.format(ip=ip), method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")

        data = json.loads(body)
        token = (
            data.get("token")
            or data.get("csrf_token")
            or data.get("csrfToken")
        )
        if not token:
            log(f"[reboot] в ответе платы нет поля token: {body[:200]!r}")
            log(_FALLBACK_MSG)
            return False

        log("[reboot] отправляю команду грациозного ребута...")
        reboot_req = urllib.request.Request(
            _REBOOT_URL.format(ip=ip),
            method="POST",
            headers={"X-CSRF-Token": token},
        )
        with urllib.request.urlopen(reboot_req, timeout=timeout) as resp:
            resp.read()

        log(
            f"[reboot] команда принята, жду {_POST_REBOOT_DELAY_S:.1f}с "
            "закрытия сегмента платой..."
        )
        time.sleep(_POST_REBOOT_DELAY_S)
        log("[reboot] готово — сегмент закрыт, можно прошивать")
        return True

    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log(f"[reboot] ошибка сети ({type(e).__name__}: {e})")
        log(_FALLBACK_MSG)
        return False
