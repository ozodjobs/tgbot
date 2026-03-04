from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_USERNAME, REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS
from db.database import (
    get_db, get_or_create_ref_code, get_referral_count, get_rewarded_referral_count
)
from config import menu_premium

router = Router()


async def check_and_reward_referrer(bot, referrer_id: int):
    """
    Check if referrer has hit a new REFERRAL_REQUIRED milestone and hasn't
    been rewarded for it yet.  Award REFERRAL_REWARD_DAYS of premium if so.
    """
    try:
        total    = get_referral_count(referrer_id)
        rewarded = get_rewarded_referral_count(referrer_id)

        # How many complete milestones earned vs already rewarded
        milestones_earned  = total    // REFERRAL_REQUIRED
        milestones_rewarded = rewarded // REFERRAL_REQUIRED

        if milestones_earned <= milestones_rewarded:
            return  # No new milestone yet

        # Grant premium for each unrewarded milestone
        new_milestones = milestones_earned - milestones_rewarded
        days_to_add    = new_milestones * REFERRAL_REWARD_DAYS

        db = get_db()
        try:
            with db.cursor() as c:
                # Extend premium
                c.execute(
                    """UPDATE users
                       SET access_until = GREATEST(COALESCE(access_until, NOW()), NOW()) + INTERVAL %s DAY,
                           warned = 0
                       WHERE user_id = %s""",
                    (days_to_add, referrer_id)
                )
                # Mark the referrals up to this milestone as rewarded
                # Mark exactly REFERRAL_REQUIRED * new_milestones rows as rewarded
                rows_to_reward = new_milestones * REFERRAL_REQUIRED
                c.execute(
                    """UPDATE referrals
                       SET rewarded = 1
                       WHERE referrer_id = %s AND rewarded = 0
                       ORDER BY id ASC
                       LIMIT %s""",
                    (referrer_id, rows_to_reward)
                )
        finally:
            db.close()

        msg = (
            f"🎉 <b>Tabriklaymiz!</b>\n\n"
            f"Siz <b>{REFERRAL_REQUIRED} ta do'stingizni</b> taklif qildingiz!\n"
            f"<b>{days_to_add} kunlik premium</b> hisobingizga qo'shildi! ✅"
        )
        try:
            await bot.send_message(referrer_id, msg, parse_mode="HTML", reply_markup=menu_premium)
        except Exception as e:
            print(f"[REWARD SEND ERROR uid={referrer_id}] {e}")

    except Exception as e:
        print(f"[check_and_reward_referrer ERROR] {e}")


# ================================================================
# ══════════════  REFERRAL — DO'ST TAKLIF QILISH  ════════════════
# ================================================================

@router.message(F.text == "👥 Do'st taklif qilish")
async def referral_panel(message: types.Message):
    uid   = message.from_user.id
    code  = get_or_create_ref_code(uid)
    total = get_referral_count(uid)
    done_milestones   = total // REFERRAL_REQUIRED
    remaining_in_step = REFERRAL_REQUIRED - (total % REFERRAL_REQUIRED)

    invite_link = f"https://t.me/{BOT_USERNAME}?start=ref_{code}"

    # Progress bar (10 slots)
    filled  = total % REFERRAL_REQUIRED
    bar     = "🟩" * filled + "⬜" * (REFERRAL_REQUIRED - filled)

    text = (
        f"👥 <b>DO'ST TAKLIF QILISH</b>\n\n"
        f"Har <b>{REFERRAL_REQUIRED} ta</b> do'stingizni taklif qilganingizda "
        f"<b>{REFERRAL_REWARD_DAYS} kunlik premium</b> sovg'a!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Sizning statistikangiz:\n"
        f"👤 Jami taklif qilinganlar: <b>{total}</b>\n"
        f"🎁 Qo'lga kiritilgan mukofotlar: <b>{done_milestones}</b>\n"
        f"⏳ Keyingi mukofotgacha: <b>{remaining_in_step}</b> ta\n\n"
        f"{bar}  <b>{total % REFERRAL_REQUIRED}/{REFERRAL_REQUIRED}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 Sizning havolangiz:\n"
        f"<code>{invite_link}</code>\n\n"
        f"👇 Pastdagi tugmani bosib do'stlaringizga yuboring!"
    )

    share_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📤 Do'stlarga yuborish",
            url=f"https://t.me/share/url?url={invite_link}&text=Bu%20botdan%20foydalaning%2C%20juda%20foydali%21"
        )],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="ref:refresh")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=share_kb)


@router.callback_query(F.data == "ref:refresh")
async def referral_refresh(callback: types.CallbackQuery):
    uid   = callback.from_user.id
    code  = get_or_create_ref_code(uid)
    total = get_referral_count(uid)
    done_milestones   = total // REFERRAL_REQUIRED
    remaining_in_step = REFERRAL_REQUIRED - (total % REFERRAL_REQUIRED)

    invite_link = f"https://t.me/{BOT_USERNAME}?start=ref_{code}"
    filled  = total % REFERRAL_REQUIRED
    bar     = "🟩" * filled + "⬜" * (REFERRAL_REQUIRED - filled)

    text = (
        f"👥 <b>DO'ST TAKLIF QILISH</b>\n\n"
        f"Har <b>{REFERRAL_REQUIRED} ta</b> do'stingizni taklif qilganingizda "
        f"<b>{REFERRAL_REWARD_DAYS} kunlik premium</b> sovg'a!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Sizning statistikangiz:\n"
        f"👤 Jami taklif qilinganlar: <b>{total}</b>\n"
        f"🎁 Qo'lga kiritilgan mukofotlar: <b>{done_milestones}</b>\n"
        f"⏳ Keyingi mukofotgacha: <b>{remaining_in_step}</b> ta\n\n"
        f"{bar}  <b>{total % REFERRAL_REQUIRED}/{REFERRAL_REQUIRED}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 Sizning havolangiz:\n"
        f"<code>{invite_link}</code>\n\n"
        f"👇 Pastdagi tugmani bosib do'stlaringizga yuboring!"
    )

    share_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📤 Do'stlarga yuborish",
            url=f"https://t.me/share/url?url={invite_link}&text=Bu%20botdan%20foydalaning%2C%20juda%20foydali%21"
        )],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="ref:refresh")]
    ])
    await callback.answer("🔄 Yangilandi")
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=share_kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=share_kb)
