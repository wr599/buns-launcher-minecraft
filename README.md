# BunLauncher

**BunLauncher** — десктопный лаунчер Minecraft с поддержкой NeoForge и модпаков. Написан на Python, использует PySide6 (Qt6) для интерфейса. Работает оффлайн после первоначальной установки.

> **Важно:** BunLauncher не связан с Mojang Studios или Microsoft. Minecraft® — зарегистрированная торговая марка Mojang Synergies AB.

## Возможности

- Графический интерфейс на Qt6 с анимациями и настройками
- Оффлайн-установка: Minecraft, Java, NeoForge и модпак из одного bundle
- Автоматический поиск и установка Java (Temurin)
- Проверка целостности файлов (SHA256)
- Настройки памяти, разрешения, JVM-аргументов, путей
- Сборка в standalone `.exe` и Windows-инсталлятор

## Требования

| Компонент | Версия |
|-----------|--------|
| Python | 3.10+ |
| ОС | Windows 10+, Linux, macOS |

### Python-зависимости

```
requests
psutil
Pillow
PySide6
```

## Быстрый старт

### Запуск из исходников

```bash
git clone https://github.com/milkycloud-dev/buns-launcher-minecraft.git
cd buns-launcher-minecraft
pip install -r requirements.txt
python run.py
```

При первом запуске откроется мастер установки. Файлы игры по умолчанию сохраняются в:

- **Windows:** `%APPDATA%\BunLauncher`
- **Linux:** `~/BunLauncher`
- **macOS:** `~/BunLauncher`

### Готовый инсталлятор (Windows)

Соберите или скачайте `BunLauncher_Setup.exe` из релизов. Подробности сборки — в [docs/BUILD.md](docs/BUILD.md).

## Структура проекта

```
buns-launcher-minecraft/
├── run.py                 # Точка входа: GUI + оффлайн-установка + запуск игры
├── manifest.json          # Версии Minecraft, NeoForge, Java и URL-ы для bundle
├── requirements.txt       # Python-зависимости
├── assets/                # Логотип и фоновые изображения
├── backend/               # Модульный backend для онлайн-установки
│   ├── config.py          # Конфигурация launcher_config.json
│   ├── downloader.py      # Загрузка файлов с прогрессом
│   ├── java.py            # Поиск и установка Java
│   ├── launcher.py        # Оркестратор install_and_play / launch_game
│   ├── manifest.py        # Получение удалённого манифеста
│   ├── minecraft.py       # Vanilla Minecraft + NeoForge
│   └── security.py        # Проверка SHA256
├── build_bundle.py        # Сборка оффлайн-bundle (нужен интернет)
├── build_all.py           # Полный pipeline: bundle → exe → installer
├── BunLauncher.spec       # Конфигурация PyInstaller
├── installer.iss          # Скрипт Inno Setup
└── docs/                  # Подробная документация
```

## Конфигурация

Настройки хранятся в `{game_dir}/launcher_config.json`. Полный список параметров — в [docs/CONFIG.md](docs/CONFIG.md).

Основные параметры:

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `username` | `Player` | Никнейм (3–16 символов, `a-z`, `0-9`, `_`) |
| `memory_mb` | `4096` | Объём RAM для JVM |
| `width` / `height` | `854` / `480` | Разрешение окна |
| `fullscreen` | `false` | Полноэкранный режим |
| `game_dir` | *(пусто)* | Папка игры (пусто = `%APPDATA%\BunLauncher`) |
| `java_path` | *(пусто)* | Путь к `java` (пусто = автоопределение) |
| `jvm_args` | *(пусто)* | Дополнительные JVM-аргументы |

## Сборка

Кратко:

```bash
# 1. Собрать оффлайн-bundle (нужен интернет, ~30 мин)
python build_bundle.py

# 2. Собрать exe + инсталлятор (Windows)
python build_all.py
```

Подробная инструкция: [docs/BUILD.md](docs/BUILD.md).

## Архитектура

Проект состоит из двух слоёв:

1. **`run.py`** — монолитное GUI-приложение с встроенной логикой оффлайн-установки и запуска
2. **`backend/`** — переиспользуемая библиотека для онлайн-установки (скачивание с Mojang CDN, NeoForge Maven и т.д.)

Подробнее: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Участие в разработке

См. [CONTRIBUTING.md](CONTRIBUTING.md).

## Лицензия

Проект распространяется под лицензией [GNU General Public License v3.0](LICENSE).

```
Copyright (C) 2025-2026 Milkycloud Dev
```

### Сторонние компоненты

- **Minecraft** — собственность Mojang Studios / Microsoft. Для игры требуется лицензия.
- **NeoForge** — LGPL-2.1
- **Eclipse Temurin (OpenJDK)** — GPL-2.0 with Classpath Exception
- **PySide6 / Qt6** — LGPL-3.0

Контент модпака может распространяться на отдельных условиях — уточняйте у авторов модпака.

## Ссылки

- [Репозиторий](https://github.com/milkycloud-dev/buns-launcher-minecraft)
- [NeoForge](https://neoforged.net/)
- [Eclipse Temurin](https://adoptium.net/)
