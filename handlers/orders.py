import json
from datetime import datetime, timedelta

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID, ORDER_TYPES, ORDER_LIMIT_PER_MONTH, FILETYPE_LABELS, DEADLINE_OPTIONS
from states import OrderStates, DeliverStates
from db.database import get_db, has_perm, all_sub_admins
from keyboards.keyboards import kb_cancel, kb_pages, kb_filetype, kb_deadline, kb_confirm
from utils.helpers import (
    has_access, get_menu, get_order_monthly_count, get_active_order,
    deadline_str_to_date, format_deadline
)

router = Router()


async def start_order(message: types.Message, state: FSMContext, order_type: str):
    uid = message.from_user.id
    if not has_access(uid):
        return await message.answer(
            "❌ Bu funksiya faqat premium foydalanuvchilar uchun.\n💳 To'lov qilish tugmasini bosing.",
            reply_markup=get_menu(uid)
        )
    active = get_active_order(uid)
    if active:
        type_name = ORDER_TYPES.get(active["type"], active["type"])
        return await message.answer(
            f"⚠️ Sizda hali bajarilmagan buyurtma bor:\n🆔 #{active['id']} | {type_name}\n"
            f"📚 {active['subject']} — {active['topic']}\n⏳ Holati: {active['status']}\n\n"
            f"Yangi buyurtma berish uchun avvalgi buyurtma tugashini kuting.",
            reply_markup=get_menu(uid)
        )
    used = get_order_monthly_count(uid)
    if used >= ORDER_LIMIT_PER_MONTH:
        return await message.answer(
            f"⚠️ Siz bu oy {ORDER_LIMIT_PER_MONTH} ta buyurtma limitidan foydalandingiz.\nKeyingi oy yangilanadi.",
            reply_markup=get_menu(uid)
        )
    remaining  = ORDER_LIMIT_PER_MONTH - used
    type_label = ORDER_TYPES.get(order_type, order_type)
    await state.set_state(OrderStates.entering_subject)
    await state.update_data(order_type=order_type)
    await message.answer(
        f"{type_label} buyurtmasi\n📊 Bu oy: {used}/{ORDER_LIMIT_PER_MONTH} (qoldi: {remaining})\n\n"
        f"📚 Fan nomini kiriting:\n<i>Masalan: Matematika, Fizika, Tarix...</i>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )


@router.message(F.text == "📝 Referat yozdirish")
async def order_referat(message: types.Message, state: FSMContext):
    await start_order(message, state, "referat")


@router.message(F.text == "📘 Mustaqil ish yozdirish")
async def order_mustaqil(message: types.Message, state: FSMContext):
    await start_order(message, state, "mustaqil")


@router.message(OrderStates.entering_subject)
async def order_subject(message: types.Message, state: FSMContext):
    subject = message.text.strip()
    if len(subject) < 2 or len(subject) > 100:
        return await message.answer("❌ Fan nomi 2-100 ta belgi bo'lishi kerak.")
    await state.update_data(subject=subject)
    await state.set_state(OrderStates.entering_topic)
    await message.answer(
        f"✅ Fan: <b>{subject}</b>\n\n📝 Mavzuni kiriting:\n<i>Masalan: Ikkinchi jahon urushi sabablari</i>",
        parse_mode="HTML"
    )


@router.message(OrderStates.entering_topic)
async def order_topic(message: types.Message, state: FSMContext):
    topic = message.text.strip()
    if len(topic) < 3 or len(topic) > 200:
        return await message.answer("❌ Mavzu 3-200 ta belgi bo'lishi kerak.")
    await state.update_data(topic=topic)
    await state.set_state(OrderStates.choosing_pages)
    await message.answer(
        f"✅ Mavzu: <b>{topic}</b>\n\n📄 Necha sahifa kerak? (maksimal 25)",
        reply_markup=kb_pages(), parse_mode="HTML"
    )


@router.message(OrderStates.choosing_pages)
async def order_pages(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 25):
        return await message.answer("❌ 1-25 orasida son kiriting:")
    await state.update_data(pages=int(text))
    await state.set_state(OrderStates.choosing_filetype)
    await message.answer(
        f"✅ Sahifalar: <b>{text}</b>\n\n📁 Fayl turini tanlang:",
        reply_markup=kb_filetype(), parse_mode="HTML"
    )


@router.message(OrderStates.choosing_filetype)
async def order_filetype(message: types.Message, state: FSMContext):
    filetype = message.text.strip()
    if filetype not in FILETYPE_LABELS:
        return await message.answer("❌ Tugmalardan birini tanlang:")
    await state.update_data(filetype=filetype)
    await state.set_state(OrderStates.choosing_deadline)
    await message.answer(
        f"✅ Fayl turi: <b>{filetype}</b>\n\n⏰ Qachon tayyor bo'lishi kerak?",
        reply_markup=kb_deadline(), parse_mode="HTML"
    )


@router.message(OrderStates.choosing_deadline)
async def order_deadline(message: types.Message, state: FSMContext):
    deadline = message.text.strip()
    if deadline not in DEADLINE_OPTIONS:
        return await message.answer("❌ Tugmalardan birini tanlang:")
    await state.update_data(deadline=deadline)
    await state.set_state(OrderStates.confirming)
    data          = await state.get_data()
    type_name     = ORDER_TYPES.get(data["order_type"], data["order_type"])
    deadline_date = datetime.now() + timedelta(days=int(deadline.split()[0]))
    summary = (
        f"📋 BUYURTMA MA'LUMOTLARI\n{'─'*25}\n"
        f"📌 Tur:       {type_name}\n📚 Fan:       {data['subject']}\n"
        f"📝 Mavzu:     {data['topic']}\n📄 Sahifa:    {data['pages']}\n"
        f"📁 Fayl turi: {data['filetype']}\n⏰ Muddat:    {deadline_date.strftime('%d.%m.%Y')} ({deadline})\n"
        f"{'─'*25}\n\n✅ Tasdiqlaysizmi?"
    )
    await message.answer(summary, reply_markup=kb_confirm())


@router.message(OrderStates.confirming, F.text == "✅ Tasdiqlash")
async def order_confirm(message: types.Message, state: FSMContext):
    uid           = message.from_user.id
    data          = await state.get_data()
    deadline_str  = data["deadline"]
    deadline_date = deadline_str_to_date(deadline_str)
    filetype      = data.get("filetype", "📄 PDF")
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "INSERT INTO orders (user_id, type, subject, topic, pages, filetype, deadline, status, created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s)",
                    (uid, data["order_type"], data["subject"], data["topic"], data["pages"], filetype, deadline_date, datetime.now())
                )
                order_id = c.lastrowid
        finally:
            db.close()
    except Exception as e:
        print(f"[ORDER INSERT ERROR] {e}")
        return await message.answer("❌ Buyurtmani saqlashda xato.")
    await state.clear()
    type_name = ORDER_TYPES.get(data["order_type"], data["order_type"])
    await message.answer(
        f"✅ Buyurtma qabul qilindi!\n🆔 #{order_id}\n📁 {filetype}\n⏰ {deadline_date}\n⏳ Admin ko'rib chiqadi.",
        reply_markup=get_menu(uid)
    )
    username  = message.from_user.username or "—"
    admin_txt = (
        f"🆕 <b>YANGI BUYURTMA #{order_id}</b>\n{'─'*25}\n"
        f"👤 @{username} (ID: <code>{uid}</code>)\n"
        f"📌 {type_name}\n📚 {data['subject']}\n📝 {data['topic']}\n"
        f"📄 {data['pages']} sahifa\n📁 {filetype}\n⏰ {deadline_date} ({deadline_str})\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"oAccept:{order_id}:{uid}"),
        InlineKeyboardButton(text="❌ Rad etish",    callback_data=f"oReject:{order_id}:{uid}")
    ]])
    targets = [OWNER_ID] + [a["user_id"] for a in all_sub_admins() if "orders" in json.loads(a.get("perms", "[]"))]
    for t in targets:
        try:
            await message.bot.send_message(t, admin_txt, reply_markup=admin_kb, parse_mode="HTML")
        except Exception as e:
            print(f"[ORDER NOTIFY ERROR uid={t}] {e}")

