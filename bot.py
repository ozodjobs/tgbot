import os
import re
import uuid
import asyncio
from datetime import datetime, timedelta

import pymysql
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from dotenv import load_dotenv
from PIL import Image

# ================= CONFIG =================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = {6875167708}

PAYNET_LINK = "https://app.paynet.uz/?m=49156&i=1abfad1a-2da7-4d8d-8509-39f59b32d538"

TARIFFS = {
    30:  "1 oy – 20 000 so'm",
    90:  "3 oy – 50 000 so'm",
    180: "6 oy – 90 000 so'm"
}

ORDER_LIMIT_PER_MONTH = 10

DEADLINE_OPTIONS = ["1 kun", "2 kun", "3 kun", "5 kun", "7 kun", "10 kun"]

ORDER_TYPES = {
    "referat":  "📝 Referat",
    "mustaqil": "📘 Mustaqil ish"
}

FILETYPE_LABELS = [
    "📄 PDF",
    "📝 Word (.docx)",
    "📊 Excel (.xlsx)",
    "📊 PowerPoint (.pptx)"
]

# ================= FSM STATES =================
class PDFStates(StatesGroup):
    collecting_images = State()
    waiting_pdf_name  = State()

class PaymentStates(StatesGroup):
    waiting_check = State()

class OrderStates(StatesGroup):
    entering_subject  = State()
    entering_topic    = State()
    choosing_pages    = State()
    choosing_filetype = State()
    choosing_deadline = State()
    confirming        = State()

class DeliverStates(StatesGroup):
    waiting_file = State()
    waiting_text = State()

class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirming      = State()

class RevokeStates(StatesGroup):
    waiting_user_id = State()

# ================= DB =================
def get_db():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),      # Railway uses custom port
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10                          # Prevents hanging on bad connection
    )

# ================= BOT =================
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ================= MENUS =================
menu_basic = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 PDF yaratish")],
        [KeyboardButton(text="💳 To'lov qilish"), KeyboardButton(text="✅ To'lov qildim")],
        [KeyboardButton(text="🔄 Tozalash")]
    ],
    resize_keyboard=True
)

menu_premium = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 PDF yaratish")],
        [KeyboardButton(text="📝 Referat yozdirish")],
        [KeyboardButton(text="📘 Mustaqil ish yozdirish")],
        [KeyboardButton(text="📋 Buyurtmalarim")],
        [KeyboardButton(text="🔄 Tozalash")]
    ],
    resize_keyboard=True
)

def menu_pdf_collecting(count: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📥 PDF yaratish"),
                KeyboardButton(text=f"🖼 Rasmlar: {count}")
            ],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

# ================= ADMIN INLINE PANEL =================
def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Userlar",      callback_data="adm:users"),
            InlineKeyboardButton(text="💳 To'lovlar",    callback_data="adm:payments"),
        ],
        [
            InlineKeyboardButton(text="⏰ Tugayotganlar", callback_data="adm:expiring"),
            InlineKeyboardButton(text="📋 Buyurtmalar",  callback_data="adm:orders"),
        ],
        [
            InlineKeyboardButton(text="📢 Broadcast",    callback_data="adm:broadcast"),
            InlineKeyboardButton(text="🚫 Premium bekor", callback_data="adm:revoke"),
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash",    callback_data="adm:refresh"),
        ]
    ])

# ================= KEYBOARDS =================
def kb_pages():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="5"),  KeyboardButton(text="10"), KeyboardButton(text="15")],
            [KeyboardButton(text="20"), KeyboardButton(text="25")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def kb_filetype():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 PDF"),            KeyboardButton(text="📝 Word (.docx)")],
            [KeyboardButton(text="📊 Excel (.xlsx)"),  KeyboardButton(text="📊 PowerPoint (.pptx)")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def kb_deadline():
    row1 = [KeyboardButton(text=d) for d in DEADLINE_OPTIONS[:3]]
    row2 = [KeyboardButton(text=d) for d in DEADLINE_OPTIONS[3:]]
    return ReplyKeyboardMarkup(
        keyboard=[row1, row2, [KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def kb_confirm():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Tasdiqlash")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

def kb_cancel():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def kb_broadcast_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yuborish",     callback_data="bc:send"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="bc:cancel"),
        ]
    ])

# ================= HELPERS =================
def has_access(uid: int) -> bool:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT access_until FROM users WHERE user_id=%s", (uid,))
                row = c.fetchone()
            return bool(row and row["access_until"] and row["access_until"] > datetime.now())
        finally:
            db.close()
    except Exception as e:
        print(f"[has_access ERROR] {e}")
        return False

def get_menu(uid: int):
    return menu_premium if has_access(uid) else menu_basic

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\s\-]', '', name, flags=re.UNICODE).strip()
    return name or "document"

def cleanup_files(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

def format_deadline(deadline_val) -> str:
    if not deadline_val:
        return "—"
    if hasattr(deadline_val, "strftime"):
        return deadline_val.strftime("%d.%m.%Y")
    return str(deadline_val)

def get_order_monthly_count(uid: int) -> int:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                month_start = datetime.now().replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
                c.execute(
                    "SELECT COUNT(*) AS c FROM orders "
                    "WHERE user_id=%s AND created_at >= %s",
                    (uid, month_start)
                )
                return c.fetchone()["c"]
        finally:
            db.close()
    except Exception as e:
        print(f"[get_order_monthly_count ERROR] {e}")
        return 0

def get_active_order(uid: int):
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT id, type, subject, topic, status FROM orders "
                    "WHERE user_id=%s AND status IN ('pending','in_progress') "
                    "ORDER BY id DESC LIMIT 1",
                    (uid,)
                )
                return c.fetchone()
        finally:
            db.close()
    except Exception as e:
        print(f"[get_active_order ERROR] {e}")
        return None

def deadline_str_to_date(deadline_str: str) -> str:
    try:
        days = int(deadline_str.split()[0])
        return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

def get_all_user_ids() -> list:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id FROM users")
                return [r["user_id"] for r in c.fetchall()]
        finally:
            db.close()
    except Exception as e:
        print(f"[get_all_user_ids ERROR] {e}")
        return []

def get_admin_stats() -> dict:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT COUNT(*) AS c FROM users")
                total = c.fetchone()["c"]

                c.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE access_until > %s",
                    (datetime.now(),)
                )
                premium = c.fetchone()["c"]

                c.execute("SELECT COUNT(*) AS c FROM payments WHERE status='pending'")
                pending_pay = c.fetchone()["c"]

                c.execute(
                    "SELECT COUNT(*) AS c FROM orders "
                    "WHERE status IN ('pending','in_progress')"
                )
                active_orders = c.fetchone()["c"]

            return {
                "total": total,
                "premium": premium,
                "pending_pay": pending_pay,
                "active_orders": active_orders
            }
        finally:
            db.close()
    except Exception as e:
        print(f"[get_admin_stats ERROR] {e}")
        return {"total": 0, "premium": 0, "pending_pay": 0, "active_orders": 0}

