# Участие в разработке

Спасибо за интерес к BunLauncher! Ниже — краткие правила для контрибьюторов.

## Как начать

1. Форкните [репозиторий](https://github.com/milkycloud-dev/buns-launcher-minecraft)
2. Создайте ветку: `git checkout -b feature/my-feature`
3. Внесите изменения
4. Убедитесь, что `python run.py` запускается без ошибок
5. Откройте Pull Request с описанием изменений

## Стиль кода

- Python 3.10+, type hints приветствуются
- Комментарии и UI-тексты — на русском (как в существующем коде)
- Следуйте стилю окружающего кода: не рефакторите несвязанные участки
- Минимальный diff: одна задача — один PR

## Структура изменений

| Тип изменения | Куда вносить |
|---------------|--------------|
| GUI, оффлайн-установка, запуск игры | `run.py` |
| Онлайн-установка, API backend | `backend/` |
| Версии Minecraft/NeoForge/модпака | `manifest.json` |
| Сборка bundle / exe / installer | `build_*.py`, `*.spec`, `installer.iss` |
| Документация | `README.md`, `docs/` |

## Обновление manifest.json

При смене версий Minecraft, NeoForge, Java или модпака:

1. Обновите URL и SHA256 в `manifest.json`
2. Пересоберите bundle: `python build_bundle.py`
3. Проверьте установку и запуск локально
4. Опишите изменения в PR

## Сборка и тестирование

```bash
pip install -r requirements.txt
python run.py                    # GUI-тест
python build_bundle.py           # только при изменении manifest
python build_all.py --skip-bundle  # сборка exe без перекачки
```

Подробнее: [docs/BUILD.md](docs/BUILD.md).

## Сообщения об ошибках

При создании issue укажите:

- ОС и версию Python
- Шаги воспроизведения
- Текст ошибки или скриншот
- Содержимое `launcher_config.json` (без личных данных)

## Лицензия

Отправляя PR, вы соглашаетесь, что ваш вклад распространяется под [GPL-3.0](LICENSE).

## Контакты

- Issues: [GitHub Issues](https://github.com/milkycloud-dev/buns-launcher-minecraft/issues)
- Обсуждения: [GitHub Discussions](https://github.com/milkycloud-dev/buns-launcher-minecraft/discussions) (если включены)
