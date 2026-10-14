from aiogram.fsm.state import State, StatesGroup


class PromoState(StatesGroup):
    waiting_for_code = State()


class AdminGrantState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_prompt = State()


class AdminPromoState(StatesGroup):
    waiting_for_code = State()
    waiting_for_type = State()
    waiting_for_value = State()
    waiting_for_max_uses = State()


class AdminEditPriceState(StatesGroup):
    waiting_for_new_price = State()


class AdminBroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirm = State()
