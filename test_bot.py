# test_bot.py - полный рабочий скрипт

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def telegram_admin(arguments: dict) -> dict:
    """
    Антиспам функция для smaiPL AI Assistant (с удалением сообщений)
    """
    import re
    import time
    from datetime import datetime

    # ============= СЕКРЕТНЫЙ КЛЮЧ ДЛЯ АДМИНОВ =============
    SECRET_KEY = "2024"  # ⚠️ ИЗМЕНИТЕ НА СВОЙ СЕКРЕТНЫЙ КЛЮЧ

    # Инициализация хранилища
    if not hasattr(telegram_admin, "_warns"):
        telegram_admin._warns = {}
        telegram_admin._messages = {}
        telegram_admin._timestamps = {}
        telegram_admin._banned = {}
        print("✅ Хранилища инициализированы")

    # Константы
    MAX_WARNS = 3
    FLOOD_TIME_WINDOW = 5.0
    FLOOD_MESSAGE_LIMIT = 3
    REPEATED_MESSAGE_LIMIT = 1
    MESSAGE_HISTORY_SIZE = 5

    BAD_WORDS = ["блять", "сука", "хуй", "пизда", "ебать", "нахер", "залупа", "мудак", "козел", "дебил"]

    SPAM_PATTERNS = [
        r"https?://", r"t\.me", r"@\w+", r"(.)\1{5,}", r"www\.",
        r"\d{10,}", r"\+?\d[\d\s\-\(\)]{8,}\d"
    ]

    def check_violation(text: str):
        if not text:
            return (None, None)
        text_lower = text.lower()
        for word in BAD_WORDS:
            if word in text_lower:
                return ("мат", word)
        for pattern in SPAM_PATTERNS:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    return ("спам/ссылка", pattern)
            except:
                continue
        return (None, None)

    def check_flood(user_id: str, current_time: float):
        timestamps = telegram_admin._timestamps.get(user_id)
        if timestamps is None:
            telegram_admin._timestamps[user_id] = [current_time]
            return False
        cutoff = current_time - FLOOD_TIME_WINDOW
        valid = [ts for ts in timestamps if ts > cutoff]
        if len(valid) >= FLOOD_MESSAGE_LIMIT:
            return True
        valid.append(current_time)
        telegram_admin._timestamps[user_id] = valid
        return False

    def check_repeated(user_id: str, text: str):
        if not text or len(text) < 3:
            return False
        text_lower = text.lower()
        messages = telegram_admin._messages.get(user_id, [])
        messages.append(text_lower)
        messages = messages[-MESSAGE_HISTORY_SIZE:]
        telegram_admin._messages[user_id] = messages
        return messages.count(text_lower) >= REPEATED_MESSAGE_LIMIT

    def add_warn(user_id: str, violation_type: str, detail: str):
        current = telegram_admin._warns.get(user_id, 0)
        new_warns = current + 1
        telegram_admin._warns[user_id] = new_warns
        print(f"⚠️ Варн {new_warns}/{MAX_WARNS} для {user_id} | {violation_type}")
        result = {"warns": new_warns, "max_warns": MAX_WARNS, "violation": violation_type}
        if new_warns >= MAX_WARNS:
            telegram_admin._warns[user_id] = 0
            telegram_admin._banned[user_id] = {"time": time.time(), "reason": violation_type}
            result["action"] = "ban"
            print(f"🔨 БАН для {user_id}")
        else:
            result["action"] = "warn"
        return result

    try:
        user_message = arguments.get("user_message", "")
        user_id = str(arguments.get("user_id", "unknown"))
        message_id = arguments.get("message_id")
        bot = arguments.get("bot")
        chat_id = arguments.get("chat_id")

        if not user_message or len(user_message.strip()) == 0:
            return {"answer": None}

        # ============= КОМАНДЫ =============
        if user_message.startswith("/"):
            # /stats - статистика (доступна всем)
            if user_message.startswith("/stats"):
                total = len(telegram_admin._warns)
                warns = sum(telegram_admin._warns.values())
                banned = len(telegram_admin._banned)
                return {"answer": f"📊 Статистика: {total} юзеров, {warns} варнов, {banned} банов"}

            # /check_user - проверка статуса (доступна всем)
            if user_message.startswith("/check_user"):
                if user_id in telegram_admin._banned:
                    return {"answer": "🔨 ВЫ ЗАБАНЕНЫ"}
                warns = telegram_admin._warns.get(user_id, 0)
                if warns == 0:
                    return {"answer": "✅ Вы активны. Нарушений нет."}
                return {"answer": f"⚠️ У вас {warns}/{MAX_WARNS} варнов"}

            # /get_warns - получить варны (доступна всем)
            if user_message.startswith("/get_warns"):
                target = user_id
                parts = user_message.split()
                if len(parts) > 1:
                    target = parts[1]
                warns = telegram_admin._warns.get(target, 0)
                return {"answer": f"⚠️ У пользователя {target} {warns}/{MAX_WARNS} варнов"}

            # /reset_warns - СБРОС ВАРНОВ
            if user_message.startswith("/reset_warns") and SECRET_KEY in user_message:
                import re
                ids = re.findall(r'\d+', user_message)
                target_id = ids[0] if ids else user_id

                old = telegram_admin._warns.get(target_id, 0)
                telegram_admin._warns[target_id] = 0
                if target_id in telegram_admin._banned:
                    del telegram_admin._banned[target_id]

                print(f"🔑 Админ {user_id} сбросил варны {target_id} (было: {old})")
                return {"answer": f"✅ Варны {target_id} сброшены (было: {old})"}

            if user_message.startswith("/reset_warns"):
                return {"answer": f"❌ Доступ запрещен! Используйте: /reset_warns {SECRET_KEY}"}

 
            # /unban - РАЗБАН (ТОЛЬКО С СЕКРЕТНЫМ КЛЮЧОМ!)
            if user_message.startswith("/unban"):
                # Убираем команду из строки, оставляем только аргументы
                args = user_message.replace("/unban", "").strip().split()

                print(f"DEBUG unban: full message='{user_message}'")
                print(f"DEBUG unban: args={args}")

                # Проверка наличия секретного ключа
                if len(args) < 1 or args[0] != SECRET_KEY:
                    return {"answer": f"❌ Доступ запрещен! Используйте: /unban {SECRET_KEY}"}

                # Определяем цель для разбана
                if len(args) >= 2:
                    target_id = args[1]
                else:
                    target_id = user_id

                # Разбан пользователя
                if target_id in telegram_admin._banned:
                    del telegram_admin._banned[target_id]
                    telegram_admin._warns[target_id] = 0

                    if bot and chat_id:
                        try:
                            bot.unban_chat_member(chat_id=chat_id, user_id=target_id)
                            print(f"🔑 Админ {user_id} разбанил {target_id} в Telegram")
                        except Exception as e:
                            print(f"Ошибка разбана в TG: {e}")

                    return {"answer": f"✅ Пользователь {target_id} разбанен"}
                else:
                    return {"answer": f"⚠️ Пользователь {target_id} не в бане"}

            # /help - помощь (доступна всем)
            if user_message.startswith("/help"):
                return {
                    "answer": "📚 Команды:\n/stats - статистика\n/check_user - мой статус\n/get_warns - получить варны\n\n🔒 Админ-команды:\n/reset_warns КЛЮЧ [ID] - сброс варнов\n/unban КЛЮЧ [ID] - разбан\n\n⚠️ 3 варна = бан"}

            return {"answer": None}

        # ============= АВТОМАТИЧЕСКАЯ ПРОВЕРКА =============

        # Проверка на бан
        if user_id in telegram_admin._banned:
            return {"answer": None}

        current_time = time.time()

        # Флуд
        if check_flood(user_id, current_time):
            if bot and message_id and chat_id:
                try:
                    bot.delete_message(chat_id=chat_id, message_id=message_id)
                    print(f"🗑️ Удалено флуд-сообщение от {user_id}")
                except Exception as e:
                    print(f"❌ Ошибка удаления: {e}")
            return {"answer": f"⛔ ФЛУД! Подождите {int(FLOOD_TIME_WINDOW)} секунд"}

        # Повтор
        if check_repeated(user_id, user_message):
            result = add_warn(user_id, "повтор", "")
            if bot and message_id and chat_id:
                try:
                    bot.delete_message(chat_id=chat_id, message_id=message_id)
                    print(f"🗑️ Удалено повторяющееся сообщение от {user_id}")
                except Exception as e:
                    print(f"❌ Ошибка удаления: {e}")
            if result["action"] == "ban":
                if bot and chat_id:
                    try:
                        bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                        print(f"🔨 Пользователь {user_id} забанен")
                    except Exception as e:
                        print(f"❌ Ошибка бана: {e}")
                return {"answer": f"⛔ БАН! Повтор сообщений"}
            return {"answer": f"⚠️ Варн {result['warns']}/{result['max_warns']} | Повтор сообщений"}

        # Мат/спам
        v_type, v_detail = check_violation(user_message)
        if v_type:
            result = add_warn(user_id, v_type, v_detail)
            if bot and message_id and chat_id:
                try:
                    bot.delete_message(chat_id=chat_id, message_id=message_id)
                    print(f"🗑️ Удалено сообщение с {v_type} от {user_id}: {user_message[:30]}")
                except Exception as e:
                    print(f"❌ Ошибка удаления: {e}")
            if result["action"] == "ban":
                if bot and chat_id:
                    try:
                        bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                        print(f"🔨 Пользователь {user_id} забанен за {v_type}")
                    except Exception as e:
                        print(f"❌ Ошибка бана: {e}")
                return {"answer": f"⛔ БАН! {v_type}"}
            return {"answer": f"⚠️ Варн {result['warns']}/{result['max_warns']} | {v_type}"}

        return {"answer": None}

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return {"answer": f"❌ Ошибка: {e}"}


