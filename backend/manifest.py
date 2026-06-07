"""
Получение удалённого JSON-манифеста.
"""
import requests


def fetch_manifest(url: str) -> dict:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise RuntimeError(f"Ошибка при получении манифеста: {e}")
