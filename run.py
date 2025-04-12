import asyncio
import logging
from bot import main as bot_main
from admin_panel.app import app
from hypercorn.asyncio import serve
from hypercorn.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_web():
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.use_reloader = False
    await serve(app, config)


async def main():
    bot_task = asyncio.create_task(bot_main())
    web_task = asyncio.create_task(run_web())
    logger.info("Starting bot and web server...")
    await asyncio.gather(bot_task, web_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")

