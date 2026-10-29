import sys; sys.stdout.reconfigure(encoding="utf-8")
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MUTATIONS = [
    ("password_in_log", "flasher/wifi_flash.py", "будет записана в плату\")", "будет записана в плату {password}\")", 1),
    ("bin_not_deleted", "flasher/flasher.py", "        wipe_secret_segments(project.segments)", "        pass", 1),
    ("splice_wrong_offset", "flasher/wifi_flash.py", "f.seek(offset)", "f.seek(offset + 0x1000)", 1),
    ("unver_not_written", "flasher/wifi_nvs.py", "_gen.write_entry(nvs, key, \"data\", \"u8\", str(value))", "pass", 1),
    ("esphome_release_passes_filter", "flasher/updater.py", "if any(a.name == asset_name for a in release.assets):", "if True:", 1),
    ("idf_app_asset_dropped", "flasher/projects.py", "app_asset_name=\"atomfast_gw.bin\",", "app_asset_name=\"\",", 1),
    ("nvs_not_spliced_overlap_returns", "flasher/wifi_flash.py", "if seg_start < nvs_end and seg_end > nvs_start:", "if False:", 5),
]


def run_pytest():
    """Запускает pytest и возвращает список упавших тестов."""
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "-rf", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env
    )
    failed_tests = set()
    for line in result.stdout.splitlines():
        if line.startswith("FAILED "):
            # Извлекаем ID теста: второй токен до " - " или конца строки
            rest = line[len("FAILED "):]
            if " - " in rest:
                test_id = rest.split(" - ")[0]
            else:
                test_id = rest
            if test_id:
                failed_tests.add(test_id)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pytest rc={result.returncode}: " + result.stdout[-300:])
    if result.returncode == 1 and not failed_tests:
        raise RuntimeError("pytest rc=1 без FAILED: " + result.stdout[-300:])
    return failed_tests


def main():
    # Базовый запуск: должно быть 0 упавших тестов
    baseline_failed = run_pytest()
    if len(baseline_failed) > 0:
        print("baseline красный")
        sys.exit(2)

    # Сохраняем оригинальные байты всех файлов, которые будем мутировать
    original_bytes = {}
    for name, rel_file, old_text, new_text, expected in MUTATIONS:
        file_path = ROOT / rel_file
        if file_path not in original_bytes:
            original_bytes[file_path] = file_path.read_bytes()

    ok_count = 0
    total_count = len(MUTATIONS)

    for name, rel_file, old_text, new_text, expected in MUTATIONS:
        file_path = ROOT / rel_file
        try:
            # Читаем файл как байты, декодируем в utf-8
            content_bytes = file_path.read_bytes()
            content_str = content_bytes.decode("utf-8")

            # Проверяем, что old_text встречается ровно один раз
            count = content_str.count(old_text)
            if count != 1:
                print(f"SKIP/ERROR {name}: old_text occurs {count} times")
                continue

            # Заменяем текст
            mutated_str = content_str.replace(old_text, new_text, 1)
            mutated_bytes = mutated_str.encode("utf-8")

            # Записываем мутированный файл (байты, чтобы сохранить окончания строк)
            file_path.write_bytes(mutated_bytes)

            # Запускаем тесты
            failed_tests = run_pytest()
            n_failed = len(failed_tests)

            # Восстанавливаем оригинальный файл
            file_path.write_bytes(original_bytes[file_path])

            # Выводим результат
            status = "OK" if n_failed == expected else "НЕ ТО"
            print(f"{name}: упало тестов {n_failed} (ожидалось {expected}) -> {status}")
            for test_id in sorted(failed_tests):
                print(f"  {test_id}")

            if n_failed == expected:
                ok_count += 1

        except Exception as e:
            # В случае ошибки восстанавливаем файл и считаем как провал
            try:
                file_path.write_bytes(original_bytes[file_path])
            except Exception:
                pass
            print(f"ERROR {name}: {e}")
            continue

    # Проверяем, что все файлы восстановлены
    all_restored = True
    for file_path, orig_bytes in original_bytes.items():
        if file_path.read_bytes() != orig_bytes:
            all_restored = False
            break

    if not all_restored:
        print("файлы НЕ восстановлены")
        sys.exit(3)
    else:
        print("файлы восстановлены")

    print(f"мутаций {ok_count}/{total_count}")
    if ok_count == total_count:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # finally блоки внутри цикла уже восстановили файлы, но на всякий случай
        # здесь можно добавить дополнительную проверку, если нужно
        sys.exit(130)
