def telegram_admin(arguments: dict) -> dict:
    from datetime import datetime, timedelta
    from telegram import ChatPermissions
    from telegram.error import TelegramError
    import re

    action = arguments.get("action")
    chat_id = arguments.get("chat_id")
    bot = arguments.get("bot")

    if not action or not chat_id or not bot:
        return {"status": "failed", "error": "Нет обязательных параметров"}

    # --- память варнов (глобальная)
    global USER_WARNINGS
    if "USER_WARNINGS" not in globals():
        USER_WARNINGS = {}

    # --- мат
    BAD_WORDS = ["блять", "сука", "хуй", "пизда", "ебать", "нахуй"]

    # --- спам
    SPAM_PATTERNS = [
        r"http[s]?://",
        r"t\.me/",
        r"@\w+",
        r"(.)\1{6,}",
    ]

    def contains_bad_words(text):
        return any(word in text.lower() for word in BAD_WORDS)

    def is_spam(text):
        return any(re.search(p, text.lower()) for p in SPAM_PATTERNS)

    def get_warns(user_id):
        return USER_WARNINGS.get(user_id, 0)

    def add_warn(user_id):
        USER_WARNINGS[user_id] = get_warns(user_id) + 1
        return USER_WARNINGS[user_id]

    def reset_warns(user_id):
        USER_WARNINGS[user_id] = 0

    # --- AI анализ (внешняя функция)
    def ai_toxicity(text):
        ai_func = arguments.get("ai_check")
        if not ai_func:
            return False

        try:
            result = ai_func(text)
            return result.get("toxic", False)
        except:
            return False

    try:
        # ------------------------
        # АВТОМОД
        # ------------------------
        if action == "automod":
            user_id = arguments.get("user_id")
            message_id = arguments.get("message_id")
            text = arguments.get("text", "")

            if not user_id or not message_id:
                return {"status": "failed", "error": "Нет user_id/message_id"}

            violation = None

            # --- проверки
            if contains_bad_words(text):
                violation = "bad_words"
            elif is_spam(text):
                violation = "spam"
            elif ai_toxicity(text):
                violation = "ai_toxic"

            if violation:
                # удаляем сообщение
                bot.delete_message(chat_id=chat_id, message_id=message_id)

                warns = add_warn(user_id)

                # --- 1-2 варна → мут
                if warns < 3:
                    until_date = datetime.now() + timedelta(minutes=5)

                    bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until_date
                    )

                    return {
                        "status": "success",
                        "answer": f"⚠️ Варн {warns}/3. Пользователь замучен",
                        "reason": violation
                    }

                # --- 3 варн → бан
                else:
                    bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                    reset_warns(user_id)

                    return {
                        "status": "success",
                        "answer": f"⛔ Пользователь забанен (3/3 варна)",
                        "reason": violation
                    }

            return {"status": "success", "answer": "OK"}

        # ------------------------
        # РУЧНЫЕ ДЕЙСТВИЯ
        # ------------------------
        elif action == "reset_warns":
            user_id = arguments.get("user_id")
            reset_warns(user_id)
            return {"status": "success", "answer": "Варны сброшены"}

        elif action == "get_warns":
            user_id = arguments.get("user_id")
            return {
                "status": "success",
                "answer": get_warns(user_id)
            }

        else:
            return {"status": "failed", "error": "Неизвестное действие"}

    except TelegramError as e:
        return {"status": "failed", "error": str(e)}