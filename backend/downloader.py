"""
Загрузка файлов с прогрессом.
Вместо глобальной функции используется callback, переданный вызывающим кодом.
"""
import os
import time
import requests
from pathlib import Path
from typing import Callable, Optional

# Тип callback: (status_text, downloaded_bytes, total_bytes, percent)
ProgressCB = Optional[Callable[[str, int, int, float], None]]


def _default_progress(status: str, downloaded: int = 0, total: int = 0, percent: float = 0.0):
    if total > 0:
        print(f"[BunLauncher] {status} — {percent:.1f}%")
    else:
        print(f"[BunLauncher] {status}")


def download_file(url: str, dest: Path, status_text: str, progress: ProgressCB = None) -> None:
    cb = progress or _default_progress
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    dest.parent.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    last_emit = time.time()

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            now = time.time()
            if now - last_emit >= 0.15:
                pct = (downloaded / total * 100) if total > 0 else 0
                cb(f"{status_text} ({downloaded / 1_048_576:.1f} MB)", downloaded, total, pct)
                last_emit = now


def download_with_fallback(urls: list, dest: Path, status_text: str, progress: ProgressCB = None) -> None:
    cb = progress or _default_progress
    if not urls:
        raise RuntimeError("Список источников загрузки пуст")

    last_error = ""
    for i, url in enumerate(urls):
        cb(f"{status_text} (источник {i + 1})", 0, 0, 0)
        try:
            download_file(url, dest, status_text, progress=cb)
            return
        except Exception as e:
            print(f"Ошибка загрузки с {url}: {e}")
            last_error = str(e)
            if dest.exists():
                os.remove(dest)

    raise RuntimeError(f"Не удалось скачать файл. Последняя ошибка: {last_error}")
