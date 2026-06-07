"""
Оркестратор: install_and_play + launch_game.
Принимает progress callback и передаёт его по цепочке.
"""
import os
import platform
import subprocess
from pathlib import Path

import psutil

from backend.config import get_config, save_config, effective_game_dir
from backend.manifest import fetch_manifest
from backend.java import ensure_java, extract_zip
from backend.minecraft import (
    ensure_vanilla, ensure_neoforge, clean_mods_folder,
    build_classpath, read_json,
)
from backend.downloader import download_with_fallback, ProgressCB
from backend.security import verify_file

MANIFEST_URL = "https://drive.usercontent.google.com/uc?id=12bGhgtLvC7vzpc6VGBWI4iISAQBepIjP&export=download"


def _noop(*_a, **_kw):
    pass


def check_mc_running() -> bool:
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = proc.info.get("name", "").lower()
            if "java" in name or "javaw" in name:
                cmdline = proc.info.get("cmdline", [])
                cmd_str = " ".join(cmdline) if cmdline else ""
                if "net.minecraft.client.main.Main" in cmd_str or "cpw.mods.bootstraplauncher.BootstrapLauncher" in cmd_str:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


def install_and_play(username: str, progress: ProgressCB = None) -> dict:
    cb = progress or _noop

    valid = 3 <= len(username) <= 16 and all(c.isalnum() or c == "_" for c in username)
    if not valid:
        raise ValueError("Никнейм: 3-16 символов, только a-z, 0-9, _")

    if check_mc_running():
        raise RuntimeError("Minecraft уже запущен")

    config = get_config()
    config["username"] = username
    save_config(config)

    cb("Получение манифеста...", 0, 0, 0)
    manifest = fetch_manifest(MANIFEST_URL)
    game_dir = effective_game_dir(config)

    java_path = ensure_java(
        game_dir,
        manifest.get("java_version"),
        manifest.get("java_urls", []),
        progress=cb,
    )

    ensure_vanilla(game_dir, manifest.get("minecraft_version"), progress=cb)

    cb("Проверка NeoForge...", 0, 0, 0)
    neo_id = ensure_neoforge(
        game_dir, java_path,
        manifest.get("neoforge_version"),
        manifest.get("neoforge_urls", []),
        progress=cb,
    )

    # Модпак
    modpack_hash_file = game_dir / ".modpack_hash"
    archive_path = game_dir / ".modpack_cache.zip"
    needs_update = True

    if modpack_hash_file.exists():
        saved_hash = modpack_hash_file.read_text(encoding="utf-8").strip()
        if saved_hash == manifest.get("archive_sha256"):
            needs_update = False

    if needs_update:
        cb("Скачивание модов...", 0, 0, 0)
        download_with_fallback(
            manifest.get("archive_urls", []),
            archive_path,
            "Загрузка модов",
            progress=cb,
        )

        if not verify_file(archive_path, manifest.get("archive_sha256"), manifest.get("archive_size")):
            if archive_path.exists():
                os.remove(archive_path)
            raise RuntimeError("Ошибка проверки целостности модпака")

        cb("Распаковка модов...", 0, 0, 0)
        clean_mods_folder(game_dir)
        extract_zip(archive_path, game_dir)
        modpack_hash_file.write_text(manifest.get("archive_sha256", ""), encoding="utf-8")

    cb("Запуск игры...", 0, 0, 100)
    return launch_game(config, game_dir, java_path, neo_id, manifest.get("minecraft_version"))


# ─── Сборка аргументов и запуск ────────────────────────

def _collect_json_args(arr: list, substitute, out: list):
    os_name_map = {"Linux": "linux", "Darwin": "osx", "Windows": "windows"}
    os_name = os_name_map.get(platform.system(), platform.system().lower())

    for item in arr:
        if isinstance(item, str):
            out.append(substitute(item))
        elif isinstance(item, dict):
            allowed = True
            rules = item.get("rules")
            if rules:
                res = True
                for rule in rules:
                    action = rule.get("action", "allow")
                    matches = True
                    os_obj = rule.get("os")
                    if os_obj and os_obj.get("name"):
                        if os_obj["name"] != os_name:
                            matches = False
                    if matches:
                        res = (action == "allow")
                allowed = res
            if not allowed:
                continue
            val = item.get("value")
            if isinstance(val, str):
                out.append(substitute(val))
            elif isinstance(val, list):
                for v in val:
                    if isinstance(v, str):
                        out.append(substitute(v))


