# Сборка BunLauncher

Инструкция для разработчиков, собирающих оффлайн-bundle, standalone-исполняемый файл и Windows-инсталлятор.

## Обзор pipeline

```
manifest.json
     │
     ▼
build_bundle.py  ──►  bundle.tar.xz  (Minecraft + Java + NeoForge + модпак)
     │
     ▼
PyInstaller      ──►  dist/BunLauncher.exe
     │
     ▼
Inno Setup       ──►  installer_output/BunLauncher_Setup.exe
```

Все шаги можно выполнить одной командой:

```bash
python build_all.py
```

## Предварительные требования

### Общие

- Python 3.10+
- Зависимости: `pip install -r requirements.txt`
- PyInstaller: `pip install pyinstaller`

### Только для Windows-инсталлятора

- [Inno Setup 6](https://jrsoftware.org/isdl.php)
- Путь по умолчанию: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`

## Шаг 1: Сборка bundle

```bash
python build_bundle.py
```

Скрипт:

1. Читает `manifest.json` из корня репозитория
2. Скачивает Minecraft (vanilla), ассеты, библиотеки
3. Скачивает и устанавливает NeoForge
4. Скачивает архив модпака
5. Скачивает JRE (Temurin) для текущей платформы
6. Упаковывает всё в `bundle.tar.xz` (LZMA2)

**Требуется интернет.** Размер bundle — несколько сотен МБ.

### manifest.json

Ключевые поля:

| Поле | Описание |
|------|----------|
| `minecraft_version` | Версия vanilla Minecraft |
| `neoforge_version` | Версия NeoForge |
| `java_version` | Требуемая major-версия Java |
| `java_windows` / `java_linux` / `java_macos` | URL и SHA256 JRE для каждой ОС |
| `neoforge_urls` | URL installer JAR NeoForge |
| `neoforge_sha256` | SHA256 installer-а |
| `archive_urls` | URL архива модпака |
| `archive_sha256` | SHA256 модпака |
| `archive_size` | Ожидаемый размер модпака (байты) |

После изменения `manifest.json` пересоберите bundle.

## Шаг 2: PyInstaller

```bash
python -m PyInstaller BunLauncher.spec
```

Результат: `dist/BunLauncher.exe`

Spec-файл включает в сборку:

- `run.py` — точка входа
- `bundle.tar.xz` — оффлайн-данные
- `assets/` — изображения интерфейса

Флаги:

- `console=False` — без консольного окна
- `upx=True` — сжатие UPX

## Шаг 3: Inno Setup

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Результат: `installer_output/BunLauncher_Setup.exe`

Инсталлятор:

- Не требует прав администратора (`PrivilegesRequired=lowest`)
- Поддерживает русский и английский языки
- Показывает лицензию GPL-3.0

## Флаги build_all.py

```bash
python build_all.py --skip-bundle      # bundle уже собран
python build_all.py --skip-exe         # exe уже собран
python build_all.py --skip-installer   # без Inno Setup
```

## Сборка на Linux / macOS

- `build_bundle.py` работает на всех платформах
- PyInstaller создаёт бинарник для текущей ОС
- Inno Setup доступен только на Windows — используйте `--skip-installer` на других ОС

## Типичные проблемы

### bundle.tar.xz не найден при сборке exe

Сначала выполните `python build_bundle.py`. Файл должен лежать в корне репозитория.

### PyInstaller не находит PySide6

```bash
pip install PySide6 pyinstaller
```

### Inno Setup не найден

Установите Inno Setup 6 или запустите с `--skip-installer` и распространяйте `dist/BunLauncher.exe` напрямую.

### Ошибка SHA256 при сборке bundle

URL в `manifest.json` мог устареть. Обновите URL и хеши для Java, NeoForge или модпака.

## Размеры артефактов (ориентировочно)

| Артефакт | Размер |
|----------|--------|
| `bundle/` (распакованный) | ~800 MB |
| `bundle.tar.xz` | ~400 MB |
| `dist/BunLauncher.exe` | ~450 MB |
| `BunLauncher_Setup.exe` | ~450 MB |

Точные значения зависят от версии модпака и Minecraft.
