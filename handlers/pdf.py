import uuid

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from PIL import Image

from states import PDFStates
from keyboards.keyboards import kb_pdf_type, menu_pdf_collecting, kb_cancel
from utils.helpers import sanitize_filename, cleanup_files, get_menu
from utils.image import process_scan_image, build_pdf_with_reportlab
from aiogram.types import FSInputFile

router = Router()


# ================================================================
# ═════════════════  PDF FLOW  ═══════════════════════════════════
# ================================================================

@router.message(F.text == "📄 PDF yaratish")
async def pdf_start(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == PDFStates.collecting_images.state:
        data = await state.get_data()
        images   = data.get("images", [])
        pdf_mode = data.get("pdf_mode", "simple")
        if images:
            return await message.answer(
                f"📸 {len(images)} ta rasm bor.\nYana rasm yuboring yoki '📥 PDF yaratish' ni bosing.",
                reply_markup=menu_pdf_collecting(len(images), pdf_mode)
            )
    await message.answer(
        "📄 <b>PDF YARATISH</b>\n\nQaysi turdagi PDF kerak?\n\n"
        "🔬 <b>Skan PDF</b> — CamScanner uslubida: oq fon, qora matn, barcha soya va dog'lar yo'q\n"
        "📄 <b>Oddiy PDF</b> — Rasmlar o'zgarishsiz PDF ga birlashtiriladi",
        reply_markup=kb_pdf_type(), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("pdftype:"))
async def pdf_type_chosen(callback: types.CallbackQuery, state: FSMContext):
    pdf_mode = callback.data.split(":")[1]
    await state.set_state(PDFStates.collecting_images)
    await state.update_data(images=[], pdf_mode=pdf_mode)
    mode_label = "🔬 Skan PDF" if pdf_mode == "scan" else "📄 Oddiy PDF"
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Rejim: <b>{mode_label}</b>\n\n📸 Rasmlarni yuboring.\nHammasi tayyor bo'lgach '📥 PDF yaratish' tugmasini bosing.",
        reply_markup=menu_pdf_collecting(0, pdf_mode), parse_mode="HTML"
    )


@router.message(PDFStates.collecting_images, F.photo)
async def pdf_add_image(message: types.Message, state: FSMContext):
    uid  = message.from_user.id
    file = await message.bot.get_file(message.photo[-1].file_id)
    path = f"/tmp/img_{uid}_{uuid.uuid4().hex}.jpg"
    await message.bot.download_file(file.file_path, path)
    data   = await state.get_data()
    images = data.get("images", [])
    images.append(path)
    await state.update_data(images=images)
    pdf_mode = data.get("pdf_mode", "simple")
    await message.answer(
        f"✅ Rasm qo'shildi! Jami: {len(images)} ta\nYana rasm yuboring yoki '📥 PDF yaratish' ni bosing.",
        reply_markup=menu_pdf_collecting(len(images), pdf_mode)
    )


@router.message(PDFStates.collecting_images, F.text == "🗑 Tozalash")
async def pdf_clear_images(message: types.Message, state: FSMContext):
    data   = await state.get_data()
    images = data.get("images", [])
    pdf_mode = data.get("pdf_mode", "simple")
    for p in images:
        cleanup_files(p)
    await state.update_data(images=[])
    await message.answer("🗑 Barcha rasmlar o'chirildi.\nQaytadan rasm yuborishingiz mumkin.", reply_markup=menu_pdf_collecting(0, pdf_mode))


@router.message(PDFStates.collecting_images, F.text == "📥 PDF yaratish")
async def pdf_ask_name(message: types.Message, state: FSMContext):
    data   = await state.get_data()
    images = data.get("images", [])
    pdf_mode = data.get("pdf_mode", "simple")
    if not images:
        return await message.answer("❌ Hali rasm yuborilmagan.", reply_markup=menu_pdf_collecting(0, pdf_mode))
    await state.set_state(PDFStates.waiting_pdf_name)
    await message.answer(f"✅ {len(images)} ta rasm tayyor.\n\n📝 PDF uchun nom kiriting:", reply_markup=kb_cancel())


@router.message(PDFStates.waiting_pdf_name, F.text)
async def pdf_create(message: types.Message, state: FSMContext):
    data     = await state.get_data()
    images   = data.get("images", [])
    pdf_mode = data.get("pdf_mode", "simple")
    pdf_path = None
    if not images:
        await state.clear()
        return await message.answer("❌ Rasm topilmadi.", reply_markup=get_menu(message.from_user.id))
    safe_name = sanitize_filename(message.text)
    pdf_path  = f"/tmp/{safe_name}_{uuid.uuid4().hex}.pdf"
    mode_label = "🔬 Skan" if pdf_mode == "scan" else "📄 Oddiy"
    await message.answer(f"⏳ {mode_label} PDF yaratilmoqda...")
    try:
        pil_images = []
        for p in images:
            img = Image.open(p).convert("RGB")
            if pdf_mode == "scan":
                img = process_scan_image(img)
            pil_images.append(img)
        build_pdf_with_reportlab(pil_images, pdf_path)
        for img in pil_images:
            img.close()
        await message.answer_document(
            FSInputFile(pdf_path, filename=f"{safe_name}.pdf"),
            caption=f"✅ {mode_label} PDF tayyor! ({len(images)} ta rasm)"
        )
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    finally:
        cleanup_files(*images, pdf_path)
        await state.clear()
    await message.answer("✅ Bajarildi!", reply_markup=get_menu(message.from_user.id))
