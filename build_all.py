"""
build_all.py — Полная сборка BunLauncher: bundle → exe → installer.
Один скрипт для всего процесса.
"""
import platform
import subprocess
import sys
import shutil
import os
from pathlib import Path

ROOT = Path(__file__).parent
IS_WINDOWS = platform.system() == "Windows"
DATA_SEP = ";" if IS_WINDOWS else ":"
EXE_NAME = "BunLauncher.exe" if IS_WINDOWS else "BunLauncher"


def log(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")

def run(cmd, **kw):
    print(f"  > {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=str(ROOT), **kw)
    if r.returncode != 0:
        print(f"  ✗ Команда завершилась с кодом {r.returncode}")
        return False
    return True

def check_tool(name, cmd):
    """Проверяет наличие инструмента."""
    try:
        subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
        return True
    except:
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="BunLauncher Full Build")
    parser.add_argument("--skip-bundle", action="store_true", help="Пропустить скачивание (bundle уже готов)")
    parser.add_argument("--skip-exe", action="store_true", help="Пропустить PyInstaller (exe уже готов)")
    parser.add_argument("--skip-installer", action="store_true", help="Пропустить Inno Setup")
    parser.add_argument("--force-bundle", action="store_true", help="Пересобрать bundle без запроса")
    parser.add_argument("--yes", action="store_true", help="Не задавать интерактивных вопросов")
    args = parser.parse_args()
    non_interactive = args.force_bundle or args.yes or os.environ.get("CI") == "true"

    # ── Информация ──
    log("BunLauncher Full Build Pipeline")
    print("  Шаги:")
    print("  1. build_bundle.py  → bundle.tar.xz (скачивание + LZMA2)")
    print("  2. PyInstaller      → dist/BunLauncher.exe")
    print("  3. Inno Setup       → installer_output/BunLauncher_Setup.exe")
    print()

    # ── Проверка инструментов ──
    has_pyinstaller = check_tool("PyInstaller", "python -m PyInstaller --version")
    if not has_pyinstaller:
        print("  ⚠ PyInstaller не найден. Установите: pip install pyinstaller")
        sys.exit(1)

    # Inno Setup
    iscc_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        shutil.which("ISCC") or "",
    ]
    iscc = None
    for p in iscc_paths:
        if p and Path(p).exists():
            iscc = p
            break

    if not iscc and not args.skip_installer:
        print("  ⚠ Inno Setup не найден.")
        print("  Скачайте: https://jrsoftware.org/isdl.php")
        print("  Или используйте --skip-installer")
        print()

    # ═══ Шаг 1: Bundle ═══
    if not args.skip_bundle:
        log("Шаг 1/3: Скачивание и сжатие bundle")
        bundle_exists = (ROOT / "bundle.tar.xz").exists()
        if bundle_exists and not args.force_bundle:
            print("  ℹ bundle.tar.xz уже существует.")
            if non_interactive:
                print("  → Пропускаем (используйте --force-bundle для пересборки)")
            else:
                ans = input("  Пересобрать? (y/N): ").strip().lower()
                if ans != "y":
                    print("  → Пропускаем")
                elif not run(f"{sys.executable} build_bundle.py"):
                    sys.exit(1)
        elif bundle_exists and args.force_bundle:
            if not run(f"{sys.executable} build_bundle.py"):
                sys.exit(1)
        else:
            if not run(f"{sys.executable} build_bundle.py"):
                sys.exit(1)
    else:
        print("  → Шаг 1 пропущен (--skip-bundle)")

    # Проверяем что bundle готов
    use_archive = (ROOT / "bundle.tar.xz").exists()
    use_folder = (ROOT / "bundle").exists()
    if not use_archive and not use_folder:
        print("  ✗ Ни bundle.tar.xz, ни bundle/ не найдены!")
        sys.exit(1)

    # ═══ Шаг 2: PyInstaller ═══
    if not args.skip_exe:
        log("Шаг 2/3: Компиляция PyInstaller → BunLauncher.exe")

        # Определяем что включать
        if use_archive:
            data_args = f'--add-data "bundle.tar.xz{DATA_SEP}."'
            print("  Используем: bundle.tar.xz (сжатый)")
        else:
            data_args = f'--add-data "bundle{DATA_SEP}bundle"'
            print("  Используем: bundle/ (несжатый)")

        icon_arg = ""
        if (ROOT / "assets" / "bun.png").exists():
            # PyInstaller на Windows предпочитает .ico — но .png тоже работает
            icon_arg = '--icon "assets/bun.png"'

        cmd = (
            f'{sys.executable} -m PyInstaller --onefile --noconsole '
            f'--name BunLauncher {icon_arg} '
            f'{data_args} '
            f'--add-data "assets{DATA_SEP}assets" '
            f'run.py'
        )
        if not run(cmd):
            sys.exit(1)

        exe_path = ROOT / "dist" / EXE_NAME
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / 1048576
            print(f"  ✓ {exe_path} ({size_mb:.0f} MB)")
        else:
            print(f"  ✗ {EXE_NAME} не создан!")
            sys.exit(1)
    else:
        print("  → Шаг 2 пропущен (--skip-exe)")

    # ═══ Шаг 3: Inno Setup Installer ═══
    if not args.skip_installer:
        log("Шаг 3/3: Создание установщика (Inno Setup)")

        if not IS_WINDOWS:
            print("  → Inno Setup доступен только на Windows (--skip-installer на других ОС)")
        elif not iscc:
            print("  ⚠ Inno Setup (ISCC.exe) не найден — пропускаем.")
            print("  Скачайте: https://jrsoftware.org/isdl.php")
            print("  Затем: ISCC.exe installer.iss")
        else:
            iss_path = ROOT / "installer.iss"
            if not iss_path.exists():
                print("  ✗ installer.iss не найден!")
                sys.exit(1)

            # Создаём папку для выхода
            (ROOT / "installer_output").mkdir(exist_ok=True)

            if not run(f'"{iscc}" "{iss_path}"'):
                print("  ✗ Inno Setup завершился с ошибкой")
                sys.exit(1)

            setup = ROOT / "installer_output" / "BunLauncher_Setup.exe"
            if setup.exists():
                size_mb = setup.stat().st_size / 1048576
                print(f"  ✓ {setup} ({size_mb:.0f} MB)")
    else:
        print("  → Шаг 3 пропущен (--skip-installer)")

    # ═══ Итог ═══
    log("Сборка завершена!")
    print("  Файлы:")

    for name, path in [
        ("Bundle", ROOT / "bundle.tar.xz"),
        ("EXE", ROOT / "dist" / EXE_NAME),
        ("Installer", ROOT / "installer_output" / "BunLauncher_Setup.exe"),
    ]:
        if path.exists():
            size = path.stat().st_size / 1048576
            print(f"    ✓ {name}: {path} ({size:.0f} MB)")
        else:
            print(f"    ✗ {name}: не найден")

    print()
    print("  Раздайте пользователям:")
    setup = ROOT / "installer_output" / "BunLauncher_Setup.exe"
    exe = ROOT / "dist" / EXE_NAME
    if setup.exists():
        print(f"    → {setup}")
        print("    (полноценный установщик с ярлыками и удалением)")
    elif exe.exists():
        print(f"    → {exe}")
        print("    (портативный .exe)")


if __name__ == "__main__":
    main()
