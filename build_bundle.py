"""
build_bundle.py — Скачивает ВСЁ для полностью офлайн-лаунчера.
Запускать на машине разработчика С интернетом.
Результат: bundle.tar.xz — максимально сжатый архив.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
import concurrent.futures
from pathlib import Path

import requests

import lzma
import tarfile

# ── Конфиг ──
MANIFEST_URL = "https://drive.usercontent.google.com/uc?id=12bGhgtLvC7vzpc6VGBWI4iISAQBepIjP&export=download"
MOJANG_MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"

ROOT = Path(__file__).parent
BUNDLE = ROOT / "bundle"


def get_java_urls(manifest: dict) -> list:
    """URL Java для текущей платформы из manifest.json."""
    key = {
        "Windows": "java_windows",
        "Darwin": "java_macos",
    }.get(platform.system(), "java_linux")
    platform_cfg = manifest.get(key, {})
    if isinstance(platform_cfg, dict):
        urls = platform_cfg.get("urls", [])
        if urls:
            return urls
    return manifest.get("java_urls", [])


def log(msg):
    print(f"[BUILD] {msg}")


def download(url, dest, label=""):
    """Скачать файл с прогрессом."""
    log(f"  ↓ {label or url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                print(f"\r  [{pct:5.1f}%] {downloaded // 1048576} / {total // 1048576} MB", end="", flush=True)
    print()


def main():
    log("=" * 50)
    log("BunLauncher Offline Bundle Builder")
    log("=" * 50)

    # ── 1. Манифест ──
    log("1/7 Чтение локального манифеста...")
    manifest_path = ROOT / "manifest.json"
    if not manifest_path.exists():
        manifest_path = BUNDLE / "manifest.json"
        
    if not manifest_path.exists():
        log("  ✗ Ошибка: локальный manifest.json не найден в корне или bundle/")
        sys.exit(1)
        
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    BUNDLE.mkdir(parents=True, exist_ok=True)
    # Копируем манифест в bundle/ чтобы он попал в архив
    (BUNDLE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    mc_version = manifest.get("minecraft_version")
    java_version = manifest.get("java_version")
    neo_version = manifest.get("neoforge_version")
    java_urls = get_java_urls(manifest)
    neo_urls = manifest.get("neoforge_urls", [])
    archive_urls = manifest.get("archive_urls", [])
    archive_sha256 = manifest.get("archive_sha256", "")

    log(f"  Minecraft: {mc_version}")
    log(f"  Java: {java_version}")
    log(f"  NeoForge: {neo_version}")

    # ── 2. Java JRE ──
    log("2/7 Скачивание Java JRE...")
    java_dir = BUNDLE / "runtime" / f"jre-{java_version}"
    java_bin = java_dir / "bin" / ("java.exe" if platform.system() == "Windows" else "java")

    if not java_bin.exists():
        is_win = platform.system() == "Windows"
        arch = "x64"
        archive_ext = ".jre.zip" if is_win else ".jre.tar.gz"
        archive_path = BUNDLE / archive_ext

        # Пробуем URL из манифеста
        for url in java_urls:
            try:
                download(url, archive_path, f"Java {java_version}")
                break
            except Exception as e:
                log(f"  ✗ {e}")
                continue

        # Фоллбэк: Adoptium (Eclipse Temurin)
        if not archive_path.exists():
            os_name = "windows" if is_win else ("mac" if platform.system() == "Darwin" else "linux")
            ext = "zip" if is_win else "tar.gz"
            adoptium_url = (
                f"https://api.adoptium.net/v3/binary/latest/{java_version}/ga/"
                f"{os_name}/{arch}/jre/hotspot/normal/eclipse?project=jdk"
            )
            log(f"  Фоллбэк: Adoptium Temurin JRE {java_version}...")
            try:
                download(adoptium_url, archive_path, f"Adoptium JRE {java_version}")
            except Exception as e:
                log(f"  ✗ Adoptium тоже не удался: {e}")

        if not archive_path.exists():
            log(f"  ✗ ОШИБКА: Не удалось скачать Java JRE ни по одному URL")
            sys.exit(1)

        java_dir.mkdir(parents=True, exist_ok=True)
        if is_win:
            with zipfile.ZipFile(archive_path, "r") as zf:
                # Ищем корневую папку в архиве и распаковываем с strip
                names = zf.namelist()
                prefix = names[0].split("/")[0] + "/" if names else ""
                for member in names:
                    # Убираем первый уровень (jdk-21.0.x-jre/)
                    rel = member[len(prefix):] if member.startswith(prefix) else member
                    if not rel: continue
                    target = java_dir / rel
                    if member.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        else:
            subprocess.run(["tar", "-xzf", str(archive_path), "-C", str(java_dir), "--strip-components=1"], check=True)

        if archive_path.exists():
            archive_path.unlink()
    else:
        log("  ✓ Java уже скачана")

    if not java_bin.exists():
        log(f"  ✗ ОШИБКА: java не найдена по пути {java_bin}")
        sys.exit(1)

    # ── 3. Vanilla Minecraft ──
    log("3/7 Скачивание Minecraft vanilla...")
    versions_dir = BUNDLE / "versions" / mc_version
    versions_dir.mkdir(parents=True, exist_ok=True)
    van_json_path = versions_dir / f"{mc_version}.json"
    van_jar_path = versions_dir / f"{mc_version}.jar"

    if not van_json_path.exists():
        log("  Получение манифеста Mojang...")
        mojang = requests.get(MOJANG_MANIFEST_URL, timeout=60).json()
        entry = next((v for v in mojang["versions"] if v["id"] == mc_version), None)
        if not entry:
            log(f"  ✗ Версия {mc_version} не найдена в Mojang")
            sys.exit(1)

        version_data = requests.get(entry["url"], timeout=60).json()
        van_json_path.write_text(json.dumps(version_data, indent=2), encoding="utf-8")
    else:
        version_data = json.loads(van_json_path.read_text(encoding="utf-8"))

    if not van_jar_path.exists():
        jar_url = version_data["downloads"]["client"]["url"]
        download(jar_url, van_jar_path, "Minecraft client.jar")
    else:
        log("  ✓ client.jar уже есть")

    # ── 4. Assets ──
    log("4/7 Скачивание ассетов (звуки, текстуры)...")
    assets_dir = BUNDLE / "assets"
    indexes_dir = assets_dir / "indexes"
    objects_dir = assets_dir / "objects"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    objects_dir.mkdir(parents=True, exist_ok=True)

    asset_index_info = version_data.get("assetIndex", {})
    idx_id = asset_index_info.get("id", "17")
    index_path = indexes_dir / f"{idx_id}.json"

    if not index_path.exists():
        idx_url = asset_index_info["url"]
        download(idx_url, index_path, f"Asset index {idx_id}")

    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    objects = index_data.get("objects", {})

    missing = []
    for _, val in objects.items():
        h = val.get("hash", "")
        if h:
            obj_path = objects_dir / h[:2] / h
            if not obj_path.exists():
                missing.append((h, obj_path))

    if missing:
        log(f"  Скачивание {len(missing)} ассетов...")

        def dl_asset(item):
            h, path = item
            url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                path.write_bytes(r.content)
            except Exception:
                pass

        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = {pool.submit(dl_asset, item): item for item in missing}
            for f in concurrent.futures.as_completed(futures):
                done += 1
                if done % 100 == 0 or done == len(missing):
                    print(f"\r  [{done}/{len(missing)}]", end="", flush=True)
        print()
    else:
        log("  ✓ Все ассеты уже есть")

    # ── 5. Libraries ──
    log("5/7 Скачивание библиотек...")
    libs_dir = BUNDLE / "libraries"
    libs_dir.mkdir(parents=True, exist_ok=True)

    os_name = {"Linux": "linux", "Darwin": "osx", "Windows": "windows"}.get(platform.system(), "windows")

    def download_libs(version_json):
        for lib in version_json.get("libraries", []):
            allowed = True
            rules = lib.get("rules")
            if rules:
                for rule in rules:
                    action = rule.get("action", "allow")
                    os_obj = rule.get("os", {})
                    if os_obj.get("name") == os_name:
                        allowed = action == "allow"
            if not allowed:
                continue

            artifact = lib.get("downloads", {}).get("artifact", {})
            path = artifact.get("path")
            url = artifact.get("url")
            if path and url:
                dest = libs_dir / path
                if not dest.exists():
                    download(url, dest, path.split("/")[-1])

            # Natives
            native_key = f"natives-{os_name}"
            classifiers = lib.get("downloads", {}).get("classifiers", {})
            native = classifiers.get(native_key, {})
            if native.get("path") and native.get("url"):
                dest = libs_dir / native["path"]
                if not dest.exists():
                    download(native["url"], dest, native["path"].split("/")[-1])

    download_libs(version_data)

    # ── 6. NeoForge ──
    log("6/7 Установка NeoForge...")
    # Всегда устанавливаем NeoForge
    neo_installed = None
    installer_path = BUNDLE / ".neoforge_installer.jar"
    for url in neo_urls:
        try:
            download(url, installer_path, "NeoForge installer")
            break
        except Exception as e:
            log(f"  ✗ {e}")

    # Читаем version id из install_profile
    neo_installed = f"neoforge-{neo_version}"
    try:
        if zipfile.is_zipfile(installer_path):
            with zipfile.ZipFile(installer_path, "r") as zf:
                if "install_profile.json" in zf.namelist():
                    with zf.open("install_profile.json") as f:
                        neo_installed = json.loads(f.read()).get("version", f"neoforge-{neo_version}")
    except Exception:
        pass

    # Create a dummy launcher_profiles.json so the installer doesn't complain
    dummy_profiles = BUNDLE / "launcher_profiles.json"
    if not dummy_profiles.exists():
        dummy_profiles.write_text('{"profiles":{}}', encoding="utf-8")

    log(f"  Запуск NeoForge installer ({neo_installed})...")
    result = subprocess.run(
        [str(java_bin), "-jar", str(installer_path), "--install-client", str(BUNDLE)],
        cwd=str(BUNDLE),
    )

    if installer_path.exists():
        installer_path.unlink()

    if result.returncode != 0:
        log(f"  ✗ NeoForge installer вернул код {result.returncode}")
        # Попробуем найти установленную версию
        neo_versions_dir = BUNDLE / "versions"
        if neo_versions_dir.exists():
            for d in neo_versions_dir.iterdir():
                if d.is_dir() and d.name.startswith("neoforge-") and neo_version in d.name:
                    if (d / f"{d.name}.json").exists():
                        neo_installed = d.name
                        break

    # Скачиваем библиотеки NeoForge
    neo_json_path = BUNDLE / "versions" / neo_installed / f"{neo_installed}.json"
    if neo_json_path.exists():
        neo_json = json.loads(neo_json_path.read_text(encoding="utf-8"))
        download_libs(neo_json)

    # Сохраняем neo_id в manifest
    manifest["_neo_id"] = neo_installed
    (BUNDLE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # ── 7. Модпак ──
    log("7/7 Скачивание модпака...")
    mods_dir = BUNDLE / "mods"

    if archive_urls:
        modpack_zip = BUNDLE / ".modpack.zip"
        for url in archive_urls:
            try:
                download(url, modpack_zip, "Модпак")
                break
            except Exception as e:
                log(f"  ✗ {e}")

        if modpack_zip.exists():
            # Чистим старые моды
            if mods_dir.exists():
                for f in mods_dir.iterdir():
                    if f.is_file() and f.suffix == ".jar":
                        f.unlink()

            log("  Распаковка модпака...")
            with zipfile.ZipFile(modpack_zip, "r") as zf:
                for name in zf.namelist():
                    # Ищем файлы внутри папки mods/ или config/ (даже если они в подпапках внутри архива)
                    parts = name.split("/")
                    if "mods" in parts:
                        idx = parts.index("mods")
                        subpath = "/".join(parts[idx:])
                        if not name.endswith("/"): # это файл
                            dest = BUNDLE / subpath
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(name) as source, open(dest, "wb") as target:
                                shutil.copyfileobj(source, target)
                    elif "config" in parts:
                        idx = parts.index("config")
                        subpath = "/".join(parts[idx:])
                        if not name.endswith("/"): # это файл
                            dest = BUNDLE / subpath
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(name) as source, open(dest, "wb") as target:
                                shutil.copyfileobj(source, target)
                                
            modpack_zip.unlink()
    else:
        log("  Нет URL модпака в манифесте")

    # ── Готово: bundle/ собран ──
    log("=" * 50)
    raw_size = sum(f.stat().st_size for f in BUNDLE.rglob("*") if f.is_file())
    log(f"Bundle (несжатый): {raw_size / 1048576:.0f} MB")
    log(f"NeoForge ID: {neo_installed}")

    # ══════════════════════════════════════════════════
    # 8/8 Сжатие в .tar.xz (LZMA2, максимальный пресет)
    # ══════════════════════════════════════════════════
    log("")
    log("8/8 Сжатие bundle → bundle.tar.xz (LZMA2 max)...")
    log("  Это может занять 5-20 минут. Пожалуйста, подождите.")

    archive_path = ROOT / "bundle.tar.xz"

    # LZMA2 с максимальным пресетом (9) + extreme
    lzma_filters = [
        {"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME}
    ]

    with lzma.open(archive_path, "wb", filters=lzma_filters, format=lzma.FORMAT_XZ) as xz:
        with tarfile.open(fileobj=xz, mode="w") as tar:
            files = sorted(f for f in BUNDLE.rglob("*") if f.is_file())
            total = len(files)
            for i, fpath in enumerate(files):
                arcname = fpath.relative_to(BUNDLE)
                tar.add(fpath, arcname=str(arcname))
                if (i+1) % 100 == 0 or i+1 == total:
                    print(f"\r  [{i+1}/{total}] {(i+1)/total*100:.0f}%", end="", flush=True)
            print()

    compressed_size = archive_path.stat().st_size
    ratio = compressed_size / raw_size * 100 if raw_size > 0 else 0
    log(f"  ✓ Сжато: {compressed_size / 1048576:.0f} MB ({ratio:.0f}% от оригинала)")
    log(f"  Файл: {archive_path}")
    log("")
    log("Следующий шаг — компиляция:")
    log('  python -m PyInstaller --onefile --noconsole --name BunLauncher --icon assets/bun.png --add-data "bundle.tar.xz;." --add-data "assets;assets" run.py')


if __name__ == "__main__":
    main()
