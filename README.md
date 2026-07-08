# ESP32 Flasher

Простой прошивальщик для ESP32-устройств на базе Python/PySide6.
Автоматически загружает актуальную прошивку с GitHub Releases.

## Требования

- Windows 10/11 x64
- Интернет-соединение (прошивка тянется с GitHub при каждом запуске)
- USB-драйвер платы (CH340 / CP2102 / FTDI)

## Использование

1. Запустить `atomspectra-waterfall-esp32.exe`
2. Выбрать проект из выпадающего списка
3. Выбрать COM-порт платы
4. Нажать «Установить»

Flasher автоматически загрузит последнюю версию прошивки с GitHub и прошьёт плату.

## ⚠ Перед использованием

Flasher **стирает и перезаписывает флэш-память** выбранной платы ESP32. Убедитесь, что:

- выбран правильный COM-порт **именно вашей платы** (посторонние USB-UART-устройства —
  звуковые карты, адаптеры — прошивать нельзя, это выведет их из строя);
- прошивка не прерывается (не отключайте плату во время записи) — прерывание может
  потребовать восстановления платы в режиме загрузчика.

Flasher прошивает только плату ESP32; на подключённый к плате измерительный прибор
он не воздействует.

## Отказ от ответственности

Программа предоставляется «как есть», без каких-либо гарантий. Автор не несёт
ответственности за любой прямой или косвенный ущерб: неработоспособность платы или
подключённого оборудования, потерю данных, ошибочную прошивку не того устройства.
Используя программу, вы действуете на свой страх и риск.

## Поддерживаемые устройства

| Проект | Репо прошивки |
|--------|--------------|
| AtomSpectra (водопад ESP32-S3) | VibeEngineering-LLC/atomspectra-waterfall-esp32 |
| AtomFast BLE Gateway (ESP32) | VibeEngineering-LLC/atomfast-esp32 |
| Radex BLE Gateway (ESP32-S3) | VibeEngineering-LLC/radex-esp32 |
| RadonEye BLE Gateway (ESP32) | VibeEngineering-LLC/radoneye-esp32 |

## Обновление прошивки

Flasher при каждом запуске запрашивает `latest release` с GitHub API и кэширует файлы
в `%LOCALAPPDATA%\atomspectra-flasher\cache\<repo>\<tag>\`.
Для принудительного обновления нажать «Обновить прошивку» в UI.

При отсутствии интернета или превышении rate limit GitHub API — flasher показывает
fatal-сообщение. Offline-режим не поддерживается.

## Сборка из исходников

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/make_icon.py       # если ассетов ещё нет
python -m flasher                 # запуск без сборки .exe
```

Сборка `.exe`:

```powershell
python -m PyInstaller --noconfirm --clean atomspectra-waterfall-esp32.spec
# → dist/atomspectra-waterfall-esp32.exe
```

## Лицензия

MIT
