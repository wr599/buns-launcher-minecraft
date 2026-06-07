# BunLauncher

Лаунчер Minecraft на Python. Без браузера, без npm — только Python + tkinter.

## Запуск

```bash
pip install -r requirements.txt
python run.py
```

## Зависимости

- `requests` — загрузка файлов
- `psutil` — проверка запущенных процессов
- `Pillow` — отображение изображений в GUI

## Структура

```
├── run.py              — GUI лаунчера (tkinter)
├── requirements.txt    — Python-зависимости
├── assets/             — логотип и фон
└── backend/
    ├── config.py       — конфигурация (launcher_config.json)
    ├── downloader.py   — загрузка файлов с прогрессом
    ├── java.py         — автопоиск/установка Java
    ├── launcher.py     — установка и запуск Minecraft
    ├── manifest.py     — манифест модпака
    ├── minecraft.py    — Vanilla + NeoForge
    └── security.py     — проверка SHA256
```