# ================= ADMIN ORDER CALLBACKS =================

@router.callback_query(F.data.startswith("oAccept:"))
async def order_accept(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "orders"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        _, order_id, uid = callback.data.split(":")
        order_id, uid = int(order_id), int(uid)
    except Exception:
        return await callback.answer("❌ Noto'g'ri format", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("UPDATE orders SET status='in_progress' WHERE id=%s", (order_id,))
        finally:
            db.close()
    except Exception as e:
        print(f"[ORDER ACCEPT ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)
    try:
        await callback.bot.send_message(uid, f"✅ Buyurtmangiz #{order_id} qabul qilindi!\n⏳ Tayyor bo'lganda yuboriladi.")
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(
            f"✅ #{order_id} qabul qilindi.\n\n📎 Fayl: <code>/deliver {order_id}</code>\n✏️ Matn: <code>/delivertext {order_id}</code>",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("✅ Qabul qilindi")


@router.callback_query(F.data.startswith("oReject:"))
async def order_reject_cb(callback: types.CallbackQuery):
    if not has_perm(callback.from_user.id, "orders"):
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    try:
        _, order_id, uid = callback.data.split(":")
        order_id, uid = int(order_id), int(uid)
    except Exception:
        return await callback.answer("❌ Noto'g'ri format", show_alert=True)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("UPDATE orders SET status='rejected' WHERE id=%s", (order_id,))
        finally:
            db.close()
    except Exception as e:
        print(f"[ORDER REJECT ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)
    try:
        await callback.bot.send_message(uid, f"❌ Buyurtmangiz #{order_id} rad etildi.")
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"❌ #{order_id} rad etildi.")
    except Exception:
        pass
    await callback.answer("❌ Rad etildi")

# ================= DELIVER — FILE =================

@router.message(Command("deliver"))
async def deliver_file_cmd(message: types.Message, state: FSMContext):
    if not has_perm(message.from_user.id, "orders"):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("❌ Ishlatish: /deliver {order_id}")
    order_id = int(args[1])
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT id, user_id, type, subject, topic, status FROM orders WHERE id=%s", (order_id,))
                order = c.fetchone()
        finally:
            db.close()
    except Exception:
        return await message.answer("❌ DB xato")
    if not order:
        return await message.answer(f"❌ #{order_id} topilmadi")
    if order["status"] == "done":
        return await message.answer(f"⚠️ #{order_id} allaqachon bajarilgan")
    type_name = ORDER_TYPES.get(order["type"], order["type"])
    await state.set_state(DeliverStates.waiting_file)
    await state.update_data(order_id=order_id, target_uid=order["user_id"])
    await message.answer(
        f"📤 #{order_id} uchun fayl yuboring:\n👤 {order['user_id']}\n📌 {type_name} | {order['subject']} — {order['topic']}\n\nFayl yuboring:",
        reply_markup=kb_cancel()
    )


@router.message(DeliverStates.waiting_file, F.document)
async def deliver_file_send(message: types.Message, state: FSMContext):
    data       = await state.get_data()
    order_id   = data["order_id"]
    target_uid = data["target_uid"]
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT subject, topic, type FROM orders WHERE id=%s", (order_id,))
                order = c.fetchone()
            with db.cursor() as c:
                c.execute("UPDATE orders SET status='done' WHERE id=%s", (order_id,))
        finally:
            db.close()
    except Exception:
        await message.answer("❌ DB xato")
        await state.clear()
        return
    type_name = ORDER_TYPES.get(order["type"], order["type"])
    caption   = f"✅ Buyurtmangiz tayyor!\n🆔 #{order_id} | {type_name}\n📚 {order['subject']} — {order['topic']}"
    try:
        await message.bot.send_document(target_uid, message.document.file_id, caption=caption)
        await message.answer(f"✅ Fayl yuborildi (#{order_id})", reply_markup=get_menu(message.from_user.id))
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    await state.clear()

# ================= DELIVER — TEXT =================

@router.message(Command("delivertext"))
async def deliver_text_cmd(message: types.Message, state: FSMContext):
    if not has_perm(message.from_user.id, "orders"):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("❌ Ishlatish: /delivertext {order_id}")
    order_id = int(args[1])
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT id, user_id, type, subject, topic, status FROM orders WHERE id=%s", (order_id,))
                order = c.fetchone()
        finally:
            db.close()
    except Exception:
        return await message.answer("❌ DB xato")
    if not order:
        return await message.answer(f"❌ #{order_id} topilmadi")
    if order["status"] == "done":
        return await message.answer(f"⚠️ #{order_id} allaqachon bajarilgan")
    type_name = ORDER_TYPES.get(order["type"], order["type"])
    await state.set_state(DeliverStates.waiting_text)
    await state.update_data(order_id=order_id, target_uid=order["user_id"])
    await message.answer(
        f"✏️ #{order_id} uchun matn yuboring:\n👤 {order['user_id']}\n📌 {type_name} | {order['subject']} — {order['topic']}\n\nMatnni yozing:",
        reply_markup=kb_cancel()
    )


@router.message(DeliverStates.waiting_text, F.text)
async def deliver_text_send(message: types.Message, state: FSMContext):
    data       = await state.get_data()
    order_id   = data["order_id"]
    target_uid = data["target_uid"]
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT subject, topic, type FROM orders WHERE id=%s", (order_id,))
                order = c.fetchone()
            with db.cursor() as c:
                c.execute("UPDATE orders SET status='done' WHERE id=%s", (order_id,))
        finally:
            db.close()
    except Exception:
        await message.answer("❌ DB xato")
        await state.clear()
        return
    type_name = ORDER_TYPES.get(order["type"], order["type"])
    header    = f"✅ Buyurtmangiz tayyor!\n🆔 #{order_id} | {type_name}\n📚 {order['subject']} — {order['topic']}\n{'─'*25}\n\n"
    try:
        await message.bot.send_message(target_uid, header + message.text)
        await message.answer(f"✅ Matn yuborildi (#{order_id})", reply_markup=get_menu(message.from_user.id))
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    await state.clear()

# ================= MY ORDERS =================

@router.message(F.text == "📋 Buyurtmalarim")
async def my_orders(message: types.Message):
    uid = message.from_user.id
    if not has_access(uid):
        return await message.answer("❌ Bu funksiya premium foydalanuvchilar uchun.")
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT id, type, subject, topic, pages, deadline, status, created_at "
                    "FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 10",
                    (uid,)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception:
        return await message.answer("❌ Xato yuz berdi.")
    if not rows:
        return await message.answer("📋 Hali buyurtmalar yo'q.")
    used      = get_order_monthly_count(uid)
    remaining = max(0, ORDER_LIMIT_PER_MONTH - used)
    status_icons = {
        "pending": "⏳ Kutilmoqda", "in_progress": "🔄 Jarayonda",
        "done": "✅ Bajarildi", "rejected": "❌ Rad etildi"
    }
    txt = f"📋 BUYURTMALARIM\n📊 Bu oy: {used}/{ORDER_LIMIT_PER_MONTH} (qoldi: {remaining})\n{'─'*25}\n\n"
    for r in rows:
        txt += (
            f"🆔 #{r['id']} | {ORDER_TYPES.get(r['type'], r['type'])}\n"
            f"📚 {r['subject']} — {r['topic']}\n"
            f"📄 {r['pages']} sahifa | ⏰ {format_deadline(r['deadline'])}\n"
            f"📅 {r['created_at'].strftime('%d.%m.%Y') if r['created_at'] else '—'} | {status_icons.get(r['status'], r['status'])}\n{'─'*25}\n"
        )
    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."
    await message.answer(txt)
