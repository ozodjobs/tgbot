import json
from datetime import datetime

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID, TARIFFS, PAYNET_LINK
from states import PaymentStates
from db.database import get_db, has_perm, all_sub_admins
from keyboards.keyboards import kb_cancel
from utils.helpers import get_menu, user_submitted_check_today
from config import menu_premium

router = Router()


@router.message(F.text == "💳 To'lov qilish")
async def payment_info(message: types.Message):
    txt = "💳 <b>Tariflar:</b>\n\n" + "".join(f"• {v}\n" for v in TARIFFS.values())
    txt += f"\n👉 To'lov:\n{PAYNET_LINK},\n yoki Karta:\n 9860350147430564"
    await message.answer(txt, parse_mode="HTML")


@router.message(F.text == "✅ To'lov qildim")
async def wait_for_check(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if user_submitted_check_today(uid) and uid != OWNER_ID:
        return await message.answer("⚠️ Siz bugungi limitdan foydalandingiz, ertaga qayta bosing.")
    await state.set_state(PaymentStates.waiting_check)
    await message.answer("🧾 Chekni yuboring (rasm yoki PDF)")


@router.message(PaymentStates.waiting_check, F.photo | F.document)
async def receive_check(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "INSERT INTO payments (user_id, status, created_at) VALUES (%s, 'pending', %s)",
                    (uid, datetime.now())
                )
                payment_id = c.lastrowid
        finally:
            db.close()
    except Exception as e:
        print(f"[PAYMENT INSERT ERROR] {e}")
        return await message.answer("❌ Xato yuz berdi.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ 30 kun",  callback_data=f"pApprove:{payment_id}:{uid}:30"),
            InlineKeyboardButton(text="✅ 90 kun",  callback_data=f"pApprove:{payment_id}:{uid}:90"),
            InlineKeyboardButton(text="✅ 180 kun", callback_data=f"pApprove:{payment_id}:{uid}:180"),
        ],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pReject:{payment_id}:{uid}")]
    ])
    username = message.from_user.username or "—"
    caption  = (
        f"🧾 <b>TO'LOV CHEKI</b>\n👤 @{username} (ID: <code>{uid}</code>)\n"
        f"🆔 Payment ID: {payment_id}\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    targets = [OWNER_ID] + [a["user_id"] for a in all_sub_admins() if "payments" in json.loads(a.get("perms", "[]"))]
    for admin_target in targets:
        try:
            if message.photo:
                await message.bot.send_photo(admin_target, message.photo[-1].file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
            else:
                await message.bot.send_document(admin_target, message.document.file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            print(f"[ADMIN SEND ERROR uid={admin_target}] {e}")
    await message.answer("⏳ Chek yuborildi. 24 soat ichida javob beriladi.")


@router.callback_query(F.data.startswith("pApprove:"))
async def approve_payment(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "payments"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        _, payment_id, uid, days = callback.data.split(":")
        payment_id, uid, days = int(payment_id), int(uid), int(days)
    except Exception:
        return await callback.answer("❌ Noto'g'ri format", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT id, status FROM payments WHERE id=%s", (payment_id,))
                pay = c.fetchone()
            if not pay:
                return await callback.answer("❌ Payment topilmadi", show_alert=True)
            if pay["status"] != "pending":
                return await callback.answer(
                    f"⚠️ Bu to'lov allaqachon {'tasdiqlangan' if pay['status']=='approved' else 'rad etilgan'}!",
                    show_alert=True
                )
            with db.cursor() as c:
                c.execute(
                    "UPDATE users SET access_until = GREATEST(COALESCE(access_until,NOW()),NOW()) + INTERVAL %s DAY, warned=0 WHERE user_id=%s",
                    (days, uid)
                )
            with db.cursor() as c:
                c.execute("UPDATE payments SET status='approved', tariff_days=%s WHERE id=%s", (days, payment_id))
        finally:
            db.close()
    except Exception as e:
        print(f"[APPROVE PAYMENT ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)
    try:
        await callback.bot.send_message(
            uid,
            f"🎉 Premium <b>{days} kun</b> faollashtirildi!\n📅 {datetime.now().strftime('%d.%m.%Y')}",
            reply_markup=menu_premium, parse_mode="HTML"
        )
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")
    admin_name = callback.from_user.username or str(callback.from_user.id)
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + f"\n\n✅ <b>Tasdiqlandi</b> (@{admin_name}, +{days} kun)",
            reply_markup=None, parse_mode="HTML"
        )
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await callback.answer(f"✅ Tasdiqlandi: +{days} kun")


@router.callback_query(F.data.startswith("pReject:"))
async def reject_payment(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "payments"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        _, payment_id, uid = callback.data.split(":")
        payment_id, uid = int(payment_id), int(uid)
    except Exception:
        return await callback.answer("❌ Noto'g'ri format", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT id, status FROM payments WHERE id=%s", (payment_id,))
                pay = c.fetchone()
            if not pay:
                return await callback.answer("❌ Payment topilmadi", show_alert=True)
            if pay["status"] != "pending":
                return await callback.answer(
                    f"⚠️ Bu to'lov allaqachon {'tasdiqlangan' if pay['status']=='approved' else 'rad etilgan'}!",
                    show_alert=True
                )
            with db.cursor() as c:
                c.execute("UPDATE payments SET status='rejected' WHERE id=%s", (payment_id,))
        finally:
            db.close()
    except Exception as e:
        print(f"[REJECT PAYMENT ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)
    try:
        await callback.bot.send_message(uid, "❌ To'lovingiz tasdiqlanmadi.\nChekni qayta tekshirib yuboring.")
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")
    admin_name = callback.from_user.username or str(callback.from_user.id)
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + f"\n\n❌ <b>Rad etildi</b> (@{admin_name})",
            reply_markup=None, parse_mode="HTML"
        )
    except Exception:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await callback.answer("❌ Rad etildi")

# ================================================================
# ════════  PENDING PAYMENTS LIST  ═══════════════════════════════
# ================================================================

@router.message(Command("pendingpay"))
@router.callback_query(F.data == "adm:pending_payments")
async def adm_pending_payments(event: types.Message | types.CallbackQuery):
    uid = event.from_user.id
    if not has_perm(uid, "payments"):
        if isinstance(event, types.CallbackQuery):
            return await event.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        target = event.message
    else:
        target = event
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT p.id, p.user_id, p.created_at, u.username "
                    "FROM payments p LEFT JOIN users u ON p.user_id=u.user_id "
                    "WHERE p.status='pending' ORDER BY p.id DESC"
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[PENDING PAY ERROR] {e}")
        return await target.answer("❌ DB xato.")
    if not rows:
        return await target.answer("✅ Hozircha kutilayotgan to'lovlar yo'q.")
    await target.answer(f"⏳ <b>KUTILAYOTGAN TO'LOVLAR — {len(rows)} ta</b>", parse_mode="HTML")
    for r in rows:
        uname    = f"@{r['username']}" if r.get("username") else "—"
        date_str = r["created_at"].strftime('%d.%m.%Y %H:%M') if r.get("created_at") else "—"
        pay_uid  = r["user_id"]
        pay_id   = r["id"]
        txt = (
            f"🧾 <b>To'lov #{pay_id}</b>\n"
            f"👤 {uname} (ID: <code>{pay_uid}</code>)\n"
            f"📅 {date_str}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ 30 kun",  callback_data=f"pApprove:{pay_id}:{pay_uid}:30"),
                InlineKeyboardButton(text="✅ 90 kun",  callback_data=f"pApprove:{pay_id}:{pay_uid}:90"),
                InlineKeyboardButton(text="✅ 180 kun", callback_data=f"pApprove:{pay_id}:{pay_uid}:180"),
            ],
            [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pReject:{pay_id}:{pay_uid}")]
        ])
        try:
            await target.answer(txt, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            print(f"[PENDING PAY SEND ERROR] {e}")
