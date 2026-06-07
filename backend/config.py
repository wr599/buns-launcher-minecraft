"""
Конфигурация лаунчера — чтение/запись launcher_config.json.
Все настройки (включая новые) хранятся здесь.
"""
import json
import platform
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "username": "Player",
    "memory_mb": 4096,
    "width": 854,
    "height": 480,
    "jvm_args": "",
    "fullscreen": False,
    "auto_connect": False,
    "game_dir": "",          # пустая строка = стандартная папка .minecraft
}


def get_minecraft_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("APPDATA", "")) / ".minecraft"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "minecraft"
    else:
        return Path.home() / ".minecraft"


def get_config_path() -> Path:
    return get_minecraft_dir() / "launcher_config.json"


def get_config() -> dict:
    """Читает конфиг. Если файла нет или в нём не хватает ключей — дополняет дефолтами."""
    path = get_config_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    # Дополняем недостающие ключи дефолтами
    merged = {**DEFAULT_CONFIG, **data}
    return merged


def save_config(config: dict):
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def effective_game_dir(config: dict) -> Path:
    """Возвращает папку игры: либо пользовательскую, либо стандартную."""
    d = config.get("game_dir", "").strip()
    if d:
        return Path(d)
    return get_minecraft_dir()
