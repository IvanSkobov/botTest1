# Telegram Bot

Простой Telegram бот‑модератор.

## Установка

1. Убедитесь, что у вас установлен Python 3.10 или выше.
2. Создайте виртуальное окружение:
   ```bash
   python -m venv .venv
   ```
3. Активируйте виртуальное окружение:
   - На Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - На macOS и Linux:
     ```bash
     source .venv/bin/activate
     ```
4. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

## Настройка

1. Получите токен у @BotFather в Telegram.
2. Установите переменную окружения `BOT_TOKEN`:
   - PowerShell:
     ```powershell
     $env:BOT_TOKEN="ВАШ_ТОКЕН"
     ```
   - Bash:
     ```bash
     export BOT_TOKEN="ВАШ_ТОКЕН"
     ```

## Запуск

```bash
python src/bot.py
```

## Команды бота (для админов)
- `/ping` — проверка связи
- `/del` — удалить сообщение (нужно ответить на него)
- `/mute <длительность>` — временный мут (нужно ответить). Примеры: `30`, `15m`, `2h`, `1d`
- `/ban` — бан (нужно ответить)
- `/unban <user_id>` — разбан по ID или ответом на сообщение

## Структура проекта

```
botTest/
├── src/
│   └── bot.py
├── docs/
├── tests/
├── requirements.txt
├── .gitignore
└── README.md
```\