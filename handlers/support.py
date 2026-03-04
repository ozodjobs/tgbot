from datetime import datetime

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID
from states import SupportStates, SupportReplyStates
from keyboards.keyboards import kb_cancel
from utils.helpers import get_menu

router = Router()


@router.message(F.text == "🆘 Yordam")
async def support_start(message: types.Message, state: FSMContext):
    await state.set_state(SupportStates.waiting_message)
    await message.answer("✍️ Xabaringizni yozing:", reply_markup=kb_cancel())

@router.message(SupportStates.waiting_message, F.text)
async def support_receive(message: types.Message, state: FSMContext):
    uid      = message.from_user.id
    username = message.from_user.username or "—"
    text     = message.text.strip()
    await state.clear()
    admin_txt = (
        f"💬 <b>YORDAM SO'ROVI</b>\n"
        f"👤 @{username} (ID: <code>{uid}</code>)\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"{'─'*25}\n\n{text}"
    )
    reply_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Javob berish", callback_data=f"supReply:{uid}")
    ]])
    try:
        await message.bot.send_message(OWNER_ID, admin_txt, reply_markup=reply_kb, parse_mode="HTML")
    except Exception as e:
        print(f"[SUPPORT FORWARD ERROR] {e}")
    await message.answer("✅ Xabaringiz adminga yuborildi!", reply_markup=get_menu(uid))

@router.callback_query(F.data.startswith("supReply:"))
async def support_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("❌ Ruxsat yo'q", show_alert=True)
    target_uid = int(callback.data.split(":")[1])
    await state.set_state(SupportReplyStates.waiting_reply)
    await state.update_data(support_target_uid=target_uid)
    await callback.answer()
    await callback.message.reply(
        f"✏️ <code>{target_uid}</code> foydalanuvchiga javobingizni yozing:",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )

@router.message(SupportReplyStates.waiting_reply, F.text)
async def support_reply_send(message: types.Message, state: FSMContext):
    data       = await state.get_data()
    target_uid = data.get("support_target_uid")
    await state.clear()
    try:
        await message.bot.send_message(target_uid, f"<b>Admin:</b>\n\n{message.text}", parse_mode="HTML")
        await message.answer("✅ Javob yuborildi.", reply_markup=get_menu(message.from_user.id))
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
