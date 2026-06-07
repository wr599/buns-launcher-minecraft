"""
Java — автопоиск, скачивание и распаковка JRE нужной версии.
Все функции принимают progress callback вместо глобальной функции.
"""
import glob
import os
import platform
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable, Optional

from backend.downloader import download_with_fallback, ProgressCB


def _noop(*_a, **_kw):
    pass


def get_jre_binary(runtime_dir: Path) -> Path:
    system = platform.system()
    if system == "Darwin":
        return runtime_dir / "Contents" / "Home" / "bin" / "java"
    elif system == "Windows":
        return runtime_dir / "bin" / "java.exe"
    else:
        return runtime_dir / "bin" / "java"


def _get_java_major_version(java_bin: str) -> int | None:
    """Возвращает мажорную версию Java (например 21), или None."""
    try:
        result = subprocess.run(
            [java_bin, "-version"],
            capture_output=True, text=True, timeout=15,
        )
        text = result.stdout + result.stderr
        m = re.search(r'version "(\d+)', text)
        if m:
            ver = int(m.group(1))
            if ver > 1:
                return ver
            m2 = re.search(r'version "1\.(\d+)', text)
            return int(m2.group(1)) if m2 else None
    except Exception:
        pass
    return None


def check_java_version(java_bin: Path, version: str) -> bool:
    try:
        result = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True, text=True, timeout=15,
        )
        text = result.stdout + result.stderr
        return f'version "{version}' in text or f'version "1.{version}' in text
    except Exception:
        return False


def find_system_java(required_major: int | None = None) -> str | None:
    """Ищет Java в JAVA_HOME, PATH и стандартных директориях."""
    is_windows = platform.system() == "Windows"
    exe = "java.exe" if is_windows else "java"
    candidates: list[str] = []

    # JAVA_HOME
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(os.path.join(java_home, "bin", exe))

    # PATH
    java_in_path = shutil.which("java")
    if java_in_path:
        candidates.append(java_in_path)

    # Windows: Program Files
    if is_windows:
        for pf in [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]:
            if not pf:
                continue
            for pattern in [
                os.path.join(pf, "Java", "jdk-*", "bin", exe),
                os.path.join(pf, "Java", "jre-*", "bin", exe),
                os.path.join(pf, "Eclipse Adoptium", "jdk-*", "bin", exe),
                os.path.join(pf, "Microsoft", "jdk-*", "bin", exe),
                os.path.join(pf, "Zulu", "zulu-*", "bin", exe),
                os.path.join(pf, "BellSoft", "LibericaJDK-*", "bin", exe),
                os.path.join(pf, "Amazon Corretto", "jdk*", "bin", exe),
            ]:
                candidates.extend(sorted(glob.glob(pattern), reverse=True))

    for cand in candidates:
        if not os.path.isfile(cand):
            continue
        if required_major is not None:
            ver = _get_java_major_version(cand)
            if ver is None or ver < required_major:
                continue
        return cand

    return None


def extract_zip(zip_path: Path, dest: Path):
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)


def ensure_java(game_dir: Path, version: str, urls: list, progress: ProgressCB = None) -> str:
    """
    Гарантирует наличие Java нужной версии.
    1) Скачанная ранее JRE  2) Системная Java  3) Скачать
    """
    cb = progress or _noop
    runtime_dir = game_dir / "runtime" / f"jre-{version}"
    java_bin = get_jre_binary(runtime_dir)

    # 1. Уже скачанная
    if java_bin.exists() and check_java_version(java_bin, version):
        cb(f"Java {version} найдена (скачанная ранее)", 0, 0, 0)
        return str(java_bin)

    # 2. Системная
    try:
        required_major = int(version.split(".")[0])
    except (ValueError, IndexError):
        required_major = None

    cb("Поиск Java в системе...", 0, 0, 0)
    system_java = find_system_java(required_major)
    if system_java:
        cb(f"Найдена системная Java: {system_java}", 0, 0, 0)
        return system_java

    # 3. Скачивание
    cb(f"Скачивание Java {version}...", 0, 0, 0)
    is_windows = platform.system() == "Windows"
    archive_name = ".jre.zip" if is_windows else ".jre.tar.gz"
    archive_path = game_dir / archive_name

    download_with_fallback(urls, archive_path, f"Скачивание Java {version}", progress=cb)
    cb("Установка Java...", 0, 0, 0)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if is_windows:
        extract_zip(archive_path, runtime_dir)
    else:
        subprocess.run(
            ["tar", "-xzf", str(archive_path), "-C", str(runtime_dir), "--strip-components=1"],
            check=True,
        )

    if archive_path.exists():
        os.remove(archive_path)

    if not java_bin.exists():
        raise RuntimeError("Java не найдена после установки")

    if not is_windows:
        os.chmod(str(java_bin), 0o755)

    return str(java_bin)
