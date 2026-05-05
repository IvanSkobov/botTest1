def telegram_admin(arguments: dict) -> dict:
    from datetime import datetime, timedelta
    from telegram import ChatPermissions
    from telegram.error import TelegramError
    import re

    action = arguments.get("action")
    chat_id = arguments.get("chat_id")
    bot = arguments.get("bot")
    debug = arguments.get("debug", False)

    if not action or not chat_id or not bot:
        return {"answer": None, "error": "Нет обязательных параметров", "status": "failed"}

    # --- анти-мат (можешь расширять список)
    BAD_WORDS = [
        "блять", "сука", "хуй", "пизда", "ебать", "нахуй"
    ]

    # --- простая анти-спам логика
    SPAM_PATTERNS = [
        r"http[s]?://",
        r"t\.me/",
        r"@\w+",
        r"(.)\1{6,}",  # повтор символов
    ]

    def contains_bad_words(text):
        text = text.lower()
        return any(word in text for word in BAD_WORDS)

    def is_spam(text):
        for pattern in SPAM_PATTERNS:
            if re.search(pattern, text.lower()):
                return True
        return False

    try:
        # ------------------------
        # УДАЛЕНИЕ СООБЩЕНИЯ
        # ------------------------
        if action == "delete_message":
            message_id = arguments.get("message_id")
            if not message_id:
                return {"answer": None, "error": "Нет message_id", "status": "failed"}

            bot.delete_message(chat_id=chat_id, message_id=message_id)

            return {"answer": "Сообщение удалено", "status": "success"}

        # ------------------------
        # БАН
        # ------------------------
        elif action == "ban_user":
            user_id = arguments.get("user_id")
            ban_ttl = arguments.get("ban_ttl", 0)

            if not user_id:
                return {"answer": None, "error": "Нет user_id", "status": "failed"}

            until_date = None
            if ban_ttl > 0:
                until_date = datetime.now() + timedelta(seconds=ban_ttl)

            bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=until_date
            )

            return {"answer": f"Пользователь {user_id} забанен", "status": "success"}

        # ------------------------
        # РАЗБАН
        # ------------------------
        elif action == "unban_user":
            user_id = arguments.get("user_id")

            bot.unban_chat_member(chat_id=chat_id, user_id=user_id)

            return {"answer": "Пользователь разбанен", "status": "success"}

        # ------------------------
        # МУТ
        # ------------------------
        elif action == "mute_user":
            user_id = arguments.get("user_id")
            mute_ttl = arguments.get("mute_ttl", 60)

            until_date = datetime.now() + timedelta(seconds=mute_ttl)

            bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )

            return {"answer": f"Пользователь замучен на {mute_ttl} сек", "status": "success"}

        # ------------------------
        # ОТПРАВКА СООБЩЕНИЯ
        # ------------------------
        elif action == "send_message":
            text = arguments.get("text")

            bot.send_message(chat_id=chat_id, text=text)

            return {"answer": "Сообщение отправлено", "status": "success"}

        # ------------------------
        # АВТОМОД
        # ------------------------
        elif action == "automod":
            user_id = arguments.get("user_id")
            message_id = arguments.get("message_id")
            text = arguments.get("text", "")

            if not user_id or not message_id:
                return {"answer": None, "error": "Нет user_id/message_id", "status": "failed"}

            # --- МАТ
            if contains_bad_words(text):
                bot.delete_message(chat_id=chat_id, message_id=message_id)

                until_date = datetime.now() + timedelta(minutes=5)

                bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )

                return {
                    "answer": f"Мат обнаружен. Пользователь {user_id} замучен",
                    "status": "success",
                    "reason": "bad_words"
                }

            # --- СПАМ
            if is_spam(text):
                bot.delete_message(chat_id=chat_id, message_id=message_id)

                return {
                    "answer": f"Спам удалён у {user_id}",
                    "status": "success",
                    "reason": "spam"
                }

            return {"answer": "Нарушений нет", "status": "success"}

        else:
            return {"answer": None, "error": "Неизвестное действие", "status": "failed"}

    except TelegramError as e:
        return {"answer": None, "error": str(e), "status": "failed"}