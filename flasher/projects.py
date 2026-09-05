from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FlashSegment:
    offset: int
    path: Path


@dataclass(frozen=True)
class Project:
    key: str
    title: str
    chip: str
    flash_mode: str
    flash_freq: str
    flash_size: str
    before: str
    after: str
    stub: bool
    segments: tuple[FlashSegment, ...]
    next_steps: str = ""

    # Новые поля
    github_repo: str = ""
    factory_asset_name: str = "firmware.factory.bin"
    segments_from_factory: bool = False

    # Опциональный шаг: грациозный ребут платы по сети (HTTP) ПЕРЕД
    # аппаратным сбросом esptool — плата успевает дописать/закрыть открытый
    # сегмент водопада. Есть только у прошивки atomspectra-waterfall-esp32
    # (эндпоинты /api/csrf-token + /api/reboot-esp), у ESPHome-шлюзов нет.
    pre_flash_http_reboot: bool = False

    # #RADEX-186: смещение раздела NVS, куда флешер может заранее записать
    # учётные данные Wi-Fi, чтобы плата поднялась в домашней сети сразу и
    # captive-портал был не нужен. None — проект так не умеет (у ESPHome-
    # прошивок своя схема хранения, этот формат туда не подходит).
    wifi_nvs_offset: int | None = None

    # #RADEX-186 шаг Б: ассет ТОЛЬКО приложения и его смещение. Полный образ
    # непрерывен от 0x0, и в его диапазон попадает раздел nvs — заливка на уже
    # настроенную плату стирает сохранённую сеть, привязку прибора и параметры
    # критерия (проверено на живой плате 05.09, audit/work-incidents.md W-065).
    # Пустое имя означает, что проект так не умеет: у ESPHome-прошивок нет
    # отдельного ассета приложения, там только factory.
    app_asset_name: str = ""
    app_offset: int = 0x20000

    def resolve(self, bin_path: Path) -> tuple[FlashSegment, ...]:
        if self.segments_from_factory:
            return (FlashSegment(0x0, bin_path),)
        else:
            return self.segments

    def resolve_app(self, bin_path: Path) -> tuple[FlashSegment, ...]:
        """Сегменты обновления: одно приложение, разделы данных не тронуты."""
        return (FlashSegment(self.app_offset, bin_path),)

    @property
    def supports_update(self) -> bool:
        return bool(self.app_asset_name)


# Реестр проектов
PROJECT_REGISTRY = {
    "atomspectra-waterfall-esp32": Project(
        key="atomspectra-waterfall-esp32",
        title="AtomSpectra (водопад ESP32-S3)",
        chip="esp32s3",
        flash_mode="dio",
        flash_freq="80m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/atomspectra-waterfall-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
        pre_flash_http_reboot=True,
    ),
    "atomfast-gateway": Project(
        key="atomfast-gateway",
        title="AtomFast BLE Gateway (ESP32)",
        chip="esp32",
        flash_mode="dio",
        flash_freq="40m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/atomfast-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
    ),
    # Radex MR107ion (радон) через BLE. Прошивка ESPHome, плата
    # ESP32-S3-DevKitC-1 N16R8 (16 MB флеша, 8 MB PSRAM) - та же, что у
    # водопада AtomSpectra. MAC прибора в бинарник не зашит: плата ищет
    # Radex в эфире сама, поэтому один общий образ годится всем.
    "radex-gateway": Project(
        key="radex-gateway",
        title="Radex BLE Gateway (ESP32-S3 N16R8)",
        chip="esp32s3",
        flash_mode="dio",
        flash_freq="80m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/radex-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
        wifi_nvs_offset=0x9000,
        # #RADEX-186 шаг Б: приложение лежит в релизе отдельным файлом — им
        # обновляют плату, которая уже настроена, не теряя сеть и привязку.
        app_asset_name="radex-gw-idf.bin",
        app_offset=0x20000,
        next_steps="Если вы заполнили поля Wi-Fi перед прошивкой, плата уже знает вашу сеть: включите её и через несколько секунд откройте Web UI - http://radex-gw.local/ (логин и пароль по умолчанию: radex / radex).\nЕсли сеть НЕ задавалась, плата поднимет свою точку доступа RadexGW-Setup (без пароля): подключитесь к ней с телефона, откроется страница настройки (если нет - зайдите на http://192.168.4.1), выберите домашнюю сеть и введите пароль.\nЗатем включите Radex MR107ion рядом с платой. Прибор находится в эфире сам - следите за полем 'Найденный прибор Radex' в Web UI. Если приборов несколько, впишите нужный адрес в поле 'MAC Radex (AA:BB:CC:DD:EE:FF)' и нажмите 'Применить MAC и перезагрузить'.\nВыгрузка на Народмон выключена и включается только вручную.",
    ),
    "radon-gateway": Project(
        key="radon-gateway",
        title="RadonEye BLE Gateway (ESP32)",
        chip="esp32",
        flash_mode="dio",
        flash_freq="40m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/radoneye-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
    ),
    "bdkg05-gateway": Project(
        key="bdkg05-gateway", title="ATOMTEX БДКГ-05 USB Gateway (ESP32-S3)",
        chip="esp32s3", flash_mode="dio", flash_freq="80m", flash_size="detect",
        before="default_reset", after="hard_reset", stub=True, segments=(),
        github_repo="VibeEngineering-LLC/atomtex-esp32",
        factory_asset_name="firmware.factory.bin", segments_from_factory=True,
    ),
}


def all_projects() -> list[Project]:
    return list(PROJECT_REGISTRY.values())