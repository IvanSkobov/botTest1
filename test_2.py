def telegram_admin(arguments: dict) -> dict:
    """
    Антиспам функция для smaiPL AI Assistant (с удалением сообщений)
    """
    import re
    import time
    import logging
    from datetime import datetime
    from typing import Optional, Tuple, Dict, Any, List

    # ============= НАСТРОЙКА ЛОГИРОВАНИЯ =============
    logger = logging.getLogger(f"antispam_{__name__}")

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # ============= ИНИЦИАЛИЗАЦИЯ ХРАНИЛИЩА =============
    if not hasattr(telegram_admin, "_warns"):
        telegram_admin._warns: Dict[str, int] = {}
        telegram_admin._messages: Dict[str, List[str]] = {}
        telegram_admin._timestamps: Dict[str, List[float]] = {}
        telegram_admin._banned: Dict[str, dict] = {}
        logger.debug("Хранилища инициализированы")

    # ============= КОНСТАНТЫ =============
    MAX_WARNS = 2  # БАН ПОСЛЕ 2 ВАРНОВ
    FLOOD_TIME_WINDOW = 3.0
    FLOOD_MESSAGE_LIMIT = 5
    REPEATED_MESSAGE_LIMIT = 2  # 2 ПОВТОРА = ВАРН
    MESSAGE_HISTORY_SIZE = 10
    MAX_MESSAGE_LENGTH = 1000

    BAD_WORDS = ["блять", "сука", "хуй", "пизда", "ебать", "нахер", "залупа", "мудак", "козел", "дебил"]

    SPAM_PATTERNS = [
        r"https?://", r"t\.me", r"@\w+", r"(.)\1{5,}", r"www\.",
        r"\d{10,}", r"\+?\d[\d\s\-\(\)]{8,}\d", r"discord\.gg/\w+"
    ]

    # ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============
    def check_violation(text: str) -> Tuple[Optional[str], Optional[str]]:
        if not text or len(text) > MAX_MESSAGE_LENGTH:
            return (None, None)
        text_lower = text.lower()
        for word in BAD_WORDS:
            if word in text_lower:
                logger.debug(f"Найдено запрещенное слово: {word}")
                return ("мат", word)
        for pattern in SPAM_PATTERNS:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    logger.debug(f"Найден спам-паттерн: {pattern}")
                    return ("спам/ссылка", pattern)
            except re.error:
                continue
        return (None, None)

    def check_flood(user_id: str, current_time: float) -> bool:
        timestamps = telegram_admin._timestamps.get(user_id)
        if timestamps is None:
            telegram_admin._timestamps[user_id] = [current_time]
            return False
        cutoff = current_time - FLOOD_TIME_WINDOW
        valid_timestamps = [ts for ts in timestamps if ts > cutoff]
        if len(valid_timestamps) >= FLOOD_MESSAGE_LIMIT:
            logger.info(f"Флуд от {user_id}: {len(valid_timestamps)} сообщений")
            return True
        valid_timestamps.append(current_time)
        telegram_admin._timestamps[user_id] = valid_timestamps
        return False

    def check_repeated(user_id: str, text: str) -> Tuple[bool, bool, int]:
        """
        Проверка на повтор сообщений.
        Возвращает (нужно_удалить, нужно_выдать_варн, количество_повторов)
        Удаляются ВСЕ повторы, остается только 1 сообщение
        """
        if not text or len(text) < 3:
            return (False, False, 0)

        text_lower = text.lower()
        messages = telegram_admin._messages.get(user_id)

        if messages is None:
            telegram_admin._messages[user_id] = [text_lower]
            return (False, False, 0)

        # Считаем сколько раз уже было такое сообщение
        count = messages.count(text_lower)

        if count > 0:
            logger.info(f"Повтор от {user_id}: '{text[:30]}' (уже было {count} раз)")

            # Увеличиваем счетчик повторов для варна
            if not hasattr(telegram_admin, "_repeat_count"):
                telegram_admin._repeat_count = {}

            repeat_count = telegram_admin._repeat_count.get(user_id, 0) + 1
            telegram_admin._repeat_count[user_id] = repeat_count

            # Выдаем варн при достижении лимита
            if repeat_count >= REPEATED_MESSAGE_LIMIT:
                telegram_admin._repeat_count[user_id] = 0
                return (True, True, count + 1)  # Удалить И выдать варн

            return (True, False, count + 1)  # Только удалить, варн не выдаем

        # Новое сообщение - добавляем в историю
        messages.append(text_lower)
        telegram_admin._messages[user_id] = messages[-MESSAGE_HISTORY_SIZE:]
        # Сбрасываем счетчик повторов
        if hasattr(telegram_admin, "_repeat_count"):
            telegram_admin._repeat_count[user_id] = 0
        return (False, False, 0)

    def add_warn(user_id: str, violation_type: str, detail: str) -> Dict[str, Any]:
        current = telegram_admin._warns.get(user_id, 0)
        new_warns = current + 1
        telegram_admin._warns[user_id] = new_warns
        logger.info(f"Варн {new_warns}/{MAX_WARNS} | {user_id} | {violation_type}")
        result = {
            "warns": new_warns,
            "max_warns": MAX_WARNS,
            "violation": violation_type,
            "action": "ban" if new_warns >= MAX_WARNS else "warn"
        }
        if result["action"] == "ban":
            telegram_admin._warns[user_id] = 0
            telegram_admin._banned[user_id] = {
                "time": time.time(),
                "time_str": datetime.now().isoformat(),
                "reason": violation_type
            }
            logger.warning(f"БАН! {user_id} за {violation_type}")
        return result

    # ============= ОСНОВНАЯ ЛОГИКА =============
    try:
        # Получаем параметры
        action = arguments.get("action", "automod")
        user_message = arguments.get("user_message", "")
        user_id = str(arguments.get("user_id", "unknown"))
        message_id = arguments.get("message_id")
        chat_id = arguments.get("chat_id")
        bot = arguments.get("bot")
        debug = arguments.get("debug", False)

        if debug:
            logger.debug(f"=== ВЫЗОВ === user={user_id} action={action} msg_len={len(user_message)}")

        # Пустое сообщение
        if not user_message or len(user_message.strip()) == 0:
            return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        # Длинное сообщение
        if len(user_message) > MAX_MESSAGE_LENGTH:
            return {
                "answer": f"⚠️ Сообщение слишком длинное (макс. {MAX_MESSAGE_LENGTH} символов)",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            }

        # ============= КОМАНДЫ =============
        if user_message.startswith("/"):
            if user_message.startswith("/stats"):
                total = len(telegram_admin._warns)
                warns = sum(telegram_admin._warns.values())
                banned = len(telegram_admin._banned)
                answer = f"📊 Статистика: {total} пользователей, {warns} варнов, {banned} банов"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            if user_message.startswith("/check_user"):
                if user_id in telegram_admin._banned:
                    answer = "🔨 ВЫ ЗАБАНЕНЫ"
                else:
                    warns = telegram_admin._warns.get(user_id, 0)
                    answer = "✅ Вы активны" if warns == 0 else f"⚠️ У вас {warns}/{MAX_WARNS} варнов"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            if user_message.startswith("/get_warns"):
                target = user_id
                parts = user_message.split()
                if len(parts) > 1:
                    target = parts[1]
                warns = telegram_admin._warns.get(target, 0)
                answer = f"⚠️ У пользователя {target} {warns}/{MAX_WARNS} варнов"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            if user_message.startswith("/reset_warns"):
                old = telegram_admin._warns.get(user_id, 0)
                telegram_admin._warns[user_id] = 0
                if user_id in telegram_admin._banned:
                    del telegram_admin._banned[user_id]
                answer = f"✅ Варны сброшены (было: {old})"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            if user_message.startswith("/unban"):
                parts = user_message.split()
                target = parts[1] if len(parts) > 1 else user_id
                if target in telegram_admin._banned:
                    del telegram_admin._banned[target]
                    telegram_admin._warns[target] = 0
                    if bot and chat_id:
                        try:
                            bot.unban_chat_member(chat_id=chat_id, user_id=target)
                            answer = f"✅ Пользователь {target} разбанен"
                        except Exception as e:
                            answer = f"⚠️ Разбанен в памяти, но ошибка: {e}"
                    else:
                        answer = f"✅ Пользователь {target} разбанен (только в памяти)"
                else:
                    answer = f"⚠️ Пользователь {target} не в бане"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            if user_message.startswith("/help"):
                answer = f"📚 Команды:\n/stats - статистика\n/check_user - мой статус\n/get_warns - варны\n/reset_warns - сброс\n/unban [id] - разбан\n\n⚠️ {MAX_WARNS} варна = бан\n🔄 2 повтора = варн"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        # ============= АВТОМАТИЧЕСКАЯ ПРОВЕРКА =============

        # Проверка на бан
        if user_id in telegram_admin._banned:
            logger.debug(f"Забаненный {user_id} пытается писать")
            return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        current_time = time.time()
        answer_text = None
        should_ban = False

        # Флуд
        if check_flood(user_id, current_time):
            answer_text = f"⛔ ФЛУД | Подождите {int(FLOOD_TIME_WINDOW)}с"
            if bot and message_id and chat_id:
                try:
                    bot.delete_message(chat_id=chat_id, message_id=message_id)
                    logger.info(f"🗑️ Удалено флуд-сообщение от {user_id}")
                except Exception as e:
                    logger.error(f"Ошибка удаления: {e}")

        # Повтор (проверяем ДО мата/спама)
        else:
            need_delete, need_warn, repeat_count = check_repeated(user_id, user_message)

            if need_delete:
                # Удаляем повторяющееся сообщение
                if bot and message_id and chat_id:
                    try:
                        bot.delete_message(chat_id=chat_id, message_id=message_id)
                        logger.info(f"🗑️ Удалено повторяющееся сообщение от {user_id} (повтор #{repeat_count})")
                    except Exception as e:
                        logger.error(f"Ошибка удаления: {e}")

                # Выдаем варн если нужно
                if need_warn:
                    result = add_warn(user_id, "повтор", f"{REPEATED_MESSAGE_LIMIT}+ повторов")
                    answer_text = f"⚠️ Варн {result['warns']}/{result['max_warns']} | Повтор сообщений"
                    if result["action"] == "ban":
                        answer_text = f"⛔ БАН | Повтор сообщений | {result['warns']}/{result['max_warns']}"
                        should_ban = True
                else:
                    # Просто удаляем, без варна
                    answer_text = f"🗑️ Удалено повторяющееся сообщение (оставлено только первое)"

        # Мат/спам (если не было флуда и не было повтора)
        if answer_text is None:
            v_type, v_detail = check_violation(user_message)
            if v_type:
                result = add_warn(user_id, v_type, v_detail)
                answer_text = f"⚠️ Варн {result['warns']}/{result['max_warns']} | {v_type}"
                if result["action"] == "ban":
                    answer_text = f"⛔ БАН | {v_type} | {result['warns']}/{result['max_warns']}"
                    should_ban = True
                if bot and message_id and chat_id:
                    try:
                        bot.delete_message(chat_id=chat_id, message_id=message_id)
                        logger.info(f"🗑️ Удалено сообщение с {v_type} от {user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка удаления: {e}")

        # Бан пользователя
        if should_ban and bot and chat_id:
            try:
                bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                logger.warning(f"🔨 Пользователь {user_id} забанен")
            except Exception as e:
                logger.error(f"Ошибка бана: {e}")

        if answer_text:
            return {"answer": answer_text, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        if debug:
            logger.debug(f"✅ Сообщение от {user_id} прошло проверку")

        return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    except Exception as e:
        error_msg = f"❌ Ошибка: {str(e)}"
        logger.error(error_msg)
        return {"answer": error_msg, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

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

    # Вызываем антиспам функцию
    result = telegram_admin({
        "user_message": user_message,
        "user_id": user_id,
        "message_id": message_id,
        "chat_id": chat_id,
        "bot": BotWrapper(context.bot)
    })

    # Отправляем ответ через send_message (НЕ reply_text!)
    if result.get("answer"):
        print(f"🤖 Ответ: {result['answer'][:50]}")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result["answer"]
            )
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")


# ============= КОМАНДЫ (ИСПРАВЛЕННЫЕ) =============
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🤖 **Антиспам бот запущен!**\n\n"
        "Я автоматически **УДАЛЯЮ** сообщения с матом, спамом, флудом.\n\n"
        "**Команды:**\n"
        "/stats - статистика\n"
        "/check_user - мой статус\n"
        "/get_warns - получить варны\n"
        "/reset_warns - сбросить варны\n"
        "/unban [id] - разбан пользователя\n"
        "/help - помощь\n\n"
        f"⚠️ **3 варна = бан**",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📚 **Команды:**\n\n"
        "/stats - статистика\n"
        "/check_user - мой статус\n"
        "/get_warns - получить варны\n"
        "/reset_warns - сбросить варны\n"
        "/unban [ID] - разбан пользователя\n"
        "/help - помощь\n\n"
        f"⚠️ {3} варна = бан",
        parse_mode="Markdown"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# ============= ЗАПУСК =============
def main():
    TOKEN = "ВВЕДИТЕ ТОКЕН ВАШЕГО БОТА"

    print("=" * 50)
    print("🤖 ЗАПУСК АНТИСПАМ БОТА")
    print("=" * 50)

    app = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
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


if __name__ == "__main__":
    main()
