# atomspectra-waterfall-esp32 (Flasher)

Автономный Windows-прошивальщик платы **AtomSpectra Waterfall (ESP32-S3)**.
Один `.exe`, всё внутри — драйвер esptool, готовые `.bin`, минимальный UI.

## Клиенту

1. Скачать `atomspectra-waterfall-esp32.exe`.
2. Вставить плату в USB.
3. Запустить `.exe`.
4. Выбрать проект (пока один: *AtomSpectra Waterfall (ESP32-S3)*), проверить,
   что автоматически подставился нужный COM-порт (иначе — «Обновить»).
5. Нажать **Установить**. Ждать «Готово».

## Сборка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/make_icon.py       # если ассетов ещё нет
python -m PyInstaller --noconfirm --clean atomspectra-waterfall-esp32.spec
# → dist/atomspectra-waterfall-esp32.exe
```

## Смена/обновление firmware

Положи новые файлы в `firmware/atomspectra-waterfall-esp32/`:

- `bootloader.bin`
- `partition-table.bin`
- `atomspectra_gw.bin`
- `flasher_args.json` (offsets/flash-settings; берётся из `build/` ESP-IDF)

Пересобрать `.exe` тем же PyInstaller-командой.

## Добавление других проектов

Пока только AtomSpectra. Radex / AtomFast / RadonEye — в будущем: положить их
`firmware/<key>/` + расширить `all_projects()` в
`flasher/projects.py`.
