"""
Безопасность — проверка SHA256 и размера файла.
"""
import hashlib
from pathlib import Path


def verify_file(path: Path, expected_sha256: str, expected_size: int | None = None) -> bool:
    if not path.exists():
        return False
    if expected_size is not None and path.stat().st_size != expected_size:
        return False
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest() == expected_sha256
