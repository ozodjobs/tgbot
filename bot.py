import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS
from db.database import ensure_tables, get_db
from utils.image import HAS_CV2
from handlers import start, pdf, orders, payment, admin, referral, support

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.include_router(start.router)
dp.include_router(pdf.router)
dp.include_router(orders.router)
dp.include_router(payment.router)
dp.include_router(admin.router)
dp.include_router(referral.router)
dp.include_router(support.router)

# ================================================================
# ═════════════════  WATCHER  ════════════════════════════════════
# ================================================================

async def access_watcher():
    while True:
        try:
            db = get_db()
            try:
                with db.cursor() as c:
                    c.execute("SELECT user_id, access_until FROM users WHERE warned=0 AND access_until IS NOT NULL AND access_until > NOW()")
                    rows = c.fetchall()
            finally:
                db.close()
            for r in rows:
                delta = r["access_until"] - datetime.now()
                if timedelta(days=0) < delta <= timedelta(days=3):
                    try:
                        await bot.send_message(r["user_id"], "⏰ Diqqat! Obunangiz tugashiga 3 kun qoldi.\nUzluksiz foydalanish uchun to'lovni yangilang.")
                        db2 = get_db()
                        try:
                            with db2.cursor() as c2:
                                c2.execute("UPDATE users SET warned=1 WHERE user_id=%s", (r["user_id"],))
                        finally:
                            db2.close()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Watcher ERROR] {e}")
        await asyncio.sleep(3600)

# ================================================================
# ═════════════════  STARTUP & RUN  ══════════════════════════════
# ================================================================

async def on_startup():
    ensure_tables()
    asyncio.create_task(access_watcher())
    print("✅ Bot ishga tushdi")
    if HAS_CV2:
        print("✅ OpenCV mavjud — auto-crop va professional skan yoqildi")
    else:
        print("⚠️  OpenCV yo'q — fallback skan rejimi ishlatiladi (pip install opencv-python-headless)")
    print(f"👥 Referral tizimi: {REFERRAL_REQUIRED} ta taklif = {REFERRAL_REWARD_DAYS} kun premium")


async def main():
    print("🚀 Starting bot...")
    dp.startup.register(on_startup)
    while True:
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), close_bot_session=False)
        except Exception as e:
            print(f"[POLLING ERROR] {e} — restarting in 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
