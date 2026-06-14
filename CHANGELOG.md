# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Unreleased]

### Added

- Полная документация проекта (`README.md`, `docs/`, `CONTRIBUTING.md`)
- Copyright-заголовок в `LICENSE` (GPL-3.0)
- `.gitignore` для Python- и build-артефактов

## [1.0.0] — 2026-06-14

### Added

- GUI-лаунчер на PySide6 (Qt6) с установщиком первого запуска
- Оффлайн-установка из `bundle.tar.xz` (Minecraft + NeoForge + модпак)
- Модульный backend для онлайн-установки (`backend/`)
- Сборка Windows-инсталлятора через PyInstaller + Inno Setup
- Скрипты сборки: `build_bundle.py`, `build_all.py`
