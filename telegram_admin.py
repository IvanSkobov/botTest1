def telegram_admin(arguments: dict) -> dict:
    """
    Антиспам функция для smaiPL AI Assistant (рабочая версия)
    """
    # Все импорты внутри функции
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
    MAX_WARNS = 3
    FLOOD_TIME_WINDOW = 3.0
    FLOOD_MESSAGE_LIMIT = 5
    REPEATED_MESSAGE_LIMIT = 3
    MESSAGE_HISTORY_SIZE = 5
    MAX_MESSAGE_LENGTH = 1000

    BAD_WORDS = ["блять", "сука", "хуй", "пизда", "ебать", "нахер", "залупа", "мудак", "козел", "дебил"]

    SPAM_PATTERNS = [
        r"https?://", r"t\.me", r"@\w+", r"(.)\1{5,}", r"www\.",
        r"\d{10,}", r"\+?\d[\d\s\-\(\)]{8,}\d", r"discord\.gg/\w+"
    ]

    # ============= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =============
    def check_violation(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Проверка текста на нарушения"""
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
        """Проверка на флуд"""
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

    def check_repeated(user_id: str, text: str) -> bool:
        """Проверка на повтор сообщений"""
        if not text or len(text) < 3:
            return False

        text_lower = text.lower()
        messages = telegram_admin._messages.get(user_id)

        if messages is None:
            telegram_admin._messages[user_id] = [text_lower]
            return False

        recent = messages[-MESSAGE_HISTORY_SIZE:] if len(messages) > MESSAGE_HISTORY_SIZE else messages
        count = sum(1 for msg in recent if msg == text_lower)

        if count >= REPEATED_MESSAGE_LIMIT - 1:
            logger.info(f"Повтор от {user_id}: '{text[:30]}'")
            messages.append(text_lower)
            telegram_admin._messages[user_id] = messages[-MESSAGE_HISTORY_SIZE:]
            return True

        messages.append(text_lower)
        telegram_admin._messages[user_id] = messages[-MESSAGE_HISTORY_SIZE:]
        return False

    def add_warn(user_id: str, violation_type: str, detail: str) -> Dict[str, Any]:
        """Добавление предупреждения"""
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
        action = arguments.get("action", "automod")
        user_message = arguments.get("user_message", "")
        user_id = str(arguments.get("user_id", "unknown"))
        debug = arguments.get("debug", False)

        if debug:
            logger.debug(f"=== ВЫЗОВ === user={user_id} action={action} msg_len={len(user_message)}")

        # Проверка на пустое сообщение
        if not user_message or len(user_message.strip()) == 0:
            logger.debug(f"Пустое сообщение от {user_id}")
            return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        # Проверка на длинное сообщение
        if len(user_message) > MAX_MESSAGE_LENGTH:
            return {
                "answer": f"⚠️ Сообщение слишком длинное (макс. {MAX_MESSAGE_LENGTH} символов)",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            }

        # ============= ОБРАБОТКА КОМАНД =============
        if user_message.startswith("/"):
            # /stats
            if user_message.startswith("/stats"):
                total_users = len(telegram_admin._warns)
                total_warns = sum(telegram_admin._warns.values())
                banned_count = len(telegram_admin._banned)
                answer = f"📊 Статистика: {total_users} пользователей, {total_warns} варнов, {banned_count} банов"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            # /check_user
            if user_message.startswith("/check_user"):
                if user_id in telegram_admin._banned:
                    answer = "🔨 ВЫ ЗАБАНЕНЫ"
                else:
                    warns = telegram_admin._warns.get(user_id, 0)
                    if warns == 0:
                        answer = "✅ Вы активны. Нарушений нет."
                    else:
                        answer = f"⚠️ У вас {warns}/{MAX_WARNS} варнов"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            # /get_warns
            if user_message.startswith("/get_warns"):
                target_id = user_id
                parts = user_message.split()
                if len(parts) > 1 and parts[1].isdigit():
                    target_id = parts[1]
                warns = telegram_admin._warns.get(target_id, 0)
                answer = f"⚠️ У пользователя {target_id} {warns}/{MAX_WARNS} варнов"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            # /reset_warns
            if user_message.startswith("/reset_warns"):
                old_warns = telegram_admin._warns.get(user_id, 0)
                telegram_admin._warns[user_id] = 0
                if user_id in telegram_admin._banned:
                    del telegram_admin._banned[user_id]
                answer = f"✅ Варны сброшены (было: {old_warns})"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            # /help
            if user_message.startswith("/help"):
                answer = f"📚 Антиспам бот\nКоманды: /stats, /check_user, /get_warns, /reset_warns\n{MAX_WARNS} варна = бан"
                return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

            # Неизвестная команда
            return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        # ============= АВТОМАТИЧЕСКАЯ ПРОВЕРКА =============

        # Проверка на бан
        if user_id in telegram_admin._banned:
            logger.debug(f"Забаненный {user_id} пытается писать")
            return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        current_time = time.time()

        # Проверка на флуд
        if check_flood(user_id, current_time):
            answer = f"⛔ ФЛУД | Подождите {int(FLOOD_TIME_WINDOW)}с"
            return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        # Проверка на повтор
        if check_repeated(user_id, user_message):
            result = add_warn(user_id, "повтор", "")
            if result["action"] == "ban":
                answer = f"⛔ БАН | Повтор | {result['warns']}/{result['max_warns']}"
            else:
                answer = f"⚠️ Варн {result['warns']}/{result['max_warns']} | Повтор"
            return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        # Проверка на мат/спам
        violation_type, violation_detail = check_violation(user_message)
        if violation_type:
            result = add_warn(user_id, violation_type, violation_detail)
            if result["action"] == "ban":
                answer = f"⛔ БАН | {result['violation']} | {result['warns']}/{result['max_warns']}"
            else:
                answer = f"⚠️ Варн {result['warns']}/{result['max_warns']} | {result['violation']}"
            return {"answer": answer, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

        # Нет нарушений
        if debug:
            logger.debug(f"✅ Сообщение от {user_id} прошло проверку")

        return {"answer": None, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    except Exception as e:
        error_msg = f"❌ Ошибка: {str(e)}"
        logger.error(error_msg)
        return {"answer": error_msg, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


# ============= ТЕСТИРОВАНИЕ =============
if __name__ == "__main__":
    print("=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ АНТИСПАМ ФУНКЦИИ")
    print("=" * 60)

    # Тест 1: Обычное сообщение
    print("\n📝 Тест 1: Обычное сообщение")
    result = telegram_admin({
        "user_message": "Привет! Как дела?",
        "user_id": "user123",
        "debug": True
    })
    print(f"Результат: {result}")

    # Тест 2: Сообщение с матом
    print("\n📝 Тест 2: Сообщение с матом")
    result = telegram_admin({
        "user_message": "Ты сука тупой?",
        "user_id": "user123",
        "debug": True
    })
    print(f"Результат: {result}")

    # Тест 3: Флуд
    print("\n📝 Тест 3: Флуд")
    flood_user = "flooder"
    for i in range(6):
        result = telegram_admin({
            "user_message": f"Сообщение {i}",
            "user_id": flood_user
        })
        if result.get("answer"):
            print(f"  Сообщение {i}: {result['answer'][:50]}...")
        else:
            print(f"  Сообщение {i}: OK")

    # Тест 4: Статистика
    print("\n📝 Тест 4: Статистика")
    result = telegram_admin({
        "user_message": "/stats",
        "user_id": "admin"
    })
    print(f"Результат: {result.get('answer')}")

    print("\n" + "=" * 60)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 60)