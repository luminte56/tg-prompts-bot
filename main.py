import asyncio
import logging
import os
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


async def start_healthcheck_server() -> None:
    port_str = os.getenv("PORT", "10000")
    port = int(port_str) if port_str.isdigit() else 10000
    try:
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text="Bot is running 24/7!"))
        app.router.add_get("/health", lambda r: web.Response(text="OK"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Healthcheck HTTP server started on port {port}")
    except Exception as e:
        logger.warning(f"Could not start HTTP server on port {port}: {e}")


async def main() -> None:
    # Запуск HTTP healthcheck сервера сразу при старте процесса
    await start_healthcheck_server()

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
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "pre_checkout_query", "my_chat_member"]
        )
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