# ============= ТЕЛЕГРАМ БОТ =============
class BotWrapper:
    """Обертка для передачи бота в функцию"""

    def __init__(self, bot):
        self.bot = bot

    def delete_message(self, chat_id, message_id):
        """Синхронная обертка для удаления сообщения"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.bot.delete_message(chat_id, message_id))
            else:
                loop.run_until_complete(self.bot.delete_message(chat_id, message_id))
        except Exception as e:
            print(f"Ошибка удаления: {e}")

    def ban_chat_member(self, chat_id, user_id):
        """Синхронная обертка для бана пользователя"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.bot.ban_chat_member(chat_id, user_id))
            else:
                loop.run_until_complete(self.bot.ban_chat_member(chat_id, user_id))
        except Exception as e:
            print(f"Ошибка бана: {e}")


# ============= ОБРАБОТЧИК СООБЩЕНИЙ (ИСПРАВЛЕННЫЙ) =============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех сообщений"""
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    user_message = update.effective_message.text or ""
    message_id = update.effective_message.message_id
    chat_id = str(update.effective_chat.id)

    print(f"\n📩 Сообщение от {user_name} ({user_id}): {user_message[:50]}")

    result = telegram_admin({
        "user_message": user_message,
        "user_id": user_id,
        "message_id": message_id,
        "chat_id": chat_id,
        "bot": BotWrapper(context.bot)
    })

    if result.get("answer"):
        print(f"🤖 Ответ: {result['answer'][:50]}")
        try:
            await context.bot.send_message(chat_id=chat_id, text=result["answer"])
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")


