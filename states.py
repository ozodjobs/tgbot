from aiogram.fsm.state import State, StatesGroup


class PDFStates(StatesGroup):
    choosing_type     = State()
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

class SubAdminStates(StatesGroup):
    waiting_user_id = State()
    choosing_perms  = State()

class SupportStates(StatesGroup):
    waiting_message = State()

class SupportReplyStates(StatesGroup):
    waiting_reply = State()
