import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from config.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def parse_duration(text: str) -> timedelta:
    if not text:
        return timedelta(minutes=10)
    text = text.strip().lower()
    value_str = "".join(ch for ch in text if ch.isdigit())
    unit = "".join(ch for ch in text if ch.isalpha())
    value = int(value_str)
    if unit in ("", "m", "min", "minute", "minutes"):
        return timedelta(minutes=value)
    if unit in ("h", "hr", "hour", "hours"):
        return timedelta(hours=value)
    if unit in ("d", "day", "days"):
        return timedelta(days=value)
    raise ValueError("Поддерживаются только m/h/d")


async def is_admin(message: types.Message, user_id: int) -> bool:
    member = await message.chat.get_member(user_id)
    return member.status in {"administrator", "creator"}


@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("pong")


if __name__ == "__main__":
    import asyncio
    from aiogram import F

    logger.info("Бот запущен")
    asyncio.run(dp.start_polling(bot))