# ============= КОМАНДЫ (ИСПРАВЛЕННЫЕ - БЕЗ MARKDOWN) =============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🤖 Антиспам бот запущен!\n\n"
        "Я автоматически УДАЛЯЮ сообщения с:\n"
        "• Нецензурной лексикой\n"
        "• Спамом и ссылками\n"
        "• Флудом\n"
        "• Повтором сообщений\n\n"
        "Команды:\n"
        "/stats - статистика\n"
        "/check_user - проверить статус\n"
        "/help - помощь\n\n"
        f"⚠️ {3} варна = бан"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📚 Помощь\n\n"
        "Бот автоматически удаляет сообщения с нарушениями и выдает варны.\n"
        f"После {3} варнов - бан.\n\n"
        "Команды:\n"
        "/stats - статистика\n"
        "/check_user - мой статус\n"
        "/get_warns - получить варны\n"
        "/reset_warns - сбросить варны"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
    result = telegram_admin({
        "user_message": "/stats",
        "user_id": str(update.effective_user.id)
    })
    if result.get("answer"):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=result["answer"]
        )


async def check_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /check_user"""
    result = telegram_admin({
        "user_message": "/check_user",
        "user_id": str(update.effective_user.id)
    })
    if result.get("answer"):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=result["answer"]
        )


async def get_warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /get_warns"""
    user_id = str(update.effective_user.id)
    parts = update.message.text.split()
    target = parts[1] if len(parts) > 1 else user_id
    result = telegram_admin({
        "user_message": f"/get_warns {target}",
        "user_id": user_id
    })
    if result.get("answer"):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=result["answer"]
        )


async def reset_warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /reset_warns"""
    user_id = str(update.effective_user.id)
    result = telegram_admin({
        "user_message": "/reset_warns",
        "user_id": user_id
    })
    if result.get("answer"):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=result["answer"]
        )


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unban"""
    user_id = str(update.effective_user.id)
    parts = update.message.text.split()
    target = parts[1] if len(parts) > 1 else user_id
    result = telegram_admin({
        "user_message": f"/unban {target}",
        "user_id": user_id,
        "chat_id": str(update.effective_chat.id),
        "bot": BotWrapper(context.bot)
    })
    if result.get("answer"):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=result["answer"]
        )


def main():
    TOKEN = "7413306182:AAGb8XrvkgoioGdNqBT6DMVHeISGG-dMWvM"

    print("=" * 50)
    print("🤖 ЗАПУСК АНТИСПАМ БОТА")
    print("=" * 50)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("check_user", check_user_command))
    app.add_handler(CommandHandler("get_warns", get_warns_command))
    app.add_handler(CommandHandler("reset_warns", reset_warns_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот успешно запущен!")
    print("=" * 50)

    app.run_polling()


# ============= ЭТО САМОЕ ВАЖНОЕ - ЗАПУСК =============
if __name__ == "__main__":
    main()