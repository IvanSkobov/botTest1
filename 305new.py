def telegram_admin(arguments: dict) -> dict:
    """
    Антиспам-функция для Telegram-бота (SMAIPL).

    Логика:
    • Жёсткий спам/мошенничество → мгновенный бан
    • Ссылки на другие сообщества → удаление + страйк
    • Мат/оскорбления → удаление + страйк
    • Реклама/крипта → удаление + страйк
    • 3 страйка → бан
    """

    import re

    action = arguments.get("action")
    chat_id = arguments.get("chat_id")

    if not action or not chat_id:
        return {"error": "Не переданы обязательные параметры 'action' или 'chat_id'."}

    # Храним страйки прямо в функции (SMAIPL это позволяет)
    if not hasattr(telegram_admin, "strikes"):
        telegram_admin.strikes = {}

    # ================== ПРОВЕРКА СООБЩЕНИЯ ==================
    if action == "check_message":

        user_id = arguments.get("user_id")
        message_id = arguments.get("message_id")
        text = arguments.get("text", "")

        if not user_id or not message_id:
            return {"error": "Для проверки нужны 'user_id' и 'message_id'."}

        text_lower = text.lower()

        if user_id not in telegram_admin.strikes:
            telegram_admin.strikes[user_id] = 0

        # -------- ключевые фильтры --------
        scam_words = [
            "100% profit", "free money", "гарантированный доход",
            "заработай быстро", "airdrop"
        ]

        crypto_words = [
            "bitcoin", "btc", "eth", "usdt",
            "binance", "крипта"
        ]

        bad_words = [
            "идиот", "дурак", "тупой"
        ]

        link_pattern = r"(https?://|t\.me/|discord\.gg|vk\.com/)"

        # 🚨 Мгновенный бан за скам
        for word in scam_words:
            if word in text_lower:
                return {
                    "action": "ban_user",
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "reason": "Мошенничество/скам"
                }

        violation_reason = None

        # 🔗 Ссылки
        if re.search(link_pattern, text_lower):
            violation_reason = "Запрещённая ссылка"

        # 🤬 Мат
        for word in bad_words:
            if word in text_lower:
                violation_reason = "Оскорбления/мат"

        # 📢 Крипта / реклама
        for word in crypto_words:
            if word in text_lower:
                violation_reason = "Реклама/крипта"

        if violation_reason:
            telegram_admin.strikes[user_id] += 1
            strikes_count = telegram_admin.strikes[user_id]

            if strikes_count >= 3:
                return {
                    "action": "ban_user",
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "reason": "3 страйка"
                }

            return {
                "action": "delete_message",
                "chat_id": chat_id,
                "message_id": message_id,
                "warning": f"{violation_reason}. Страйк {strikes_count}/3"
            }

        return {"action": "allow"}

    # ================== СЛУЖЕБНЫЕ ДЕЙСТВИЯ ==================

    elif action == "activation_message":
        return {
            "action": "send_message",
            "chat_id": chat_id,
            "text": (
                "🚨 Антиспам-бот активирован!\n\n"
                "Я защищаю чат от спама и мошенников.\n\n"
                "Правила:\n"
                "• Жёсткий спам → бан\n"
                "• Ссылки → удаление + страйк\n"
                "• Мат → удаление + страйк\n"
                "• Реклама/крипта → удаление + страйк\n"
                "• 3 страйка → бан"
            )
        }

    return {"error": "Неизвестное действие."}


#🔧 Как использовать в SMAIPL

#При каждом новом сообщении вызываешь:

telegram_admin({
    "action": "check_message",
    "chat_id": chat_id,
    "user_id": user_id,
    "message_id": message_id,
    "text": message_text
})