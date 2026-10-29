"""Чистая логика предупреждений при записи NVS ESPHome (без Qt)."""
from __future__ import annotations


def needs_empty_password_confirm(ssid: str, password: str, checked: bool) -> bool:
    """Нужно ли переспросить: сеть пишется, а пароль пуст."""
    return bool(checked and ssid.strip() and not password)


def nvs_warning_lines(has_wifi: bool, has_mac: bool) -> list[str]:
    """Строки лога о том, что раздел настроек перезаписывается целиком."""
    lines = ["[nvs] внимание: раздел настроек платы записывается целиком, "
             "остальные сохранённые настройки (MAC из веб-интерфейса, сеть из портала, "
             "имена метрик) будут сброшены"]
    if has_wifi and not has_mac:
        lines.append("[nvs] MAC прибора не задан: ранее сохранённый MAC будет стёрт")
    if has_mac and not has_wifi:
        lines.append("[nvs] Wi-Fi не задан: ранее сохранённая сеть будет стёрта")
    return lines
