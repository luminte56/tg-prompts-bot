import asyncio
import logging
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault

from config import BOT_TOKEN, ADMIN_IDS
import database as db
from handlers.admin import router as admin_router
from handlers.user import router as user_router

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Запустить бота / Главное меню"),
        BotCommand(command="help", description="Помощь и информация"),
        BotCommand(command="admin", description="Админ-панель (только для админа)"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def main() -> None:
    logger.info("Инициализация базы данных...")
    await db.init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем роутеры: админка первой, затем юзер
    dp.include_router(admin_router)
    dp.include_router(user_router)

    await set_bot_commands(bot)

    logger.info("Бот запущен и готов к приему сообщений!")
    logger.info(f"Администраторы: {ADMIN_IDS}")

    try:
        # Сбрасываем старые вебхуки / обновления перед поллингом
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