def launch_game(config: dict, game_dir: Path, java_path: str, neo_id: str, mc_version: str):
    libs_dir = game_dir / "libraries"
    assets_dir = game_dir / "assets"
    natives_dir = game_dir / "versions" / neo_id / "natives"

    neo_json_path = game_dir / "versions" / neo_id / f"{neo_id}.json"
    van_json_path = game_dir / "versions" / mc_version / f"{mc_version}.json"

    neo_json = read_json(neo_json_path)
    try:
        van_json = read_json(van_json_path)
    except Exception:
        van_json = {}

    main_class = neo_json.get("mainClass", "cpw.mods.bootstraplauncher.BootstrapLauncher")
    asset_index = van_json.get("assetIndex", {}).get("id", "17")
    cp = build_classpath(neo_json, van_json, libs_dir)
    cp_sep = ";" if platform.system() == "Windows" else ":"

    args = []

    # Память и Оптимизация (FPS Boost)
    args.append(f"-Xmx{config.get('memory_mb', 4096)}M")
    args.append(f"-Xms{config.get('memory_mb', 4096)}M")
    args.extend([
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        "-XX:G1NewSizePercent=30",
        "-XX:G1MaxNewSizePercent=40",
        "-XX:G1HeapRegionSize=8M",
        "-XX:G1ReservePercent=20",
        "-XX:G1HeapWastePercent=5",
        "-XX:G1MixedGCCountTarget=4",
        "-XX:InitiatingHeapOccupancyPercent=15",
        "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5",
        "-XX:SurvivorRatio=32",
        "-XX:+PerfDisableSharedMem",
        "-XX:MaxTenuringThreshold=1"
    ])
    args.append(f"-Djava.library.path={natives_dir}")

    # Пользовательские JVM-аргументы
    jvm_extra = config.get("jvm_args", "").strip()
    if jvm_extra:
        args.extend(jvm_extra.split())

    def substitute(s: str) -> str:
        s = s.replace("${version_name}", neo_id)
        s = s.replace("${game_directory}", str(game_dir))
        s = s.replace("${assets_root}", str(assets_dir))
        s = s.replace("${assets_index_name}", asset_index)
        s = s.replace("${library_directory}", str(libs_dir))
        s = s.replace("${classpath_separator}", cp_sep)
        s = s.replace("${natives_directory}", str(natives_dir))
        s = s.replace("${classpath}", cp)
        return s

    jvm_args = neo_json.get("arguments", {}).get("jvm")
    if jvm_args:
        _collect_json_args(jvm_args, substitute, args)

    if not any(a in ("-cp", "-classpath") for a in args) and not any("legacyClassPath" in a for a in args):
        args.extend(["-cp", cp])

    args.append(main_class)

    game_args = neo_json.get("arguments", {}).get("game")
    van_game_args = van_json.get("arguments", {}).get("game")

    if game_args:
        _collect_json_args(game_args, substitute, args)
    elif van_game_args:
        _collect_json_args(van_game_args, substitute, args)

    joined = " ".join(args)
    if "--username" not in joined:
        args.extend(["--username", config.get("username", "Player")])
    if "--version" not in joined:
        args.extend(["--version", neo_id])
    if "--gameDir" not in joined:
        args.extend(["--gameDir", str(game_dir)])
    if "--assetsDir" not in joined:
        args.extend(["--assetsDir", str(assets_dir)])
    if "--assetIndex" not in joined:
        args.extend(["--assetIndex", asset_index])
    if "--uuid" not in joined:
        args.extend(["--uuid", "00000000-0000-0000-0000-000000000000"])
    if "--accessToken" not in joined:
        args.extend(["--accessToken", "0"])
    if "--userType" not in joined:
        args.extend(["--userType", "offline"])

    args.extend(["--width", str(config.get("width", 854))])
    args.extend(["--height", str(config.get("height", 480))])

    # Полноэкранный режим
    if config.get("fullscreen"):
        args.append("--fullscreen")

    try:
        subprocess.Popen(
            [java_path] + args,
            cwd=str(game_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"success": True}
    except Exception as e:
        raise RuntimeError(f"Ошибка запуска: {e}")
