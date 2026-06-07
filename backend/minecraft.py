"""
Minecraft — скачивание vanilla, ассетов, библиотек, установка NeoForge.
Все функции принимают progress callback.
"""
import json
import os
import platform
import subprocess
import zipfile
import concurrent.futures
from pathlib import Path
from typing import Optional, Callable

import requests

from backend.downloader import download_file, download_with_fallback, ProgressCB

MOJANG_MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"


def _noop(*_a, **_kw):
    pass


def read_json(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"Файл не найден: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_install_profile_version(installer_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(installer_path, "r") as zf:
            if "install_profile.json" not in zf.namelist():
                return None
            with zf.open("install_profile.json") as f:
                data = json.loads(f.read())
                return data.get("version")
    except Exception:
        return None


def detect_installed_neoforge(game_dir: Path, prefix: str) -> str | None:
    versions_dir = game_dir / "versions"
    if not versions_dir.exists():
        return None
    for entry in versions_dir.iterdir():
        if entry.is_dir():
            name = entry.name
            if name.startswith("neoforge-") and prefix in name:
                json_path = entry / f"{name}.json"
                if json_path.exists():
                    return name
    return None


# ─── Vanilla ───────────────────────────────────────────

def ensure_vanilla(game_dir: Path, version: str, progress: ProgressCB = None) -> dict:
    cb = progress or _noop
    vanilla_dir = game_dir / "versions" / version
    vanilla_jar = vanilla_dir / f"{version}.jar"
    vanilla_json_path = vanilla_dir / f"{version}.json"
    vanilla_dir.mkdir(parents=True, exist_ok=True)

    if vanilla_json_path.exists():
        version_json = read_json(vanilla_json_path)
    else:
        cb("Получение манифеста Mojang...", 0, 0, 0)
        resp = requests.get(MOJANG_MANIFEST_URL, timeout=60)
        resp.raise_for_status()
        manifest = resp.json()

        versions_list = manifest.get("versions", [])
        version_entry = next((v for v in versions_list if v.get("id") == version), None)
        if version_entry is None:
            raise RuntimeError(f"Версия {version} не найдена")

        cb("Получение метаданных версии...", 0, 0, 0)
        resp2 = requests.get(version_entry["url"], timeout=60)
        resp2.raise_for_status()
        version_json = resp2.json()
        vanilla_json_path.write_text(json.dumps(version_json, indent=2), encoding="utf-8")

    if not vanilla_jar.exists():
        jar_url = version_json.get("downloads", {}).get("client", {}).get("url")
        if not jar_url:
            raise RuntimeError("Нет URL client JAR")
        download_file(jar_url, vanilla_jar, "Скачивание Minecraft", progress=cb)

    ensure_asset_index(version_json, game_dir, progress=cb)
    return version_json


# ─── Assets ────────────────────────────────────────────

def ensure_asset_index(version_json: dict, game_dir: Path, progress: ProgressCB = None):
    cb = progress or _noop
    indexes_dir = game_dir / "assets" / "indexes"
    objects_dir = game_dir / "assets" / "objects"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    objects_dir.mkdir(parents=True, exist_ok=True)

    asset_index = version_json.get("assetIndex", {})
    idx_id = asset_index.get("id", "17")
    index_path = indexes_dir / f"{idx_id}.json"

    if index_path.exists():
        index_data = json.loads(index_path.read_bytes())
    else:
        url = asset_index.get("url")
        if not url:
            raise RuntimeError("Нет URL asset index")
        cb("Скачивание индекса ресурсов...", 0, 0, 0)
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        index_path.write_bytes(resp.content)
        index_data = resp.json()

    cb("Проверка ресурсов...", 0, 0, 0)
    objects = index_data.get("objects", {})

    missing = []
    for _, val in objects.items():
        h = val.get("hash", "")
        if h:
            prefix = h[:2]
            obj_path = objects_dir / prefix / h
            if not obj_path.exists():
                missing.append((h, obj_path))

    if not missing:
        return

    total = len(missing)

    def _download_asset(item):
        h, path = item
        prefix = h[:2]
        url = f"https://resources.download.minecraft.net/{prefix}/{h}"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception:
            pass

    downloaded = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
        futures = {pool.submit(_download_asset, item): item for item in missing}
        for future in concurrent.futures.as_completed(futures):
            downloaded += 1
            if downloaded % 50 == 0 or downloaded == total:
                pct = downloaded / total * 100
                cb(f"Ресурсы: {downloaded}/{total}", downloaded, total, pct)


# ─── Libraries ─────────────────────────────────────────

def ensure_libraries(game_dir: Path, version_json: dict, progress: ProgressCB = None):
    cb = progress or _noop
    libs_dir = game_dir / "libraries"
    libs_dir.mkdir(parents=True, exist_ok=True)

    os_name_map = {"Linux": "linux", "Darwin": "osx", "Windows": "windows"}
    os_name = os_name_map.get(platform.system(), platform.system().lower())
    native_classifier = {"linux": "natives-linux", "osx": "natives-osx", "windows": "natives-windows"}.get(os_name, "natives-windows")

    libs = version_json.get("libraries", [])
    for lib in libs:
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
                download_file(url, dest, "Библиотеки", progress=cb)

        classifiers = lib.get("downloads", {}).get("classifiers", {})
        native = classifiers.get(native_classifier, {})
        n_path = native.get("path")
        n_url = native.get("url")
        if n_path and n_url:
            dest = libs_dir / n_path
            if not dest.exists():
                download_file(n_url, dest, "Нативные библиотеки", progress=cb)


# ─── NeoForge ──────────────────────────────────────────

def ensure_neoforge(game_dir: Path, java_path: str, version: str, urls: list, progress: ProgressCB = None) -> str:
    cb = progress or _noop
    existing = detect_installed_neoforge(game_dir, version)
    if existing:
        neo_json_path = game_dir / "versions" / existing / f"{existing}.json"
        if neo_json_path.exists():
            neo_json = read_json(neo_json_path)
            ensure_libraries(game_dir, neo_json, progress=cb)
            return existing

    installer_path = game_dir / ".neoforge_installer.jar"
    download_with_fallback(urls, installer_path, "Скачивание NeoForge", progress=cb)

    expected_id = read_install_profile_version(installer_path) or f"neoforge-{version}"

    result = subprocess.run(
        [java_path, "-jar", str(installer_path), "--install-client", str(game_dir)],
        cwd=str(game_dir),
    )

    if installer_path.exists():
        os.remove(installer_path)

    if result.returncode != 0:
        raise RuntimeError(f"NeoForge Installer ошибка (код {result.returncode})")

    final_id = expected_id
    neo_json_path = game_dir / "versions" / final_id / f"{final_id}.json"

    if not neo_json_path.exists():
        found = detect_installed_neoforge(game_dir, version)
        if found:
            final_id = found
            neo_json_path = game_dir / "versions" / final_id / f"{final_id}.json"

    neo_json = read_json(neo_json_path)
    ensure_libraries(game_dir, neo_json, progress=cb)
    return final_id


# ─── Утилиты ──────────────────────────────────────────

def clean_mods_folder(game_dir: Path):
    mods_dir = game_dir / "mods"
    if mods_dir.exists():
        for entry in mods_dir.iterdir():
            if entry.is_file() and entry.suffix == ".jar":
                entry.unlink()


def build_classpath(neo_json: dict, vanilla_json: dict, libs_dir: Path) -> str:
    classpath = []
    for j in [neo_json, vanilla_json]:
        for lib in j.get("libraries", []):
            path = lib.get("downloads", {}).get("artifact", {}).get("path")
            if path:
                jar = libs_dir / path
                if jar.exists():
                    s = str(jar)
                    if s not in classpath:
                        classpath.append(s)
    sep = ";" if platform.system() == "Windows" else ":"
    return sep.join(classpath)
