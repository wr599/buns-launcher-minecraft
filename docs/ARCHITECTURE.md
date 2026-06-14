# Архитектура BunLauncher

## Обзор

BunLauncher — Python-приложение с двумя слоями:

```
┌─────────────────────────────────────────────────┐
│                   run.py                        │
│  PySide6 GUI · Installer Wizard · Game Launch   │
│  (оффлайн: bundle.tar.xz → game_dir)            │
└──────────────────────┬──────────────────────────┘
                       │ (независимые модули)
┌──────────────────────▼──────────────────────────┐
│                  backend/                       │
│  Онлайн-установка: Mojang CDN · NeoForge Maven  │
│  · Google Drive (манифест / модпак)             │
└─────────────────────────────────────────────────┘
```

`run.py` не импортирует `backend/` — логика установки и запуска продублирована/адаптирована для оффлайн-сценария. Модуль `backend/` предназначен для программного использования и онлайн-установки.

## Потоки данных

### Первый запуск (run.py)

```
InstallerWizard
    │
    ├─► Выбор пути установки
    ├─► Распаковка bundle.tar.xz → game_dir
    ├─► Создание .installed (маркер)
    └─► Ярлык на рабочем столе (Windows)
         │
         ▼
    BunLauncher (главное окно)
         │
         ├─► Ввод никнейма
         ├─► WorkerThread
         │       ├─► install_from_bundle() (если не установлено)
         │       └─► launch_game()
         └─► Запуск Minecraft (NeoForge BootstrapLauncher)
```

### Онлайн-установка (backend/launcher.py)

```
install_and_play(username)
    │
    ├─► fetch_manifest()          manifest.py
    ├─► ensure_java()             java.py
    ├─► ensure_vanilla()          minecraft.py  → Mojang CDN
    ├─► ensure_neoforge()         minecraft.py  → NeoForge installer
    ├─► download modpack          downloader.py → Google Drive
    ├─► verify_file()             security.py   → SHA256
    └─► launch_game()
```

## Модули backend/

| Модуль | Ответственность |
|--------|-----------------|
| `config.py` | Чтение/запись `launcher_config.json`, определение папки `.minecraft` |
| `manifest.py` | HTTP GET удалённого JSON-манифеста |
| `downloader.py` | Скачивание с прогрессом, fallback по списку URL |
| `java.py` | Поиск Java в PATH/JAVA_HOME, скачивание Temurin JRE |
| `minecraft.py` | Vanilla (version manifest, assets, libraries), NeoForge installer |
| `security.py` | Проверка SHA256 и размера файла |
| `launcher.py` | Оркестрация: `install_and_play()`, `launch_game()`, проверка запущенного MC |

## Ключевые файлы run.py

| Компонент | Назначение |
|-----------|------------|
| `InstallerWizard` | Мастер первого запуска с мини-игрой |
| `BunLauncher` | Главное окно: никнейм, кнопка Play, настройки |
| `SettingsDialog` | Вкладки: игра, производительность, пути, сеть, дополнительно |
| `WorkerThread` | Фоновая установка/запуск без блокировки UI |
| `install_from_bundle()` | Распаковка `bundle.tar.xz` или копирование `bundle/` |
| `launch_game()` | Сборка classpath, JVM-аргументов, запуск BootstrapLauncher |
| `find_game_version()` | Поиск NeoForge-версии в `versions/` |

## Запуск Minecraft (NeoForge)

1. Читается `{neo_id}.json` из `versions/`
2. Собирается classpath из `libraries/` (с дедупликацией версий)
3. Формируются `--ignoreList` для BootstrapLauncher (критично для Java 21)
4. Запускается `cpw.mods.bootstraplauncher.BootstrapLauncher`

## Хранение данных

```
{game_dir}/
├── .installed              # Маркер установки (путь к game_dir)
├── launcher_config.json    # Настройки пользователя
├── manifest.json           # Копия манифеста из bundle
├── assets/                 # Ресурсы Minecraft
├── libraries/              # JAR-зависимости
├── mods/                   # Моды из модпака
├── runtime/                # JRE (jre-21/)
└── versions/               # Vanilla + NeoForge JSON/JAR
    ├── 1.21.1/
    └── neoforge-21.1.216/
```

## Потоки и асинхронность

- GUI работает в главном Qt-потоке
- Установка и запуск игры — в `QThread` (`WorkerThread`, `InstallerThread`)
- Прогресс передаётся через Qt Signals (`progress`, `finished_ok`, `finished_err`)

## Безопасность

- Все скачиваемые файлы проверяются по SHA256 (`security.py`, manifest)
- Никнейм валидируется: 3–16 символов, `[a-zA-Z0-9_]`
- Перед запуском проверяется, не запущен ли уже Minecraft (`psutil`)

## Сборка и распространение

| Скрипт | Роль |
|--------|------|
| `build_bundle.py` | Создание оффлайн-архива |
| `build_all.py` | Полный pipeline |
| `BunLauncher.spec` | Конфигурация PyInstaller |
| `installer.iss` | Windows-инсталлятор (Inno Setup) |

Подробнее: [BUILD.md](BUILD.md).
