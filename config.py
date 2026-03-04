import os
from dotenv import load_dotenv
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")  # Set this in .env!

OWNER_ID = 6875167708
ADMIN_IDS = {OWNER_ID}

PAYNET_LINK = "https://app.paynet.uz/?m=49156&i=1abfad1a-2da7-4d8d-8509-39f59b32d538"

TARIFFS = {
    30:  "1 oy – 30 000 so'm",
    90:  "3 oy – 80 000 so'm",
    180: "6 oy – 150 000 so'm"
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

ALL_PERMS = ["payments", "orders", "broadcast", "revoke", "users", "listusers"]

PERM_LABELS = {
    "payments":  "💳 To'lovlar",
    "orders":    "📋 Buyurtmalar",
    "broadcast": "📢 Broadcast",
    "revoke":    "🚫 Premium bekor",
    "users":     "👥 Userlar",
    "listusers": "📊 Excel ro'yxat",
}

# ── Referral config ──────────────────────────────────────────────
REFERRAL_REQUIRED   = 10   # Number of referrals needed for free premium
REFERRAL_REWARD_DAYS = 30  # Days of premium awarded on reaching the goal

BOT_INFO_TEXT = """ℹ️ <b>BOT HAQIDA MA'LUMOT</b>

Ushbu bot quyidagi imkoniyatlarni taqdim etadi:

━━━━━━━━━━━━━━━━━━━━━

📄 <b>PDF YARATISH</b> (bepul)
  • <b>Skan PDF</b> — Rasmlaringizni CamScanner uslubida qayta ishlaydi: oq fon, qora yozuv, professional ko'rinish
  • <b>Oddiy PDF</b> — Rasmlarni shunchaki PDF ga birlashtiradi, o'zgartirmasdan

━━━━━━━━━━━━━━━━━━━━━

💳 <b>PREMIUM OBUNA</b>
  • 1 oy — 30 000 so'm
  • 3 oy — 80 000 so'm
  • 6 oy — 150 000 so'm

━━━━━━━━━━━━━━━━━━━━━

📝 <b>REFERAT YOZDIRISH</b> (premium)
  Kerakli fandan, mavzuda, belgilangan sahifada professional referat tayyorlanadi

📘 <b>MUSTAQIL ISH YOZDIRISH</b> (premium)
  Mustaqil ish topshiriqlari tayyor holda yetkazib beriladi

━━━━━━━━━━━━━━━━━━━━━

📋 <b>BUYURTMALARIM</b>
  Barcha buyurtmalaringiz holati va tarixi

━━━━━━━━━━━━━━━━━━━━━

👥 <b>DO'ST TAKLIF QILISH</b>
  {req} ta do'stingizni taklif qiling va <b>{days} kunlik premium</b> yutib oling!
  Har bir yangi foydalanuvchi hisobga olinadi.

━━━━━━━━━━━━━━━━━━━━━

⏰ Buyurtma muddati: 1–10 kun
📁 Fayl formatlari: PDF, Word, Excel, PowerPoint
📊 Oylik limit: 10 ta buyurtma

━━━━━━━━━━━━━━━━━━━━━

Savollar uchun admin bilan bog'laning.""".format(req=REFERRAL_REQUIRED, days=REFERRAL_REWARD_DAYS)

menu_basic = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 PDF yaratish")],
        [KeyboardButton(text="💳 To'lov qilish"), KeyboardButton(text="✅ To'lov qildim")],
        [KeyboardButton(text="ℹ️ Ma'lumot"),       KeyboardButton(text="🆘 Yordam")],
        [KeyboardButton(text="👥 Do'st taklif qilish")]
    ],
    resize_keyboard=True
)

menu_premium = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 PDF yaratish")],
        [KeyboardButton(text="📝 Referat yozdirish")],
        [KeyboardButton(text="📘 Mustaqil ish yozdirish")],
        [KeyboardButton(text="📋 Buyurtmalarim")],
        [KeyboardButton(text="ℹ️ Ma'lumot"),       KeyboardButton(text="🆘 Yordam")],
        [KeyboardButton(text="👥 Do'st taklif qilish")]
    ],
    resize_keyboard=True
)