def build_admin_text(stats: dict) -> str:
    return (
        f"📊 <b>ADMIN PANEL</b>\n\n"
        f"👤 Jami userlar:        <b>{stats['total']}</b>\n"
        f"✅ Premium:             <b>{stats['premium']}</b>\n"
        f"⏳ Kutilayotgan to'lov: <b>{stats['pending_pay']}</b>\n"
        f"📋 Aktiv buyurtmalar:   <b>{stats['active_orders']}</b>\n\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

# ================= START =================
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    uid      = message.from_user.id
    username = message.from_user.username or ""

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id FROM users WHERE user_id=%s", (uid,))
                existing = c.fetchone()
                c.execute(
                    "INSERT IGNORE INTO users (user_id, username, created_at) VALUES (%s,%s,%s)",
                    (uid, username, datetime.now())
                )

            if not existing:
                admin_id = next(iter(ADMIN_IDS))
                try:
                    await bot.send_message(
                        admin_id,
                        f"🆕 <b>YANGI FOYDALANUVCHI</b>\n"
                        f"👤 @{username or '—'} (ID: <code>{uid}</code>)\n"
                        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"[NEW USER NOTIFY ERROR] {e}")
        finally:
            db.close()
    except Exception as e:
        print(f"[START DB ERROR] {e}")

    await state.clear()
    await message.answer("👋 Xush kelibsiz!", reply_markup=get_menu(uid))

# ================= RESET / CANCEL =================
@dp.message(F.text == "🔄 Tozalash")
async def reset(message: types.Message, state: FSMContext):
    data = await state.get_data()
    for p in data.get("images", []):
        cleanup_files(p)
    await state.clear()
    await message.answer("🔄 Tozalandi", reply_markup=get_menu(message.from_user.id))

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_any(message: types.Message, state: FSMContext):
    data = await state.get_data()
    for p in data.get("images", []):
        cleanup_files(p)
    await state.clear()
    await message.answer("❌ Bekor qilindi", reply_markup=get_menu(message.from_user.id))

# ================= PDF =================
@dp.message(F.text == "📄 PDF yaratish")
async def pdf_start(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state == PDFStates.collecting_images.state:
        data   = await state.get_data()
        images = data.get("images", [])
        if images:
            return await message.answer(
                f"📸 {len(images)} ta rasm bor.\n"
                f"Yana rasm yuboring yoki '📥 PDF yaratish' ni bosing.",
                reply_markup=menu_pdf_collecting(len(images))
            )

    await state.set_state(PDFStates.collecting_images)
    await state.update_data(images=[])
    await message.answer(
        "📸 Rasmlarni yuboring.\n"
        "Hammasi tayyor bo'lgach '📥 PDF yaratish' tugmasini bosing.",
        reply_markup=menu_pdf_collecting(0)
    )

@dp.message(PDFStates.collecting_images, F.photo)
async def pdf_add_image(message: types.Message, state: FSMContext):
    uid  = message.from_user.id
    file = await bot.get_file(message.photo[-1].file_id)
    path = f"/tmp/img_{uid}_{uuid.uuid4().hex}.jpg"   # /tmp is safe on Railway
    await bot.download_file(file.file_path, path)

    data   = await state.get_data()
    images = data.get("images", [])
    images.append(path)
    await state.update_data(images=images)

    await message.answer(
        f"✅ Rasm qo'shildi! Jami: {len(images)} ta\n"
        f"Yana rasm yuboring yoki '📥 PDF yaratish' ni bosing.",
        reply_markup=menu_pdf_collecting(len(images))
    )

@dp.message(PDFStates.collecting_images, F.text == "📥 PDF yaratish")
async def pdf_ask_name(message: types.Message, state: FSMContext):
    data   = await state.get_data()
    images = data.get("images", [])

    if not images:
        return await message.answer(
            "❌ Hali rasm yuborilmagan. Avval rasmlarni yuboring.",
            reply_markup=menu_pdf_collecting(0)
        )

    await state.set_state(PDFStates.waiting_pdf_name)
    await message.answer(
        f"✅ {len(images)} ta rasm tayyor.\n\n"
        f"📝 PDF uchun nom kiriting:",
        reply_markup=kb_cancel()
    )

@dp.message(PDFStates.waiting_pdf_name, F.text)
async def pdf_create(message: types.Message, state: FSMContext):
    data     = await state.get_data()
    images   = data.get("images", [])
    pdf_path = None

    if not images:
        await state.clear()
        return await message.answer(
            "❌ Rasm topilmadi. Qaytadan boshlang.",
            reply_markup=get_menu(message.from_user.id)
        )

    safe_name = sanitize_filename(message.text)
    pdf_path  = f"/tmp/{safe_name}_{uuid.uuid4().hex}.pdf"   # /tmp is safe on Railway
    await message.answer("⏳ PDF yaratilmoqda...")

    try:
        pil_images = []
        for p in images:
            img = Image.open(p).convert("RGB")
            pil_images.append(img)

        pil_images[0].save(pdf_path, save_all=True, append_images=pil_images[1:])
        for img in pil_images:
            img.close()

        await message.answer_document(
            FSInputFile(pdf_path, filename=f"{safe_name}.pdf"),
            caption=f"✅ PDF tayyor! ({len(images)} ta rasm)"
        )
    except Exception as e:
        await message.answer(f"❌ Xato yuz berdi: {e}")
    finally:
        cleanup_files(*images, pdf_path)
        await state.clear()

    await message.answer("✅ Bajarildi!", reply_markup=get_menu(message.from_user.id))

# ================= PAYMENT =================
@dp.message(F.text == "💳 To'lov qilish")
async def payment_info(message: types.Message):
    txt = "💳 Tariflar:\n\n"
    for v in TARIFFS.values():
        txt += f"• {v}\n"
    txt += f"\n👉 To'lov:\n{PAYNET_LINK}"
    await message.answer(txt)

@dp.message(F.text == "✅ To'lov qildim")
async def wait_for_check(message: types.Message, state: FSMContext):
    await state.set_state(PaymentStates.waiting_check)
    await message.answer("🧾 Chekni yuboring (rasm yoki PDF)")

@dp.message(PaymentStates.waiting_check, F.photo | F.document)
async def receive_check(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "INSERT INTO payments (user_id, status, created_at) "
                    "VALUES (%s, 'pending', %s)",
                    (uid, datetime.now())
                )
                payment_id = c.lastrowid
        finally:
            db.close()
    except Exception as e:
        print(f"[PAYMENT INSERT ERROR] {e}")
        await message.answer("❌ Xato yuz berdi. Qaytadan urinib ko'ring.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ 30 kun",  callback_data=f"pApprove:{payment_id}:{uid}:30"),
            InlineKeyboardButton(text="✅ 90 kun",  callback_data=f"pApprove:{payment_id}:{uid}:90"),
            InlineKeyboardButton(text="✅ 180 kun", callback_data=f"pApprove:{payment_id}:{uid}:180"),
        ],
        [
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pReject:{payment_id}:{uid}")
        ]
    ])

    username = message.from_user.username or "—"
    caption  = (
        f"🧾 <b>TO'LOV CHEKI</b>\n"
        f"👤 @{username} (ID: <code>{uid}</code>)\n"
        f"🆔 Payment ID: {payment_id}\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    admin_id = next(iter(ADMIN_IDS))

    try:
        if message.photo:
            await bot.send_photo(
                admin_id, message.photo[-1].file_id,
                caption=caption, reply_markup=kb, parse_mode="HTML"
            )
        else:
            await bot.send_document(
                admin_id, message.document.file_id,
                caption=caption, reply_markup=kb, parse_mode="HTML"
            )
    except Exception as e:
        print(f"[ADMIN SEND ERROR] {e}")
        await message.answer("❌ Chekni adminga yuborishda xato. Qaytadan urinib ko'ring.")
        return

    await message.answer("⏳ Chek yuborildi. 24 soat ichida javob beriladi.")

# ================= APPROVE / REJECT PAYMENT =================
@dp.callback_query(F.data.startswith("pApprove:"))
async def approve_payment(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
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
                c.execute("SELECT id FROM payments WHERE id=%s", (payment_id,))
                if not c.fetchone():
                    return await callback.answer("❌ Payment topilmadi", show_alert=True)

            with db.cursor() as c:
                c.execute(
                    """UPDATE users
                       SET access_until = GREATEST(COALESCE(access_until, NOW()), NOW())
                                          + INTERVAL %s DAY,
                           warned = 0
                       WHERE user_id = %s""",
                    (days, uid)
                )
            with db.cursor() as c:
                c.execute(
                    "UPDATE payments SET status='approved', tariff_days=%s WHERE id=%s",
                    (days, payment_id)
                )
        finally:
            db.close()
    except Exception as e:
        print(f"[APPROVE PAYMENT ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)

    try:
        await bot.send_message(
            uid,
            f"🎉 Premium <b>{days} kun</b> faollashtirildi!\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y')}",
            reply_markup=menu_premium,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"✅ Tasdiqlandi: user {uid} → +{days} kun")
    except Exception:
        pass

    await callback.answer("✅ Tasdiqlandi")

@dp.callback_query(F.data.startswith("pReject:"))
async def reject_payment(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
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
                c.execute("SELECT id FROM payments WHERE id=%s", (payment_id,))
                if not c.fetchone():
                    return await callback.answer("❌ Payment topilmadi", show_alert=True)
            with db.cursor() as c:
                c.execute("UPDATE payments SET status='rejected' WHERE id=%s", (payment_id,))
        finally:
            db.close()
    except Exception as e:
        print(f"[REJECT PAYMENT ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)

    try:
        await bot.send_message(
            uid,
            "❌ To'lovingiz tasdiqlanmadi.\n"
            "Chekni qayta tekshirib yuboring yoki admin bilan bog'laning."
        )
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"❌ Rad etildi: payment {payment_id}")
    except Exception:
        pass

    await callback.answer("❌ Rad etildi")

# ================= ORDER FLOW =================
async def start_order(message: types.Message, state: FSMContext, order_type: str):
    uid = message.from_user.id

    if not has_access(uid):
        return await message.answer(
            "❌ Bu funksiya faqat premium foydalanuvchilar uchun.\n"
            "💳 To'lov qilish tugmasini bosing.",
            reply_markup=get_menu(uid)
        )

    active = get_active_order(uid)
    if active:
        type_name = ORDER_TYPES.get(active["type"], active["type"])
        return await message.answer(
            f"⚠️ Sizda hali bajarilmagan buyurtma bor:\n"
            f"🆔 #{active['id']} | {type_name}\n"
            f"📚 {active['subject']} — {active['topic']}\n"
            f"⏳ Holati: {active['status']}\n\n"
            f"Yangi buyurtma berish uchun avvalgi buyurtma tugashini kuting.",
            reply_markup=get_menu(uid)
        )

    used = get_order_monthly_count(uid)
    if used >= ORDER_LIMIT_PER_MONTH:
        return await message.answer(
            f"⚠️ Siz bu oy {ORDER_LIMIT_PER_MONTH} ta buyurtma limitidan foydalandingiz.\n"
            f"Keyingi oy yangilanadi.",
            reply_markup=get_menu(uid)
        )

    remaining  = ORDER_LIMIT_PER_MONTH - used
    type_label = ORDER_TYPES.get(order_type, order_type)

    await state.set_state(OrderStates.entering_subject)
    await state.update_data(order_type=order_type)

    await message.answer(
        f"{type_label} buyurtmasi\n"
        f"📊 Bu oy: {used}/{ORDER_LIMIT_PER_MONTH} (qoldi: {remaining})\n\n"
        f"📚 Fan nomini kiriting:\n"
        f"<i>Masalan: Matematika, Fizika, Tarix...</i>",
        reply_markup=kb_cancel(),
        parse_mode="HTML"
    )

@dp.message(F.text == "📝 Referat yozdirish")
async def order_referat(message: types.Message, state: FSMContext):
    await start_order(message, state, "referat")

@dp.message(F.text == "📘 Mustaqil ish yozdirish")
async def order_mustaqil(message: types.Message, state: FSMContext):
    await start_order(message, state, "mustaqil")

@dp.message(OrderStates.entering_subject)
async def order_subject(message: types.Message, state: FSMContext):
    subject = message.text.strip()
    if len(subject) < 2 or len(subject) > 100:
        return await message.answer("❌ Fan nomi 2-100 ta belgi bo'lishi kerak. Qaytadan kiriting:")
    await state.update_data(subject=subject)
    await state.set_state(OrderStates.entering_topic)
    await message.answer(
        f"✅ Fan: <b>{subject}</b>\n\n"
        f"📝 Mavzuni kiriting:\n"
        f"<i>Masalan: Ikkinchi jahon urushi sabablari</i>",
        parse_mode="HTML"
    )

@dp.message(OrderStates.entering_topic)
async def order_topic(message: types.Message, state: FSMContext):
    topic = message.text.strip()
    if len(topic) < 3 or len(topic) > 200:
        return await message.answer("❌ Mavzu 3-200 ta belgi bo'lishi kerak. Qaytadan kiriting:")
    await state.update_data(topic=topic)
    await state.set_state(OrderStates.choosing_pages)
    await message.answer(
        f"✅ Mavzu: <b>{topic}</b>\n\n"
        f"📄 Necha sahifa kerak? (maksimal 25)",
        reply_markup=kb_pages(),
        parse_mode="HTML"
    )

@dp.message(OrderStates.choosing_pages)
async def order_pages(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 25):
        return await message.answer("❌ Iltimos, 1-25 orasida son kiriting yoki tugmalardan birini tanlang:")
    await state.update_data(pages=int(text))
    await state.set_state(OrderStates.choosing_filetype)
    await message.answer(
        f"✅ Sahifalar: <b>{text}</b>\n\n"
        f"📁 Fayl turini tanlang:",
        reply_markup=kb_filetype(),
        parse_mode="HTML"
    )

@dp.message(OrderStates.choosing_filetype)
async def order_filetype(message: types.Message, state: FSMContext):
    filetype = message.text.strip()
    if filetype not in FILETYPE_LABELS:
        return await message.answer("❌ Iltimos, quyidagi tugmalardan birini tanlang:")
    await state.update_data(filetype=filetype)
    await state.set_state(OrderStates.choosing_deadline)
    await message.answer(
        f"✅ Fayl turi: <b>{filetype}</b>\n\n"
        f"⏰ Qachon tayyor bo'lishi kerak?",
        reply_markup=kb_deadline(),
        parse_mode="HTML"
    )

@dp.message(OrderStates.choosing_deadline)
async def order_deadline(message: types.Message, state: FSMContext):
    deadline = message.text.strip()
    if deadline not in DEADLINE_OPTIONS:
        return await message.answer("❌ Iltimos, quyidagi tugmalardan birini tanlang:")
    await state.update_data(deadline=deadline)
    await state.set_state(OrderStates.confirming)

    data          = await state.get_data()
    type_name     = ORDER_TYPES.get(data["order_type"], data["order_type"])
    deadline_days = int(deadline.split()[0])
    deadline_date = datetime.now() + timedelta(days=deadline_days)

    summary = (
        f"📋 BUYURTMA MA'LUMOTLARI\n"
        f"{'─' * 25}\n"
        f"📌 Tur:       {type_name}\n"
        f"📚 Fan:       {data['subject']}\n"
        f"📝 Mavzu:     {data['topic']}\n"
        f"📄 Sahifa:    {data['pages']}\n"
        f"📁 Fayl turi: {data['filetype']}\n"
        f"⏰ Muddat:    {deadline_date.strftime('%d.%m.%Y')} ({deadline})\n"
        f"{'─' * 25}\n\n"
        f"✅ Tasdiqlaysizmi?"
    )
    await message.answer(summary, reply_markup=kb_confirm())

@dp.message(OrderStates.confirming, F.text == "✅ Tasdiqlash")
async def order_confirm(message: types.Message, state: FSMContext):
    uid  = message.from_user.id
    data = await state.get_data()

    deadline_str  = data["deadline"]
    deadline_date = deadline_str_to_date(deadline_str)
    filetype      = data.get("filetype", "📄 PDF")

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    """INSERT INTO orders
                       (user_id, type, subject, topic, pages, filetype, deadline, status, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s)""",
                    (uid, data["order_type"], data["subject"], data["topic"],
                     data["pages"], filetype, deadline_date, datetime.now())
                )
                order_id = c.lastrowid
        finally:
            db.close()
    except Exception as e:
        print(f"[ORDER INSERT ERROR] {e}")
        await message.answer("❌ Buyurtmani saqlashda xato. Qaytadan urinib ko'ring.")
        return

    await state.clear()

    type_name = ORDER_TYPES.get(data["order_type"], data["order_type"])
    await message.answer(
        f"✅ Buyurtma qabul qilindi!\n"
        f"🆔 Buyurtma raqami: #{order_id}\n"
        f"📁 Fayl turi: {filetype}\n"
        f"⏰ Muddat: {deadline_date}\n"
        f"⏳ Admin ko'rib chiqadi va tez orada javob beradi.",
        reply_markup=get_menu(uid)
    )

    username  = message.from_user.username or "—"
    admin_txt = (
        f"🆕 <b>YANGI BUYURTMA #{order_id}</b>\n"
        f"{'─' * 25}\n"
        f"👤 @{username} (ID: <code>{uid}</code>)\n"
        f"📌 Tur:       {type_name}\n"
        f"📚 Fan:       {data['subject']}\n"
        f"📝 Mavzu:     {data['topic']}\n"
        f"📄 Sahifa:    {data['pages']}\n"
        f"📁 Fayl turi: {filetype}\n"
        f"⏰ Muddat:    {deadline_date} ({deadline_str})\n"
        f"📅 Vaqt:      {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"oAccept:{order_id}:{uid}"),
            InlineKeyboardButton(text="❌ Rad etish",    callback_data=f"oReject:{order_id}:{uid}")
        ]
    ])

    admin_id = next(iter(ADMIN_IDS))
    try:
        await bot.send_message(admin_id, admin_txt, reply_markup=admin_kb, parse_mode="HTML")
    except Exception as e:
        print(f"[ADMIN ORDER NOTIFY ERROR] {e}")

# ================= ADMIN ORDER CALLBACKS =================
@dp.callback_query(F.data.startswith("oAccept:"))
async def order_accept(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
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
        await bot.send_message(
            uid,
            f"✅ Buyurtmangiz #{order_id} qabul qilindi!\n"
            f"⏳ Ish boshlanmoqda. Tayyor bo'lganda sizga yuboriladi."
        )
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(
            f"✅ #{order_id} qabul qilindi.\n\n"
            f"📎 Fayl: <code>/deliver {order_id}</code>\n"
            f"✏️ Matn: <code>/delivertext {order_id}</code>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer("✅ Qabul qilindi")

@dp.callback_query(F.data.startswith("oReject:"))
async def order_reject_cb(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
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
        await bot.send_message(
            uid,
            f"❌ Buyurtmangiz #{order_id} rad etildi.\n"
            f"Iltimos, mavzuni o'zgartiring yoki admin bilan bog'laning."
        )
    except Exception as e:
        print(f"[SEND ERROR uid={uid}] {e}")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"❌ #{order_id} rad etildi.")
    except Exception:
        pass

    await callback.answer("❌ Rad etildi")

# ================= DELIVER — FAYL =================
@dp.message(Command("deliver"))
async def deliver_file_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("❌ Ishlatish: /deliver {order_id}")

    order_id = int(args[1])
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT id, user_id, type, subject, topic, status FROM orders WHERE id=%s",
                    (order_id,)
                )
                order = c.fetchone()
        finally:
            db.close()
    except Exception as e:
        print(f"[DELIVER CMD ERROR] {e}")
        return await message.answer("❌ DB xato")

    if not order:
        return await message.answer(f"❌ #{order_id} buyurtma topilmadi")
    if order["status"] == "done":
        return await message.answer(f"⚠️ #{order_id} allaqachon bajarilgan")

    type_name = ORDER_TYPES.get(order["type"], order["type"])
    await state.set_state(DeliverStates.waiting_file)
    await state.update_data(order_id=order_id, target_uid=order["user_id"])

    await message.answer(
        f"📤 #{order_id} uchun fayl yuboring:\n"
        f"👤 User ID: {order['user_id']}\n"
        f"📌 {type_name} | {order['subject']} — {order['topic']}\n\n"
        f"Fayl (PDF, DOCX, XLSX...) yuboring:",
        reply_markup=kb_cancel()
    )

@dp.message(DeliverStates.waiting_file, F.document)
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
    except Exception as e:
        print(f"[DELIVER FILE SEND ERROR] {e}")
        await message.answer("❌ DB xato")
        await state.clear()
        return

    type_name = ORDER_TYPES.get(order["type"], order["type"])
    caption   = (
        f"✅ Buyurtmangiz tayyor!\n"
        f"🆔 #{order_id} | {type_name}\n"
        f"📚 {order['subject']} — {order['topic']}"
    )

    try:
        await bot.send_document(target_uid, message.document.file_id, caption=caption)
        await message.answer(
            f"✅ Fayl user {target_uid} ga yuborildi (#{order_id})",
            reply_markup=get_menu(message.from_user.id)
        )
    except Exception as e:
        await message.answer(f"❌ Yuborishda xato: {e}")

    await state.clear()

# ================= DELIVER — MATN =================
@dp.message(Command("delivertext"))
async def deliver_text_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("❌ Ishlatish: /delivertext {order_id}")

    order_id = int(args[1])
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT id, user_id, type, subject, topic, status FROM orders WHERE id=%s",
                    (order_id,)
                )
                order = c.fetchone()
        finally:
            db.close()
    except Exception as e:
        print(f"[DELIVERTEXT CMD ERROR] {e}")
        return await message.answer("❌ DB xato")

    if not order:
        return await message.answer(f"❌ #{order_id} buyurtma topilmadi")
    if order["status"] == "done":
        return await message.answer(f"⚠️ #{order_id} allaqachon bajarilgan")

    type_name = ORDER_TYPES.get(order["type"], order["type"])
    await state.set_state(DeliverStates.waiting_text)
    await state.update_data(order_id=order_id, target_uid=order["user_id"])

    await message.answer(
        f"✏️ #{order_id} uchun matn yuboring:\n"
        f"👤 User ID: {order['user_id']}\n"
        f"📌 {type_name} | {order['subject']} — {order['topic']}\n\n"
        f"Matnni yozing:",
        reply_markup=kb_cancel()
    )

@dp.message(DeliverStates.waiting_text, F.text)
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
    except Exception as e:
        print(f"[DELIVER TEXT SEND ERROR] {e}")
        await message.answer("❌ DB xato")
        await state.clear()
        return

    type_name = ORDER_TYPES.get(order["type"], order["type"])
    header    = (
        f"✅ Buyurtmangiz tayyor!\n"
        f"🆔 #{order_id} | {type_name}\n"
        f"📚 {order['subject']} — {order['topic']}\n"
        f"{'─' * 25}\n\n"
    )

    try:
        await bot.send_message(target_uid, header + message.text)
        await message.answer(
            f"✅ Matn user {target_uid} ga yuborildi (#{order_id})",
            reply_markup=get_menu(message.from_user.id)
        )
    except Exception as e:
        await message.answer(f"❌ Yuborishda xato: {e}")

    await state.clear()

# ================= MY ORDERS =================
@dp.message(F.text == "📋 Buyurtmalarim")
async def my_orders(message: types.Message):
    uid = message.from_user.id

    if not has_access(uid):
        return await message.answer("❌ Bu funksiya premium foydalanuvchilar uchun.")

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    """SELECT id, type, subject, topic, pages, deadline, status, created_at
                       FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 10""",
                    (uid,)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[MY ORDERS ERROR] {e}")
        return await message.answer("❌ Xato yuz berdi.")

    if not rows:
        return await message.answer("📋 Hali buyurtmalar yo'q.")

    used      = get_order_monthly_count(uid)
    remaining = max(0, ORDER_LIMIT_PER_MONTH - used)

    status_icons = {
        "pending":     "⏳ Kutilmoqda",
        "in_progress": "🔄 Jarayonda",
        "done":        "✅ Bajarildi",
        "rejected":    "❌ Rad etildi"
    }

    txt = (
        f"📋 BUYURTMALARIM\n"
        f"📊 Bu oy: {used}/{ORDER_LIMIT_PER_MONTH} (qoldi: {remaining})\n"
        f"{'─' * 25}\n\n"
    )

    for r in rows:
        type_name    = ORDER_TYPES.get(r["type"], r["type"])
        status_txt   = status_icons.get(r["status"], r["status"])
        date_str     = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        deadline_txt = format_deadline(r["deadline"])

        txt += (
            f"🆔 #{r['id']} | {type_name}\n"
            f"📚 {r['subject']} — {r['topic']}\n"
            f"📄 {r['pages']} sahifa | ⏰ {deadline_txt}\n"
            f"📅 {date_str} | {status_txt}\n"
            f"{'─' * 25}\n"
        )

    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."

    await message.answer(txt)

# ================= BROADCAST =================
@dp.message(Command("broadcast"))
@dp.callback_query(F.data == "adm:broadcast")
async def broadcast_cmd(event: types.Message | types.CallbackQuery, state: FSMContext):
    uid = event.from_user.id
    if uid not in ADMIN_IDS:
        return

    await state.set_state(BroadcastStates.waiting_message)

    text = (
        "📢 <b>BROADCAST</b>\n\n"
        "Xabar yuboring — har qanday turdagi:\n"
        "• Matn\n"
        "• Rasm (caption bilan yoki siz)\n"
        "• Fayl / hujjat\n"
        "• Video\n"
        "• Forward qilingan xabar\n\n"
        "<i>❌ Bekor qilish — buyrug'ini yozish uchun</i>"
    )

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb_cancel(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb_cancel(), parse_mode="HTML")

@dp.message(BroadcastStates.waiting_message)
async def broadcast_preview(message: types.Message, state: FSMContext):
    if message.forward_from or message.forward_from_chat:
        msg_type = "forward"
    elif message.photo:
        msg_type = "photo"
    elif message.video:
        msg_type = "video"
    elif message.document:
        msg_type = "document"
    elif message.audio:
        msg_type = "audio"
    elif message.voice:
        msg_type = "voice"
    elif message.sticker:
        msg_type = "sticker"
    elif message.text:
        msg_type = "text"
    else:
        return await message.answer("❌ Bu turdagi xabar qo'llab-quvvatlanmaydi.")

    await state.update_data(
        msg_type=msg_type,
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )

    user_count = len(get_all_user_ids())
    await state.set_state(BroadcastStates.confirming)

    await message.answer(
        f"📢 <b>BROADCAST PREVIEW</b>\n\n"
        f"👥 Yuboriladi: <b>{user_count} ta</b> foydalanuvchiga\n"
        f"📨 Xabar turi: <b>{msg_type}</b>\n\n"
        f"Yuborishni tasdiqlaysizmi?",
        reply_markup=kb_broadcast_confirm(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "bc:send")
async def broadcast_send(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)

    data     = await state.get_data()
    user_ids = get_all_user_ids()

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("⏳ Yuborilmoqda...")

    status_msg = await callback.message.reply(
        f"⏳ Yuborilmoqda... 0/{len(user_ids)}"
    )

    success = 0
    failed  = 0

    for i, uid in enumerate(user_ids, 1):
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=data["from_chat_id"],
                message_id=data["message_id"]
            )
            success += 1
        except Exception:
            failed += 1

        if i % 20 == 0:
            try:
                await status_msg.edit_text(
                    f"⏳ Yuborilmoqda... {i}/{len(user_ids)}\n"
                    f"✅ {success} | ❌ {failed}"
                )
            except Exception:
                pass

        await asyncio.sleep(0.05)

    try:
        await status_msg.edit_text(
            f"✅ <b>Broadcast yakunlandi!</b>\n\n"
            f"👥 Jami: {len(user_ids)}\n"
            f"✅ Yuborildi: {success}\n"
            f"❌ Xato (bloklagan): {failed}",
            parse_mode="HTML"
        )
    except Exception:
        pass

@dp.callback_query(F.data == "bc:cancel")
async def broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("❌ Bekor qilindi")
    await callback.message.reply("❌ Broadcast bekor qilindi.")

# ================= REVOKE PREMIUM =================
@dp.message(Command("revoke"))
@dp.callback_query(F.data == "adm:revoke")
async def revoke_cmd(event: types.Message | types.CallbackQuery, state: FSMContext):
    uid = event.from_user.id
    if uid not in ADMIN_IDS:
        return

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT user_id, username, access_until FROM users "
                    "WHERE access_until > %s ORDER BY access_until DESC",
                    (datetime.now(),)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[REVOKE CMD ERROR] {e}")
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
        buttons.append([
            InlineKeyboardButton(
                text=f"🚫 @{uname} | {access_until}",
                callback_data=f"revokeUser:{r['user_id']}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="❌ Yopish", callback_data="revokeClose")
    ])

    kb   = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = (
        f"🚫 <b>PREMIUM BEKOR QILISH</b>\n\n"
        f"Premiumini bekor qilmoqchi bo'lgan userni tanlang:\n"
        f"(Jami: {len(rows)} ta premium user)"
    )

    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("revokeUser:"))
async def revoke_user(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)

    try:
        uid = int(callback.data.split(":")[1])
    except Exception:
        return await callback.answer("❌ Noto'g'ri format", show_alert=True)

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT username, access_until FROM users WHERE user_id=%s",
                    (uid,)
                )
                user = c.fetchone()

            if not user:
                return await callback.answer("❌ User topilmadi", show_alert=True)

            with db.cursor() as c:
                c.execute(
                    "UPDATE users SET access_until=NULL, warned=0 WHERE user_id=%s",
                    (uid,)
                )
        finally:
            db.close()
    except Exception as e:
        print(f"[REVOKE USER ERROR] {e}")
        return await callback.answer("❌ DB xato", show_alert=True)

    try:
        await bot.send_message(
            uid,
            "⚠️ Sizning premium obunangiz admin tomonidan bekor qilindi.\n"
            "Batafsil ma'lumot uchun admin bilan bog'laning.",
            reply_markup=menu_basic
        )
    except Exception as e:
        print(f"[REVOKE NOTIFY ERROR uid={uid}] {e}")

    uname = user["username"] or "—"
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(
            f"✅ @{uname} (ID: {uid}) premiumdan chiqarildi."
        )
    except Exception:
        pass

    await callback.answer(f"✅ @{uname} premiumdan chiqarildi")

