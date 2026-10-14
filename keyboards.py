from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Set
from config import ADMIN_IDS


def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🛒 Каталог промтов", callback_data="nav_catalog")],
        [InlineKeyboardButton(text="👥 Рефералка и баланс", callback_data="nav_referral")],
        [
            InlineKeyboardButton(text="📁 Мои покупки", callback_data="nav_my_purchases"),
            InlineKeyboardButton(text="🎟 Промокод", callback_data="nav_enter_promo"),
        ],
        [InlineKeyboardButton(text="ℹ️ Помощь / FAQ", callback_data="nav_faq")],
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def catalog_kb(prompts: List[Dict[str, Any]], purchased_ids: Set[str]) -> InlineKeyboardMarkup:
    buttons = []
    for p in prompts:
        pid = p["id"]
        title = p["title"]
        price = p["price"]
        if pid in purchased_ids:
            text = f"✅ {title} (Куплен)"
        else:
            text = f"💎 {title} — {price} ⭐️"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"show_prompt:{pid}")])

    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="nav_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prompt_card_kb(
    prompt_id: str,
    is_purchased: bool,
    final_price: int,
    has_active_promo: bool = False,
    user_balance: int = 0
) -> InlineKeyboardMarkup:
    buttons = []
    if is_purchased:
        buttons.append([InlineKeyboardButton(text="📥 Скачать .txt файл", callback_data=f"download_prompt:{prompt_id}")])
        buttons.append([InlineKeyboardButton(text="👀 Показать текст в чате", callback_data=f"view_text_prompt:{prompt_id}")])
    else:
        if user_balance >= final_price and final_price > 0:
            buttons.append([InlineKeyboardButton(text=f"💳 Оплатить с баланса ({final_price} ⭐️)", callback_data=f"buy_balance:{prompt_id}")])

        if final_price <= 0:
            buttons.append([InlineKeyboardButton(text="🎁 Забрать бесплатно (0 ⭐️)", callback_data=f"claim_free:{prompt_id}")])
        else:
            buttons.append([InlineKeyboardButton(text=f"⭐️ Оплатить Stars ({final_price} ⭐️)", callback_data=f"buy_prompt:{prompt_id}")])

        if not has_active_promo:
            buttons.append([InlineKeyboardButton(text="🎟 Применить промокод", callback_data=f"enter_promo_for:{prompt_id}")])

    buttons.append([InlineKeyboardButton(text="🔙 В каталог", callback_data="nav_catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def referral_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список моих рефералов", callback_data="nav_my_referrals")],
            [InlineKeyboardButton(text="🛒 В каталог промтов", callback_data="nav_catalog")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="nav_main_menu")],
        ]
    )


def referrals_list_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню рефералки", callback_data="nav_referral")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav_main_menu")],
        ]
    )


def my_purchases_kb(purchased_prompts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for p in purchased_prompts:
        buttons.append([
            InlineKeyboardButton(text=f"📥 {p['title']}", callback_data=f"download_prompt:{p['id']}")
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="nav_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Список юзеров и балансы", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="💰 Начислить/списать баланс", callback_data="admin_change_balance")],
            [InlineKeyboardButton(text="🎁 Выдать промт пользователю", callback_data="admin_grant_prompt")],
            [InlineKeyboardButton(text="🏷 Управление промокодами", callback_data="admin_promos_menu")],
            [InlineKeyboardButton(text="💰 Изменить цены промтов", callback_data="admin_edit_prices")],
            [InlineKeyboardButton(text="📊 Статистика и аналитика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🔙 В пользовательский режим", callback_data="nav_main_menu")],
        ]
    )


def admin_users_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Начислить/списать баланс", callback_data="admin_change_balance")],
            [InlineKeyboardButton(text="🔙 В админ-панель", callback_data="admin_main")],
        ]
    )


def admin_promos_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
            [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin_list_promos")],
            [InlineKeyboardButton(text="🔙 В админ-панель", callback_data="admin_main")],
        ]
    )


def admin_promo_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📉 Процент скидки (%)", callback_data="promo_type:percent"),
                InlineKeyboardButton(text="⭐️ Скидка в Звёздах", callback_data="promo_type:stars"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")],
        ]
    )


def admin_promos_list_kb(promos: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for promo in promos:
        code = promo["code"]
        active_mark = "🟢" if promo["is_active"] else "🔴"
        discount_desc = f"{promo['discount_percent']}%" if promo["discount_percent"] > 0 else f"{promo['discount_stars']} ⭐️"
        text = f"{active_mark} {code} (-{discount_desc}) | {promo['used_count']}/{'∞' if promo['max_uses'] == -1 else promo['max_uses']}"
        buttons.append([
            InlineKeyboardButton(text=text, callback_data=f"admin_view_promo:{code}"),
            InlineKeyboardButton(text="🗑", callback_data=f"admin_del_promo:{code}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Создать новый", callback_data="admin_create_promo")])
    buttons.append([InlineKeyboardButton(text="🔙 В меню промокодов", callback_data="admin_promos_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_select_prompt_kb(prompts: List[Dict[str, Any]], action_prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for p in prompts:
        buttons.append([
            InlineKeyboardButton(text=f"{p['title']} ({p['price']} ⭐️)", callback_data=f"{action_prefix}:{p['id']}")
        ])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_confirm_broadcast_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Подтвердить и отправить", callback_data="confirm_broadcast")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")],
        ]
    )


def cancel_kb(callback_data: str = "cancel_fsm") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)]
        ]
    )
