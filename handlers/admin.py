import asyncio
import json
from datetime import datetime, timedelta

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from config import OWNER_ID, ALL_PERMS, PERM_LABELS, ORDER_TYPES
from states import BroadcastStates, RevokeStates, SubAdminStates
from db.database import (
    get_db, has_perm, is_any_admin, all_sub_admins, get_sub_admin
)
from keyboards.keyboards import (
    admin_panel_kb, perm_toggle_kb, subadmins_list_kb, subadmin_detail_kb, kb_cancel,
    kb_broadcast_confirm
)
from utils.helpers import (
    get_menu, get_all_user_ids, get_admin_stats, build_admin_text, format_deadline
)
from utils.image import build_users_excel
from config import menu_basic

router = Router()

# ================================================================
# ═════════════════  ADMIN PANEL  ════════════════════════════════
# ================================================================

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    uid = message.from_user.id
    if not is_any_admin(uid):
        return
    stats = get_admin_stats()
    await message.answer(build_admin_text(stats, uid), reply_markup=admin_panel_kb(uid), parse_mode="HTML")


@router.callback_query(F.data == "adm:refresh")
async def adm_refresh(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if not is_any_admin(uid):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    stats = get_admin_stats()
    try:
        await callback.message.edit_text(build_admin_text(stats, uid), reply_markup=admin_panel_kb(uid), parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("🔄 Yangilandi")


@router.callback_query(F.data == "adm:users")
async def adm_users(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "users"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT user_id, username, access_until FROM users WHERE access_until > %s ORDER BY access_until DESC",
                    (datetime.now(),)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        rows = []
    await callback.answer()
    if not rows:
        return await callback.message.answer("❌ Premium userlar yo'q")
    txt = "✅ <b>PREMIUM USERLAR:</b>\n\n"
    for r in rows:
        username     = r["username"] or "—"
        access_until = r["access_until"].strftime('%d.%m.%Y') if r["access_until"] else "—"
        txt += f"@{username} (<code>{r['user_id']}</code>) | {access_until}\n"
    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."
    await callback.message.answer(txt, parse_mode="HTML")


@router.callback_query(F.data == "adm:payments")
async def adm_payments(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "payments"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT id, user_id, tariff_days, status, created_at FROM payments ORDER BY id DESC LIMIT 10")
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        rows = []
    await callback.answer()
    if not rows:
        return await callback.message.answer("❌ To'lovlar yo'q")
    txt = "💳 <b>OXIRGI TO'LOVLAR:</b>\n\n"
    for r in rows:
        icon     = "✅" if r["status"] == "approved" else ("❌" if r["status"] == "rejected" else "⏳")
        date_str = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        txt += f"{icon} #{r['id']} | <code>{r['user_id']}</code> | {r['tariff_days'] or '?'} kun | {date_str}\n"
    await callback.message.answer(txt, parse_mode="HTML")


@router.callback_query(F.data == "adm:expiring")
async def adm_expiring(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "orders"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    now  = datetime.now()
    soon = now + timedelta(days=3)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id, username, access_until FROM users WHERE access_until BETWEEN %s AND %s", (now, soon))
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        rows = []
    await callback.answer()
    if not rows:
        return await callback.message.answer("✅ Tugayotgan obunalar yo'q")
    txt = "⏰ <b>TUGAYOTGAN OBUNALAR (3 kun):</b>\n\n"
    for r in rows:
        username     = r["username"] or "—"
        access_until = r["access_until"].strftime('%d.%m.%Y %H:%M') if r["access_until"] else "—"
        txt += f"@{username} (<code>{r['user_id']}</code>) | {access_until}\n"
    await callback.message.answer(txt, parse_mode="HTML")


@router.callback_query(F.data == "adm:orders")
async def adm_orders(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "orders"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT o.id, o.user_id, u.username, o.type, o.subject, o.topic, o.pages, o.deadline, o.status, o.created_at "
                    "FROM orders o LEFT JOIN users u ON o.user_id = u.user_id "
                    "WHERE o.status IN ('pending','in_progress') ORDER BY o.id DESC"
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        rows = []
    await callback.answer()
    if not rows:
        return await callback.message.answer("✅ Aktiv buyurtmalar yo'q.")
    status_icons = {"pending": "⏳", "in_progress": "🔄"}
    txt = f"📋 <b>AKTIV BUYURTMALAR ({len(rows)} ta)</b>\n{'─'*25}\n\n"
    for r in rows:
        username     = r["username"] or "—"
        type_name    = ORDER_TYPES.get(r["type"], r["type"])
        icon         = status_icons.get(r["status"], "")
        date_str     = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        deadline_txt = format_deadline(r["deadline"])
        txt += (
            f"{icon} #{r['id']} | {type_name}\n👤 @{username} (<code>{r['user_id']}</code>)\n"
            f"📚 {r['subject']} — {r['topic']}\n📄 {r['pages']} s. | ⏰ {deadline_txt} | 📅 {date_str}\n"
            f"/deliver {r['id']} | /delivertext {r['id']}\n{'─'*25}\n"
        )
    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."
    await callback.message.answer(txt, parse_mode="HTML")

# ================= SLASH COMMANDS =================

@router.message(Command("users"))
async def users_cmd(message: types.Message):
    if not has_perm(message.from_user.id, "users"):
        return
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id, username, access_until FROM users WHERE access_until > %s ORDER BY access_until DESC", (datetime.now(),))
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        return await message.answer("❌ DB xato")
    if not rows:
        return await message.answer("❌ Premium userlar yo'q")
    txt = "✅ <b>PREMIUM USERLAR:</b>\n\n"
    for r in rows:
        username     = r["username"] or "—"
        access_until = r["access_until"].strftime('%d.%m.%Y') if r["access_until"] else "—"
        txt += f"@{username} (<code>{r['user_id']}</code>) | {access_until}\n"
    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."
    await message.answer(txt, parse_mode="HTML")


@router.message(Command("payments"))
async def payments_cmd(message: types.Message):
    if not has_perm(message.from_user.id, "payments"):
        return
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT id, user_id, tariff_days, status, created_at FROM payments ORDER BY id DESC LIMIT 10")
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        return await message.answer("❌ DB xato")
    if not rows:
        return await message.answer("❌ To'lovlar yo'q")
    txt = "💳 <b>OXIRGI TO'LOVLAR:</b>\n\n"
    for r in rows:
        icon     = "✅" if r["status"] == "approved" else ("❌" if r["status"] == "rejected" else "⏳")
        date_str = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        txt += f"{icon} #{r['id']} | <code>{r['user_id']}</code> | {r['tariff_days'] or '?'} kun | {date_str}\n"
    await message.answer(txt, parse_mode="HTML")


@router.message(Command("expiring"))
async def expiring_cmd(message: types.Message):
    if not has_perm(message.from_user.id, "orders"):
        return
    now  = datetime.now()
    soon = now + timedelta(days=3)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id, username, access_until FROM users WHERE access_until BETWEEN %s AND %s", (now, soon))
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        return await message.answer("❌ DB xato")
    if not rows:
        return await message.answer("✅ Tugayotgan obunalar yo'q")
    txt = "⏰ <b>TUGAYOTGAN OBUNALAR (3 kun):</b>\n\n"
    for r in rows:
        username     = r["username"] or "—"
        access_until = r["access_until"].strftime('%d.%m.%Y %H:%M') if r["access_until"] else "—"
        txt += f"@{username} (<code>{r['user_id']}</code>) | {access_until}\n"
    await message.answer(txt, parse_mode="HTML")


@router.message(Command("orders"))
async def orders_cmd(message: types.Message):
    if not has_perm(message.from_user.id, "orders"):
        return
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT o.id, o.user_id, u.username, o.type, o.subject, o.topic, o.pages, o.deadline, o.status, o.created_at "
                    "FROM orders o LEFT JOIN users u ON o.user_id = u.user_id "
                    "WHERE o.status IN ('pending','in_progress') ORDER BY o.id DESC"
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        return await message.answer("❌ DB xato")
    if not rows:
        return await message.answer("✅ Aktiv buyurtmalar yo'q.")
    txt = f"📋 <b>AKTIV BUYURTMALAR ({len(rows)} ta)</b>\n{'─'*25}\n\n"
    for r in rows:
        username     = r["username"] or "—"
        type_name    = ORDER_TYPES.get(r["type"], r["type"])
        date_str     = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        deadline_txt = format_deadline(r["deadline"])
        txt += (
            f"🆔 #{r['id']} | {type_name}\n👤 @{username} (<code>{r['user_id']}</code>)\n"
            f"📚 {r['subject']} — {r['topic']}\n📄 {r['pages']} s. | ⏰ {deadline_txt} | 📅 {date_str}\n"
            f"/deliver {r['id']} | /delivertext {r['id']}\n{'─'*25}\n"
        )
    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."
    await message.answer(txt, parse_mode="HTML")

# ================================================================
# ═════════════════  BROADCAST  ══════════════════════════════════
# ================================================================

@router.message(Command("broadcast"))
@router.callback_query(F.data == "adm:broadcast")
async def broadcast_cmd(event: types.Message | types.CallbackQuery, state: FSMContext):
    uid = event.from_user.id
    if not has_perm(uid, "broadcast"):
        if isinstance(event, types.CallbackQuery):
            return await event.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    await state.set_state(BroadcastStates.waiting_message)
    text = "📢 <b>BROADCAST</b>\n\nXabar yuboring — har qanday turdagi:\n• Matn\n• Rasm\n• Fayl\n• Video\n• Forward"
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb_cancel(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb_cancel(), parse_mode="HTML")


@router.message(BroadcastStates.waiting_message)
async def broadcast_preview(message: types.Message, state: FSMContext):
    if message.forward_from or message.forward_from_chat:
        msg_type = "forward"
    elif message.photo:    msg_type = "photo"
    elif message.video:    msg_type = "video"
    elif message.document: msg_type = "document"
    elif message.audio:    msg_type = "audio"
    elif message.voice:    msg_type = "voice"
    elif message.sticker:  msg_type = "sticker"
    elif message.text:     msg_type = "text"
    else:
        return await message.answer("❌ Bu turdagi xabar qo'llab-quvvatlanmaydi.")
    await state.update_data(
        msg_type=msg_type,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        original_text=message.text or message.caption or ""
    )
    user_count = len(get_all_user_ids())
    await state.set_state(BroadcastStates.confirming)
    await message.answer(
        f"📢 <b>BROADCAST PREVIEW</b>\n\n👥 Yuboriladi: <b>{user_count} ta</b>\n📨 Tur: <b>{msg_type}</b>\n\nTasdiqlaysizmi?",
        reply_markup=kb_broadcast_confirm(), parse_mode="HTML"
    )


@router.callback_query(F.data == "bc:send")
async def broadcast_send(callback: types.CallbackQuery, state: FSMContext):
    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
    if not has_perm(callback.from_user.id, "broadcast"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    data         = await state.get_data()
    user_ids     = get_all_user_ids()
    msg_type     = data.get("msg_type", "")
    original_txt = data.get("original_text", "")
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("⏳ Yuborilmoqda...")
    status_msg = await callback.message.reply(f"⏳ Yuborilmoqda... 0/{len(user_ids)}")
    success = failed = blocked = 0
    for i, uid in enumerate(user_ids, 1):
        try:
            if msg_type == "text" and original_txt:
                await callback.bot.send_message(chat_id=uid, text=f"<b>Admin:</b>\n\n{original_txt}", parse_mode="HTML")
            else:
                await callback.bot.copy_message(chat_id=uid, from_chat_id=data["from_chat_id"], message_id=data["message_id"])
            success += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                if msg_type == "text" and original_txt:
                    await callback.bot.send_message(chat_id=uid, text=f"<b>Admin:</b>\n\n{original_txt}", parse_mode="HTML")
                else:
                    await callback.bot.copy_message(chat_id=uid, from_chat_id=data["from_chat_id"], message_id=data["message_id"])
                success += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            blocked += 1  # User botni block qilgan
        except Exception:
            failed += 1
        if i % 20 == 0:
            try:
                await status_msg.edit_text(
                    f"⏳ {i}/{len(user_ids)}\n✅ {success} | ❌ {failed} | 🚫 {blocked}"
                )
            except Exception:
                pass
        await asyncio.sleep(0.035)
    try:
        await status_msg.edit_text(
            f"✅ <b>Broadcast yakunlandi!</b>\n\n"
            f"👥 Jami: <b>{len(user_ids)}</b>\n"
            f"✅ Yuborildi: <b>{success}</b>\n"
            f"❌ Xato: <b>{failed}</b>\n"
            f"🚫 Bloklagan: <b>{blocked}</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data == "bc:cancel")
async def broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("❌ Bekor qilindi")
    await callback.message.reply("❌ Broadcast bekor qilindi.")

# ================================================================
# ═════════════════  REVOKE PREMIUM  ═════════════════════════════
# ================================================================

@router.message(Command("revoke"))
@router.callback_query(F.data == "adm:revoke")
async def revoke_cmd(event: types.Message | types.CallbackQuery, state: FSMContext):
    uid = event.from_user.id
    if not has_perm(uid, "revoke"):
        if isinstance(event, types.CallbackQuery):
            return await event.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT user_id, username, access_until FROM users WHERE access_until > %s ORDER BY access_until DESC",
                    (datetime.now(),)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        rows = []
    if not rows:
        text = "❌ Hozirda premium foydalanuvchilar yo'q."
        if isinstance(event, types.CallbackQuery):
            await event.answer()
            await event.message.answer(text)
        else:
            await event.answer(text)
        return
    buttons = []
    for r in rows:
        uname        = r["username"] or "—"
        access_until = r["access_until"].strftime('%d.%m.%Y') if r["access_until"] else "—"
        buttons.append([InlineKeyboardButton(text=f"🚫 @{uname} | {access_until}", callback_data=f"revokeUser:{r['user_id']}")])
    buttons.append([InlineKeyboardButton(text="❌ Yopish", callback_data="revokeClose")])
    kb   = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = f"🚫 <b>PREMIUM BEKOR QILISH</b>\n\nUserni tanlang:\n(Jami: {len(rows)} ta premium user)"
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("revokeUser:"))
async def revoke_user(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "revoke"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        uid = int(callback.data.split(":")[1])
    except Exception:
        return await callback.answer("❌ Noto'g'ri format", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT username, access_until FROM users WHERE user_id=%s", (uid,))
                user = c.fetchone()
            if not user:
                return await callback.answer("❌ User topilmadi", show_alert=True)
            with db.cursor() as c:
                c.execute("UPDATE users SET access_until=NULL, warned=0 WHERE user_id=%s", (uid,))
        finally:
            db.close()
    except Exception:
        return await callback.answer("❌ DB xato", show_alert=True)
    try:
        await callback.bot.send_message(uid, "⚠️ Sizning premium obunangiz bekor qilindi.", reply_markup=menu_basic)
    except Exception:
        pass
    uname = user["username"] or "—"
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"✅ @{uname} (ID: {uid}) premiumdan chiqarildi.")
    except Exception:
        pass
    await callback.answer(f"✅ @{uname} premiumdan chiqarildi")


@router.callback_query(F.data == "revokeClose")
async def revoke_close(callback: types.CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Yopildi")

# ================================================================
# ═════════════════  LISTUSERS  ══════════════════════════════════
# ================================================================

@router.message(Command("listusers"))
@router.callback_query(F.data == "adm:listusers")
async def listusers_cmd(event: types.Message | types.CallbackQuery):
    uid = event.from_user.id
    if not has_perm(uid, "listusers"):
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
                    """SELECT u.user_id, u.username, u.first_name, u.last_name,
                              u.access_until, u.created_at,
                              COUNT(r.id) AS ref_count
                       FROM users u
                       LEFT JOIN referrals r ON r.referrer_id = u.user_id
                       GROUP BY u.user_id
                       ORDER BY u.created_at DESC"""
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[LISTUSERS DB ERROR] {e}")
        return await target.answer("❌ DB xato.")
    if not rows:
        return await target.answer("❌ Hech qanday foydalanuvchi yo'q.")
    now         = datetime.now()
    total       = len(rows)
    premium_cnt = sum(1 for r in rows if r.get("access_until") and r["access_until"] > now)
    await target.answer(
        f"👥 <b>FOYDALANUVCHILAR RO'YXATI</b>\n\n"
        f"📊 Jami: <b>{total}</b> | ✅ Premium: <b>{premium_cnt}</b> | 👤 Oddiy: <b>{total-premium_cnt}</b>\n\n"
        f"⏳ Excel tayyorlanmoqda...", parse_mode="HTML"
    )
    try:
        excel_bytes = build_users_excel(rows)
        filename    = f"users_{now.strftime('%Y%m%d_%H%M')}.xlsx"
        await target.answer_document(
            BufferedInputFile(excel_bytes, filename=filename),
            caption=(
                f"📊 <b>Foydalanuvchilar ro'yxati</b>\n"
                f"👥 {total} | ✅ {premium_cnt} | 📅 {now.strftime('%d.%m.%Y %H:%M')}"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        await target.answer(f"❌ Excel xato: {e}")

# ================================================================
# ═══════════════  SUB-ADMIN MANAGEMENT  ═════════════════════════
# ================================================================

@router.message(Command("admins"))
@router.callback_query(F.data == "adm:subadmins")
async def subadmins_panel(event: types.Message | types.CallbackQuery):
    uid = event.from_user.id
    if uid != OWNER_ID:
        if isinstance(event, types.CallbackQuery):
            return await event.answer("❌ Faqat owner uchun", show_alert=True)
        return
    admins = all_sub_admins()
    text = (
        f"🛡 <b>SUB-ADMINLAR</b>\n\nJami: <b>{len(admins)}</b> ta sub-admin\n\n"
        + ("\n".join(
            f"• {'@'+a['username'] if a.get('username') else 'ID:'+str(a['user_id'])}  "
            f"({len(json.loads(a['perms']))} ruxsat)"
            for a in admins
        ) if admins else "Hozircha sub-admin yo'q.")
    )
    kb = subadmins_list_kb(admins)
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("subadmView:"))
async def subadm_view(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    target_uid = int(callback.data.split(":")[1])
    row = get_sub_admin(target_uid)
    if not row:
        return await callback.answer("❌ Topilmadi", show_alert=True)
    try:
        perms = json.loads(row["perms"])
    except Exception:
        perms = []
    uname    = f"@{row['username']}" if row.get("username") else f"ID:{target_uid}"
    added_at = row["added_at"].strftime('%d.%m.%Y %H:%M') if row.get("added_at") else "—"
    perm_txt = "\n".join(f"  {'✅' if p in perms else '☐'} {PERM_LABELS.get(p, p)}" for p in ALL_PERMS)
    text = (
        f"🛡 <b>SUB-ADMIN: {uname}</b>\n"
        f"🆔 ID: <code>{target_uid}</code>\n"
        f"📅 Qo'shilgan: {added_at}\n\n"
        f"<b>Ruxsatlar:</b>\n{perm_txt}"
    )
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=subadmin_detail_kb(target_uid), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=subadmin_detail_kb(target_uid), parse_mode="HTML")


@router.callback_query(F.data == "subadmAdd")
async def subadm_add_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    await callback.answer()
    await state.set_state(SubAdminStates.waiting_user_id)
    await callback.message.answer(
        "🛡 <b>YANGI SUB-ADMIN</b>\n\nAdmin qilmoqchi bo'lgan foydalanuvchining <b>User ID</b>sini yuboring:\n<i>Masalan: 123456789</i>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )


@router.message(SubAdminStates.waiting_user_id, F.text)
async def subadm_got_uid(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        return await message.answer("❌ Noto'g'ri format. Faqat raqam kiriting:")
    target_uid = int(text)
    if target_uid == OWNER_ID:
        return await message.answer("❌ O'zingizni sub-admin qila olmaysiz.")
    existing = get_sub_admin(target_uid)
    current_perms = []
    if existing:
        try:
            current_perms = json.loads(existing["perms"])
        except Exception:
            current_perms = []
    username = None
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT username FROM users WHERE user_id=%s", (target_uid,))
                row = c.fetchone()
                if row:
                    username = row["username"]
        finally:
            db.close()
    except Exception:
        pass
    await state.set_state(SubAdminStates.choosing_perms)
    await state.update_data(target_uid=target_uid, current_perms=current_perms, target_username=username)
    uname_str = f"@{username}" if username else f"ID:{target_uid}"
    action    = "tahrirlash" if existing else "qo'shish"
    await message.answer(
        f"🛡 <b>Sub-admin {action}: {uname_str}</b>\n\nQuyidagi ruxsatlarni tanlang.\nTayyor bo'lgach <b>💾 Saqlash</b>ni bosing.",
        reply_markup=perm_toggle_kb(target_uid, current_perms), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("permToggle:"))
async def perm_toggle(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    _, target_uid_str, perm = callback.data.split(":")
    target_uid = int(target_uid_str)
    data = await state.get_data()
    current_perms = list(data.get("current_perms", []))
    if perm in current_perms:
        current_perms.remove(perm)
    else:
        current_perms.append(perm)
    await state.update_data(current_perms=current_perms)
    try:
        await callback.message.edit_reply_markup(reply_markup=perm_toggle_kb(target_uid, current_perms))
    except Exception:
        pass
    await callback.answer(f"{'✅ Yoqildi' if perm in current_perms else '☐ O`chirildi'}: {PERM_LABELS.get(perm, perm)}")


@router.callback_query(F.data.startswith("permSave:"))
async def perm_save(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    target_uid = int(callback.data.split(":")[1])
    data = await state.get_data()
    current_perms   = data.get("current_perms", [])
    target_username = data.get("target_username")
    perms_json = json.dumps(current_perms)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    """INSERT INTO admins (user_id, username, perms, added_at)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE username=%s, perms=%s""",
                    (target_uid, target_username, perms_json, datetime.now(), target_username, perms_json)
                )
        finally:
            db.close()
    except Exception as e:
        print(f"[PERM SAVE ERROR] {e}")
        await callback.answer("❌ DB xato", show_alert=True)
        await state.clear()
        return
    await state.clear()
    uname_str = f"@{target_username}" if target_username else f"ID:{target_uid}"
    perm_txt  = ", ".join(PERM_LABELS.get(p, p) for p in current_perms) or "Hech biri"
    await callback.answer("✅ Saqlandi")
    try:
        await callback.message.edit_text(
            f"✅ <b>Sub-admin saqlandi!</b>\n\n👤 {uname_str}\n🔑 Ruxsatlar: {perm_txt}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Sub-adminlar", callback_data="adm:subadmins")
            ]]),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(f"✅ Sub-admin saqlandi: {uname_str}\nRuxsatlar: {perm_txt}", parse_mode="HTML")
    try:
        perm_list = "\n".join(f"  • {PERM_LABELS.get(p,p)}" for p in current_perms) or "  • Hech biri"
        await callback.bot.send_message(
            target_uid,
            f"🛡 <b>Siz sub-admin sifatida tayinlandingiz!</b>\n\nSizga berilgan ruxsatlar:\n{perm_list}\n\nAdmin panelni ochish uchun /admin buyrug'ini yuboring.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[NOTIFY SUBADMIN ERROR] {e}")


@router.callback_query(F.data == "permCancel")
async def perm_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("❌ Bekor qilindi")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("❌ Bekor qilindi.")


@router.callback_query(F.data.startswith("subadmEdit:"))
async def subadm_edit(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    target_uid = int(callback.data.split(":")[1])
    row = get_sub_admin(target_uid)
    if not row:
        return await callback.answer("❌ Topilmadi", show_alert=True)
    try:
        current_perms = json.loads(row["perms"])
    except Exception:
        current_perms = []
    await state.set_state(SubAdminStates.choosing_perms)
    await state.update_data(target_uid=target_uid, current_perms=current_perms, target_username=row.get("username"))
    uname_str = f"@{row['username']}" if row.get("username") else f"ID:{target_uid}"
    await callback.answer()
    try:
        await callback.message.edit_text(
            f"✏️ <b>Ruxsatlarni o'zgartirish: {uname_str}</b>\n\nRuxsatlarni yoqing yoki o'chiring, so'ng 💾 Saqlash.",
            reply_markup=perm_toggle_kb(target_uid, current_perms), parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"✏️ Ruxsatlarni o'zgartirish: {uname_str}",
            reply_markup=perm_toggle_kb(target_uid, current_perms), parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("subadmDel:"))
async def subadm_delete(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    target_uid = int(callback.data.split(":")[1])
    row = get_sub_admin(target_uid)
    if not row:
        return await callback.answer("❌ Topilmadi", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("DELETE FROM admins WHERE user_id=%s", (target_uid,))
        finally:
            db.close()
    except Exception as e:
        print(f"[SUBADM DELETE ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)
    uname_str = f"@{row['username']}" if row.get("username") else f"ID:{target_uid}"
    await callback.answer(f"✅ {uname_str} o'chirildi")
    try:
        await callback.bot.send_message(target_uid, "⚠️ Sizning admin huquqlaringiz bekor qilindi.")
    except Exception:
        pass
    admins = all_sub_admins()
    text = (
        f"🛡 <b>SUB-ADMINLAR</b>\n\nJami: <b>{len(admins)}</b> ta sub-admin\n\n"
        + ("\n".join(
            f"• {'@'+a['username'] if a.get('username') else 'ID:'+str(a['user_id'])}  "
            f"({len(json.loads(a['perms']))} ruxsat)"
            for a in admins
        ) if admins else "Hozircha sub-admin yo'q.")
    )
    try:
        await callback.message.edit_text(text, reply_markup=subadmins_list_kb(admins), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=subadmins_list_kb(admins), parse_mode="HTML")