@dp.callback_query(F.data == "revokeClose")
async def revoke_close(callback: types.CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Yopildi")

# ================= ADMIN PANEL =================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    stats = get_admin_stats()
    await message.answer(
        build_admin_text(stats),
        reply_markup=admin_panel_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "adm:refresh")
async def adm_refresh(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)

    stats = get_admin_stats()
    try:
        await callback.message.edit_text(
            build_admin_text(stats),
            reply_markup=admin_panel_kb(),
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("🔄 Yangilandi")

@dp.callback_query(F.data == "adm:users")
async def adm_users(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT user_id, username, access_until FROM users "
                    "WHERE access_until > %s ORDER BY access_until DESC",
                    (datetime.now(),)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[ADM USERS ERROR] {e}")
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

@dp.callback_query(F.data == "adm:payments")
async def adm_payments(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT id, user_id, tariff_days, status, created_at "
                    "FROM payments ORDER BY id DESC LIMIT 10"
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[ADM PAYMENTS ERROR] {e}")
        rows = []

    await callback.answer()

    if not rows:
        return await callback.message.answer("❌ To'lovlar yo'q")

    txt = "💳 <b>OXIRGI TO'LOVLAR:</b>\n\n"
    for r in rows:
        icon     = "✅" if r["status"] == "approved" else ("❌" if r["status"] == "rejected" else "⏳")
        date_str = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        txt += (
            f"{icon} #{r['id']} | "
            f"<code>{r['user_id']}</code> | "
            f"{r['tariff_days'] or '?'} kun | "
            f"{date_str}\n"
        )

    await callback.message.answer(txt, parse_mode="HTML")

@dp.callback_query(F.data == "adm:expiring")
async def adm_expiring(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)

    now  = datetime.now()
    soon = now + timedelta(days=3)

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT user_id, username, access_until FROM users "
                    "WHERE access_until BETWEEN %s AND %s",
                    (now, soon)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[ADM EXPIRING ERROR] {e}")
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

@dp.callback_query(F.data == "adm:orders")
async def adm_orders(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)

    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    """SELECT o.id, o.user_id, u.username, o.type,
                              o.subject, o.topic, o.pages, o.deadline,
                              o.status, o.created_at
                       FROM orders o
                       LEFT JOIN users u ON o.user_id = u.user_id
                       WHERE o.status IN ('pending','in_progress')
                       ORDER BY o.id DESC"""
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[ADM ORDERS ERROR] {e}")
        rows = []

    await callback.answer()

    if not rows:
        return await callback.message.answer("✅ Aktiv buyurtmalar yo'q.")

    status_icons = {
        "pending":     "⏳",
        "in_progress": "🔄",
    }

    txt = f"📋 <b>AKTIV BUYURTMALAR ({len(rows)} ta)</b>\n{'─' * 25}\n\n"
    for r in rows:
        username     = r["username"] or "—"
        type_name    = ORDER_TYPES.get(r["type"], r["type"])
        icon         = status_icons.get(r["status"], "")
        date_str     = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        deadline_txt = format_deadline(r["deadline"])

        txt += (
            f"{icon} #{r['id']} | {type_name}\n"
            f"👤 @{username} (<code>{r['user_id']}</code>)\n"
            f"📚 {r['subject']} — {r['topic']}\n"
            f"📄 {r['pages']} s. | ⏰ {deadline_txt} | 📅 {date_str}\n"
            f"/deliver {r['id']} | /delivertext {r['id']}\n"
            f"{'─' * 25}\n"
        )

    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."

    await callback.message.answer(txt, parse_mode="HTML")

# ================= SLASH COMMANDS =================
@dp.message(Command("users"))
async def users_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT user_id, username, access_until FROM users "
                    "WHERE access_until > %s ORDER BY access_until DESC",
                    (datetime.now(),)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[USERS CMD ERROR] {e}")
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

@dp.message(Command("payments"))
async def payments_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT id, user_id, tariff_days, status, created_at "
                    "FROM payments ORDER BY id DESC LIMIT 10"
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[PAYMENTS CMD ERROR] {e}")
        return await message.answer("❌ DB xato")

    if not rows:
        return await message.answer("❌ To'lovlar yo'q")

    txt = "💳 <b>OXIRGI TO'LOVLAR:</b>\n\n"
    for r in rows:
        icon     = "✅" if r["status"] == "approved" else ("❌" if r["status"] == "rejected" else "⏳")
        date_str = r["created_at"].strftime('%d.%m.%Y') if r["created_at"] else "—"
        txt += f"{icon} #{r['id']} | <code>{r['user_id']}</code> | {r['tariff_days'] or '?'} kun | {date_str}\n"

    await message.answer(txt, parse_mode="HTML")

@dp.message(Command("expiring"))
async def expiring_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    now  = datetime.now()
    soon = now + timedelta(days=3)
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT user_id, username, access_until FROM users "
                    "WHERE access_until BETWEEN %s AND %s",
                    (now, soon)
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[EXPIRING CMD ERROR] {e}")
        return await message.answer("❌ DB xato")

    if not rows:
        return await message.answer("✅ Tugayotgan obunalar yo'q")

    txt = "⏰ <b>TUGAYOTGAN OBUNALAR (3 kun):</b>\n\n"
    for r in rows:
        username     = r["username"] or "—"
        access_until = r["access_until"].strftime('%d.%m.%Y %H:%M') if r["access_until"] else "—"
        txt += f"@{username} (<code>{r['user_id']}</code>) | {access_until}\n"
    await message.answer(txt, parse_mode="HTML")

@dp.message(Command("orders"))
async def orders_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    """SELECT o.id, o.user_id, u.username, o.type,
                              o.subject, o.topic, o.pages, o.deadline,
                              o.status, o.created_at
                       FROM orders o
                       LEFT JOIN users u ON o.user_id = u.user_id
                       WHERE o.status IN ('pending','in_progress')
                       ORDER BY o.id DESC"""
                )
                rows = c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[ORDERS CMD ERROR] {e}")
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
            f"🆔 #{r['id']} | {type_name}\n"
            f"👤 @{username} (<code>{r['user_id']}</code>)\n"
            f"📚 {r['subject']} — {r['topic']}\n"
            f"📄 {r['pages']} s. | ⏰ {deadline_txt} | 📅 {date_str}\n"
            f"/deliver {r['id']} | /delivertext {r['id']}\n"
            f"{'─'*25}\n"
        )
    if len(txt) > 4000:
        txt = txt[:4000] + "\n..."
    await message.answer(txt, parse_mode="HTML")

# ================= WATCHER =================
async def access_watcher():
    while True:
        try:
            db = get_db()
            try:
                with db.cursor() as c:
                    c.execute(
                        "SELECT user_id, access_until FROM users "
                        "WHERE warned=0 AND access_until IS NOT NULL AND access_until > NOW()"
                    )
                    rows = c.fetchall()
            finally:
                db.close()

            for r in rows:
                delta = r["access_until"] - datetime.now()
                if timedelta(days=0) < delta <= timedelta(days=3):
                    try:
                        await bot.send_message(
                            r["user_id"],
                            "⏰ Diqqat! Obunangiz tugashiga 3 kun qoldi.\n"
                            "Uzluksiz foydalanish uchun to'lovni yangilang."
                        )
                        db2 = get_db()
                        try:
                            with db2.cursor() as c2:
                                c2.execute(
                                    "UPDATE users SET warned=1 WHERE user_id=%s",
                                    (r["user_id"],)
                                )
                        finally:
                            db2.close()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Watcher ERROR] {e}")

        await asyncio.sleep(3600)

# ================= STARTUP =================
async def on_startup():
    asyncio.create_task(access_watcher())
    print("✅ Bot ishga tushdi")

# ================= RUN =================
async def main():
    print("🚀 Starting bot...")
    dp.startup.register(on_startup)
    while True:
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                close_bot_session=False
            )
        except Exception as e:
            print(f"[POLLING ERROR] {e} — restarting in 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())