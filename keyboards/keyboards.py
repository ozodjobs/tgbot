import json

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import ALL_PERMS, PERM_LABELS, DEADLINE_OPTIONS, OWNER_ID
from db.database import has_perm


def menu_pdf_collecting(count: int, pdf_mode: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 PDF yaratish")],
            [KeyboardButton(text="🗑 Tozalash")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )

# ================= ADMIN PANEL KEYBOARDS =================

def admin_panel_kb(uid: int) -> InlineKeyboardMarkup:
    rows = []
    row = []
    if has_perm(uid, "users"):
        row.append(InlineKeyboardButton(text="👥 Userlar", callback_data="adm:users"))
    if has_perm(uid, "payments"):
        row.append(InlineKeyboardButton(text="💳 To'lovlar", callback_data="adm:payments"))
    if row:
        rows.append(row)

    row2 = []
    if has_perm(uid, "orders"):
        row2.append(InlineKeyboardButton(text="⏰ Tugayotganlar", callback_data="adm:expiring"))
        row2.append(InlineKeyboardButton(text="📋 Buyurtmalar",   callback_data="adm:orders"))
    if row2:
        rows.append(row2)

    row3 = []
    if has_perm(uid, "broadcast"):
        row3.append(InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:broadcast"))
    if has_perm(uid, "revoke"):
        row3.append(InlineKeyboardButton(text="🚫 Premium bekor", callback_data="adm:revoke"))
    if row3:
        rows.append(row3)

    if has_perm(uid, "payments"):
        rows.append([InlineKeyboardButton(text="⏳ Kutilayotgan to'lovlar", callback_data="adm:pending_payments")])

    if has_perm(uid, "listusers"):
        rows.append([InlineKeyboardButton(text="📊 Userlar ro'yxati (Excel)", callback_data="adm:listusers")])

    if uid == OWNER_ID:
        rows.append([InlineKeyboardButton(text="🛡 Sub-adminlar", callback_data="adm:subadmins")])

    rows.append([InlineKeyboardButton(text="🔄 Yangilash", callback_data="adm:refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def perm_toggle_kb(target_uid: int, current_perms: list) -> InlineKeyboardMarkup:
    rows = []
    for perm in ALL_PERMS:
        check = "✅" if perm in current_perms else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {PERM_LABELS[perm]}",
            callback_data=f"permToggle:{target_uid}:{perm}"
        )])
    rows.append([
        InlineKeyboardButton(text="💾 Saqlash",       callback_data=f"permSave:{target_uid}"),
        InlineKeyboardButton(text="❌ Bekor qilish",  callback_data="permCancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def subadmins_list_kb(admins: list) -> InlineKeyboardMarkup:
    rows = []
    for a in admins:
        uname = f"@{a['username']}" if a.get("username") else f"ID:{a['user_id']}"
        try:
            cnt = len(json.loads(a["perms"]))
        except Exception:
            cnt = 0
        rows.append([InlineKeyboardButton(
            text=f"🛡 {uname} ({cnt} ruxsat)",
            callback_data=f"subadmView:{a['user_id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Yangi sub-admin qo'shish", callback_data="subadmAdd")])
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm:refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def subadmin_detail_kb(target_uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Ruxsatlarni o'zgartirish", callback_data=f"subadmEdit:{target_uid}"),
            InlineKeyboardButton(text="🗑 O'chirish",                 callback_data=f"subadmDel:{target_uid}"),
        ],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm:subadmins")],
    ])

# ================= OTHER KEYBOARDS =================

def kb_pdf_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔬 Skan PDF", callback_data="pdftype:scan"),
            InlineKeyboardButton(text="📄 Oddiy PDF", callback_data="pdftype:simple"),
        ]
    ])

def kb_pages():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="5"),  KeyboardButton(text="10"), KeyboardButton(text="15")],
            [KeyboardButton(text="20"), KeyboardButton(text="25")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ], resize_keyboard=True
    )

def kb_filetype():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 PDF"),           KeyboardButton(text="📝 Word (.docx)")],
            [KeyboardButton(text="📊 Excel (.xlsx)"), KeyboardButton(text="📊 PowerPoint (.pptx)")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ], resize_keyboard=True
    )

def kb_deadline():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=d) for d in DEADLINE_OPTIONS[:3]],
            [KeyboardButton(text=d) for d in DEADLINE_OPTIONS[3:]],
            [KeyboardButton(text="❌ Bekor qilish")]
        ], resize_keyboard=True
    )

def kb_confirm():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Tasdiqlash")], [KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def kb_cancel():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def kb_broadcast_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yuborish",     callback_data="bc:send"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="bc:cancel"),
    ]])
