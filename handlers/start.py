from datetime import datetime

from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from config import BOT_INFO_TEXT, OWNER_ID
from db.database import get_db, get_uid_by_ref_code, record_referral, get_referral_count
from config import REFERRAL_REQUIRED
from utils.helpers import get_menu, cleanup_files

router = Router()


# ================================================================
# ═════════════════  START  ══════════════════════════════════════
# ================================================================

@router.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    uid      = message.from_user.id
    username = message.from_user.username or ""

    # ── Parse referral code from deep link (/start ref_XXXXXXXX) ──
    args = message.text.split(maxsplit=1)
    ref_code_used = None
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code_used = args[1][4:]  # strip "ref_" prefix

    # ── Register user ───────────────────────────────────────────
    is_new = False
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id FROM users WHERE user_id=%s", (uid,))
                existing = c.fetchone()
                if not existing:
                    is_new = True
                first_name = message.from_user.first_name or ""
                last_name  = message.from_user.last_name  or ""
                c.execute(
                    "INSERT INTO users (user_id, username, first_name, last_name, created_at) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE username=VALUES(username), first_name=VALUES(first_name), last_name=VALUES(last_name)",
                    (uid, username, first_name, last_name, datetime.now())
                )
        finally:
            db.close()
    except Exception as e:
        print(f"[START DB ERROR] {e}")

    # ── Notify owner of new user ─────────────────────────────────
    if is_new:
        try:
            await message.bot.send_message(
                OWNER_ID,
                f"🆕 <b>YANGI FOYDALANUVCHI</b>\n"
                f"👤 @{username or '—'} (ID: <code>{uid}</code>)\n"
                f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"[NEW USER NOTIFY ERROR] {e}")

    # ── Record referral (only for truly new users) ───────────────
    if is_new and ref_code_used:
        referrer_id = get_uid_by_ref_code(ref_code_used)
        if referrer_id and referrer_id != uid:
            recorded = record_referral(referrer_id, uid)
            if recorded:
                # Tell the referrer someone joined via their link
                total_now = get_referral_count(referrer_id)
                remaining = REFERRAL_REQUIRED - (total_now % REFERRAL_REQUIRED)
                try:
                    await message.bot.send_message(
                        referrer_id,
                        f"🎉 <b>Yangi do'stingiz botga qo'shildi!</b>\n\n"
                        f"👤 Jami taklif qilinganlar: <b>{total_now}</b>\n"
                        f"⏳ Keyingi mukofotgacha: <b>{remaining}</b> ta",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                # Check and reward milestone
                from handlers.referral import check_and_reward_referrer
                await check_and_reward_referrer(message.bot, referrer_id)

    await state.clear()
    await message.answer("👋 Xush kelibsiz!", reply_markup=get_menu(uid))

# ================= CANCEL =================

@router.message(F.text == "❌ Bekor qilish")
async def cancel_any(message: types.Message, state: FSMContext):
    data = await state.get_data()
    for p in data.get("images", []):
        cleanup_files(p)
    await state.clear()
    await message.answer("❌ Bekor qilindi", reply_markup=get_menu(message.from_user.id))

# ================================================================
# ═════════════════  INFO BUTTON  ════════════════════════════════
# ================================================================

@router.message(F.text == "ℹ️ Ma'lumot")
async def info_handler(message: types.Message):
    await message.answer(BOT_INFO_TEXT, parse_mode="HTML")
