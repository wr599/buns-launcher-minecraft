# Конфигурация BunLauncher

Настройки хранятся в JSON-файле:

```
{game_dir}/launcher_config.json
```

По умолчанию `game_dir` = `%APPDATA%\BunLauncher` (Windows) или `~/BunLauncher` (Linux/macOS).

Файл создаётся автоматически при первом сохранении настроек. Недостающие ключи дополняются значениями по умолчанию.

## Все параметры

### Игра

| Ключ | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `username` | string | `"Player"` | Никнейм игрока. 3–16 символов: `a-z`, `A-Z`, `0-9`, `_` |
| `width` | int | `854` | Ширина окна Minecraft |
| `height` | int | `480` | Высота окна Minecraft |
| `fullscreen` | bool | `false` | Запуск в полноэкранном режиме |
| `close_on_launch` | bool | `false` | Закрыть лаунчер после старта игры |
| `auto_connect` | bool | `false` | Автоподключение к серверу |
| `server_ip` | string | `""` | IP сервера для автоподключения |

### Производительность

| Ключ | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `memory_mb` | int | `4096` | RAM для JVM (МБ). Доступные значения в GUI: 1024–16384 |
| `jvm_args` | string | `""` | Дополнительные аргументы Java VM |
| `max_threads` | int | `8` | Потоки для параллельной загрузки ассетов |

### Пути

| Ключ | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `game_dir` | string | `""` | Папка с файлами игры. Пустая строка = стандартная папка BunLauncher |
| `java_path` | string | `""` | Полный путь к `java` / `java.exe`. Пустая строка = автоопределение |

### Сеть

| Ключ | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `check_files` | bool | `true` | Проверять целостность файлов перед запуском |

### Дополнительно

| Ключ | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `show_console` | bool | `false` | Показывать консоль Java при запуске |

## Пример файла

```json
{
  "username": "Steve",
  "memory_mb": 6144,
  "width": 1920,
  "height": 1080,
  "jvm_args": "-XX:+UseG1GC",
  "fullscreen": false,
  "game_dir": "",
  "java_path": "",
  "close_on_launch": true,
  "auto_connect": false,
  "server_ip": "",
  "show_console": false,
  "check_files": true,
  "max_threads": 8
}
```

## manifest.json (системный)

Отдельный файл в корне репозитория и в `{game_dir}/manifest.json` после установки. Задаёт версии компонентов для сборки и установки:

```json
{
  "java_version": "21",
  "minecraft_version": "1.21.1",
  "neoforge_version": "21.1.216",
  "neoforge_urls": ["https://maven.neoforged.net/..."],
  "neoforge_sha256": "...",
  "archive_urls": ["https://..."],
  "archive_sha256": "...",
  "archive_size": 234016844
}
```

Этот файл редактируют разработчики при обновлении модпака или версий. Пользователям обычно не нужно его менять.

## backend/config.py vs run.py

Модуль `backend/config.py` использует другой путь по умолчанию — стандартную папку `.minecraft`:

| Модуль | Путь по умолчанию |
|--------|-------------------|
| `run.py` | `%APPDATA%\BunLauncher` |
| `backend/config.py` | `%APPDATA%\.minecraft` |

При использовании `backend/launcher.py` напрямую конфиг сохраняется в `.minecraft/launcher_config.json`.

## Сброс настроек

Удалите `launcher_config.json` из папки игры. При следующем запуске будут применены значения по умолчанию.

## Полная переустановка

1. Запустите `run.py`
2. Выберите «Переустановить» или «Удалить»
3. Либо вручную удалите папку `{game_dir}` и файл `.installed` из `%APPDATA%`
