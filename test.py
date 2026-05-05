# ================================
# TEST FILE FOR telegram_admin
# ================================

from datetime import datetime
from pprint import pprint

# 👉 импортируй свою функцию
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


# ================================
# FAKE BOT (эмуляция Telegram API)
# ================================
class FakeBot:
    def delete_message(self, chat_id, message_id):
        print(f"[BOT] delete_message | chat_id={chat_id}, message_id={message_id}")

    def ban_chat_member(self, chat_id, user_id, until_date=None):
        print(f"[BOT] ban_user | user_id={user_id}, until={until_date}")

    def unban_chat_member(self, chat_id, user_id):
        print(f"[BOT] unban_user | user_id={user_id}")

    def restrict_chat_member(self, chat_id, user_id, permissions, until_date=None):
        print(f"[BOT] mute_user | user_id={user_id}, until={until_date}")

    def send_message(self, chat_id, text):
        print(f"[BOT] send_message | {text}")


# ================================
# FAKE AI (проверка токсичности)
# ================================
def fake_ai(text):
    toxic_words = ["идиот", "тупой", "дебил"]
    return {"toxic": any(word in text.lower() for word in toxic_words)}


# ================================
# TEST RUNNER
# ================================
def run_test(name, payload):
    print("\n" + "=" * 50)
    print(f"TEST: {name}")
    print("=" * 50)

    result = telegram_admin(payload)
    pprint(result)


# ================================
# MAIN TESTS
# ================================
if __name__ == "__main__":
    bot = FakeBot()

    # 1. Мат
    run_test("BAD WORD", {
        "action": "automod",
        "chat_id": 1,
        "user_id": 100,
        "message_id": 1,
        "text": "блять что это",
        "bot": bot,
        "ai_check": fake_ai
    })

    # 2. Спам
    run_test("SPAM", {
        "action": "automod",
        "chat_id": 1,
        "user_id": 101,
        "message_id": 2,
        "text": "заходи http://spam.com",
        "bot": bot,
        "ai_check": fake_ai
    })

    # 3. AI токсичность
    run_test("AI TOXIC", {
        "action": "automod",
        "chat_id": 1,
        "user_id": 102,
        "message_id": 3,
        "text": "ты идиот",
        "bot": bot,
        "ai_check": fake_ai
    })

    # 4. Норм сообщение
    run_test("CLEAN MESSAGE", {
        "action": "automod",
        "chat_id": 1,
        "user_id": 103,
        "message_id": 4,
        "text": "всем привет",
        "bot": bot,
        "ai_check": fake_ai
    })

    # 5. Проверка варнов (эскалация)
    for i in range(3):
        run_test(f"WARN ESCALATION {i+1}", {
            "action": "automod",
            "chat_id": 1,
            "user_id": 200,
            "message_id": 10 + i,
            "text": "сука",
            "bot": bot,
            "ai_check": fake_ai
        })

    # 6. Сброс варнов
    run_test("RESET WARNS", {
        "action": "reset_warns",
        "chat_id": 1,
        "user_id": 200,
        "bot": bot
    })

    # 7. Проверка варнов после сброса
    run_test("GET WARNS", {
        "action": "get_warns",
        "chat_id": 1,
        "user_id": 200,
        "bot": bot
    })

    print("\n✅ Все тесты выполнены")
