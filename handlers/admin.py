import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
import database as db
from keyboards import (
    admin_panel_kb,
    admin_promos_kb,
    admin_promo_type_kb,
    admin_promos_list_kb,
    admin_select_prompt_kb,
    admin_confirm_broadcast_kb,
    cancel_kb,
)
from states import (
    AdminGrantState,
    AdminPromoState,
    AdminEditPriceState,
    AdminBroadcastState,
)
from utils import get_prompt_file_info

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# -------------------- ГЛАВНОЕ МЕНЮ АДМИНКИ --------------------

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "👑 **Панель управления White Lord IntelLab**\n\n"
        "Выбери необходимое действие:",
        reply_markup=admin_panel_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "👑 **Панель управления White Lord IntelLab**\n\n"
        "Выбери необходимое действие:",
        reply_markup=admin_panel_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_cancel")
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb_admin_main(callback, state)


# -------------------- ВЫДАЧА ПРОМТА ПОЛЬЗОВАТЕЛЮ --------------------

@router.callback_query(F.data == "admin_grant_prompt")
async def cb_grant_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminGrantState.waiting_for_user_id)
    await callback.message.edit_text(
        "🎁 **Выдача промта пользователю**\n\n"
        "Введи цифровой **Telegram ID** пользователя, которому нужно выдать промт:\n\n"
        "_(Пользователь должен хотя бы раз нажать /start в этом боте)_",
        reply_markup=cancel_kb("admin_main"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminGrantState.waiting_for_user_id)
async def process_grant_user_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуй ещё раз:", reply_markup=cancel_kb("admin_main"))
        return

    target_user_id = int(text)
    user_record = await db.get_user(target_user_id)
    user_desc = f"ID `{target_user_id}`"
    if user_record and user_record.get("username"):
        user_desc += f" (@{user_record['username']})"

    await state.update_data(target_user_id=target_user_id)
    await state.set_state(AdminGrantState.waiting_for_prompt)

    prompts = await db.get_all_prompts(active_only=False)
    await message.answer(
        f"👤 Получатель: {user_desc}\n\n"
        f"Теперь выбери промт, который хочешь выдать:",
        reply_markup=admin_select_prompt_kb(prompts, "grant_to_user"),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("grant_to_user:"), AdminGrantState.waiting_for_prompt)
async def cb_grant_prompt_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        return

    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Пromt не найден!", show_alert=True)
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    # Записываем выдачу в покупки с нулевой ценой
    await db.record_purchase(
        user_id=target_user_id,
        prompt_id=prompt_id,
        price_paid=0,
        promo_code=None,
        charge_id="ADMIN_GRANT"
    )

    # Пробуем отправить файл и сообщение напрямую пользователю
    delivered = False
    delivery_err = ""
    try:
        file_info = get_prompt_file_info(prompt["filename"])
        clean_filename = f"{prompt['title'].replace('/', '_')}.txt"
        if file_info["exists"]:
            doc = FSInputFile(path=file_info["path"], filename=clean_filename)
            await bot.send_document(
                chat_id=target_user_id,
                document=doc,
                caption=(
                    f"🎁 **Вам выдан доступ к промту!**\n\n"
                    f"💎 **{prompt['title']}**\n\n"
                    f"Администратор открыл вам доступ. Файл прикреплен выше 👆\n"
                    f"Также промт навсегда добавлен в ваш раздел «📁 Мои покупки»."
                ),
                parse_mode="Markdown"
            )
            delivered = True
        else:
            await bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎁 **Вам выдан доступ к промту: {prompt['title']}!**\n"
                    f"Он доступен в разделе «📁 Мои покупки»."
                ),
                parse_mode="Markdown"
            )
            delivered = True
    except Exception as e:
        delivery_err = str(e)

    report = (
        f"✅ **Промт успешно выдан!**\n\n"
        f"💎 Промт: **{prompt['title']}**\n"
        f"👤 Пользователь: `{target_user_id}`\n"
        f"📦 Запись в БД: добавлена\n"
    )
    if delivered:
        report += "📨 Доставка в ЛС: **Успешно отправлено**"
    else:
        report += f"⚠️ Доставка в ЛС: **Ошибка** ({delivery_err}). Пользователь сможет скачать его из «Моих покупок», когда зайдет в бота."

    await callback.message.edit_text(report, reply_markup=admin_panel_kb(), parse_mode="Markdown")
    await callback.answer()


# -------------------- УПРАВЛЕНИЕ ПРОМОКОДАМИ --------------------

@router.callback_query(F.data == "admin_promos_menu")
async def cb_promos_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "🏷 **Управление промокодами**\n\n"
        "Здесь можно создавать промокоды на процентную скидку или фиксированную сумму в Звёздах, а также отслеживать их использование.",
        reply_markup=admin_promos_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_create_promo")
async def cb_create_promo_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminPromoState.waiting_for_code)
    await callback.message.edit_text(
        "➕ **Создание промокода (Шаг 1 из 4)**\n\n"
        "Введи текстовый код промокода (например: `LORD50`, `START20`, `CYBER`):",
        reply_markup=cancel_kb("admin_promos_menu"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminPromoState.waiting_for_code)
async def process_promo_code_name(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    if len(code) < 2 or len(code) > 30:
        await message.answer("❌ Длина промокода должна быть от 2 до 30 символов. Попробуй ещё раз:")
        return

    await state.update_data(promo_code=code)
    await state.set_state(AdminPromoState.waiting_for_type)

    await message.answer(
        f"🏷 Код: `{code}`\n\n"
        f"**Шаг 2 из 4:** Выбери тип скидки:",
        reply_markup=admin_promo_type_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("promo_type:"), AdminPromoState.waiting_for_type)
async def cb_promo_type_selected(callback: CallbackQuery, state: FSMContext) -> None:
    promo_type = callback.data.split(":")[1]
    await state.update_data(promo_type=promo_type)
    await state.set_state(AdminPromoState.waiting_for_value)

    if promo_type == "percent":
        text = "📉 **Шаг 3 из 4:** Введи процент скидки (от 1 до 100):"
    else:
        text = "⭐️ **Шаг 3 из 4:** Введи скидку в Звёздах (например: 5, 10, 20):"

    await callback.message.edit_text(text, reply_markup=cancel_kb("admin_promos_menu"), parse_mode="Markdown")
    await callback.answer()


@router.message(AdminPromoState.waiting_for_value)
async def process_promo_value(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введи целое положительное число:")
        return

    val = int(text)
    data = await state.get_data()
    promo_type = data.get("promo_type")

    if promo_type == "percent" and not (1 <= val <= 100):
        await message.answer("❌ Процент должен быть в диапазоне от 1 до 100:")
        return
    elif promo_type == "stars" and val <= 0:
        await message.answer("❌ Количество звёзд должно быть больше 0:")
        return

    await state.update_data(promo_val=val)
    await state.set_state(AdminPromoState.waiting_for_max_uses)

    await message.answer(
        f"📊 **Шаг 4 из 4:** Введи лимит активаций промокода.\n\n"
        f"_(Введи конкретное число, например `50`, или `0` для неограниченного количества)_:",
        reply_markup=cancel_kb("admin_promos_menu"),
        parse_mode="Markdown"
    )


@router.message(AdminPromoState.waiting_for_max_uses)
async def process_promo_max_uses(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введи число (0 для бесконечного):")
        return

    max_uses_input = int(text)
    max_uses = -1 if max_uses_input == 0 else max_uses_input

    data = await state.get_data()
    code = data.get("promo_code")
    promo_type = data.get("promo_type")
    val = data.get("promo_val")

    percent = val if promo_type == "percent" else 0
    stars = val if promo_type == "stars" else 0

    success = await db.create_promo_code(
        code=code,
        discount_percent=percent,
        discount_stars=stars,
        max_uses=max_uses
    )
    await state.clear()

    if success:
        type_str = f"{percent}%" if percent > 0 else f"{stars} ⭐️"
        limit_str = "без ограничений" if max_uses == -1 else f"{max_uses} раз"
        await message.answer(
            f"✅ **Промокод успешно создан!**\n\n"
            f"🏷 Код: `{code}`\n"
            f"🎁 Скидка: **{type_str}**\n"
            f"🔢 Лимит активаций: **{limit_str}**",
            reply_markup=admin_promos_kb(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Не удалось создать промокод в базе данных.", reply_markup=admin_promos_kb())


@router.callback_query(F.data == "admin_list_promos")
async def cb_list_promos(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    promos = await db.list_promo_codes()
    if not promos:
        await callback.message.edit_text(
            "📋 **Список промокодов пуст.**\n\nВы можете создать первый промокод прямо сейчас:",
            reply_markup=admin_promos_kb(),
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    text = (
        f"📋 **Активные и созданные промокоды ({len(promos)} шт.):**\n\n"
        f"Нажмите на 🗑 напротив нужного промокода, чтобы удалить его:"
    )
    await callback.message.edit_text(text, reply_markup=admin_promos_list_kb(promos), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_del_promo:"))
async def cb_delete_promo(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    code = callback.data.split(":")[1]
    deleted = await db.delete_promo_code(code)
    if deleted:
        await callback.answer(f"Промокод {code} удален!", show_alert=True)
    else:
        await callback.answer("Ошибка при удалении.", show_alert=True)

    promos = await db.list_promo_codes()
    if not promos:
        await callback.message.edit_text(
            "📋 **Список промокодов пуст.**",
            reply_markup=admin_promos_kb(),
            parse_mode="Markdown"
        )
        return

    await callback.message.edit_text(
        f"📋 **Список промокодов ({len(promos)} шт.):**",
        reply_markup=admin_promos_list_kb(promos),
        parse_mode="Markdown"
    )


# -------------------- ИЗМЕНЕНИЕ ЦЕН ПРОМТОВ --------------------

@router.callback_query(F.data == "admin_edit_prices")
async def cb_edit_prices_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    prompts = await db.get_all_prompts(active_only=False)
    await callback.message.edit_text(
        "💰 **Редактирование цен промтов**\n\n"
        "Выбери промт, для которого хочешь изменить стоимость:",
        reply_markup=admin_select_prompt_kb(prompts, "select_price_prompt"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_price_prompt:"))
async def cb_price_prompt_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Пromt не найден!", show_alert=True)
        return

    await state.update_data(edit_prompt_id=prompt_id)
    await state.set_state(AdminEditPriceState.waiting_for_new_price)

    await callback.message.edit_text(
        f"💰 **Изменение цены для:**\n**{prompt['title']}**\n\n"
        f"Текущая цена: `{prompt['price']} ⭐️`\n\n"
        f"Введи новую цену в Звёздах (целое число от 1 до 50):",
        reply_markup=cancel_kb("admin_edit_prices"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminEditPriceState.waiting_for_new_price)
async def process_new_price_input(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введи корректное число:")
        return

    new_price = int(text)
    if new_price < 1:
        await message.answer("❌ Цена должна быть не менее 1 ⭐️:")
        return

    data = await state.get_data()
    prompt_id = data.get("edit_prompt_id")
    await db.update_prompt_price(prompt_id, new_price)
    prompt = await db.get_prompt(prompt_id)
    await state.clear()

    await message.answer(
        f"✅ Цена для **{prompt['title']}** успешно обновлена!\n"
        f"Новая цена: `{new_price} ⭐️`",
        reply_markup=admin_panel_kb(),
        parse_mode="Markdown"
    )


# -------------------- СТАТИСТИКА --------------------

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    stats = await db.get_stats()
    text_lines = [
        "📊 **Статистика продаж и бота White Lord IntelLab**\n",
        f"👥 Всего пользователей в базе: `{stats['total_users']}`",
        f"🛒 Всего совершено покупок: `{stats['total_sales']}`",
        f"⭐️ Всего заработано Stars: `{stats['total_revenue']} ⭐️`",
        f"🏷 Активных промокодов: `{stats['active_promos']}`",
        f"💎 Всего промтов в каталоге: `{stats['total_prompts']}`\n",
    ]

    if stats["recent_purchases"]:
        text_lines.append("🕒 **Последние покупки:**")
        for p in stats["recent_purchases"]:
            user_lbl = f"@{p['username']}" if p.get("username") else f"ID {p['user_id']}"
            promo_lbl = f" (промо: {p['promo_code']})" if p.get("promo_code") else ""
            text_lines.append(f"• `{p['purchased_at'][:16]}` | {user_lbl} -> **{p['title']}** [{p['price_paid']} ⭐️]{promo_lbl}")
    else:
        text_lines.append("🕒 Покупок пока не было.")

    await callback.message.edit_text("\n".join(text_lines), reply_markup=admin_panel_kb(), parse_mode="Markdown")
    await callback.answer()


# -------------------- РАССЫЛКА --------------------

@router.callback_query(F.data == "admin_broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminBroadcastState.waiting_for_message)
    await callback.message.edit_text(
        "📢 **Создание рассылки**\n\n"
        "Отправь сообщение (текст, поддерживается Markdown), которое будет разослано всем пользователям бота:",
        reply_markup=cancel_kb("admin_main"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminBroadcastState.waiting_for_message)
async def process_broadcast_content(message: Message, state: FSMContext) -> None:
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminBroadcastState.waiting_for_confirm)

    await message.answer(
        f"📢 **Предпросмотр сообщения для рассылки:**\n\n"
        f"{message.text}\n\n"
        f"Отправить всем пользователям?",
        reply_markup=admin_confirm_broadcast_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "confirm_broadcast", AdminBroadcastState.waiting_for_confirm)
async def cb_confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    text_to_send = data.get("broadcast_text")
    await state.clear()

    user_ids = await db.get_all_user_ids()
    await callback.message.edit_text(f"⏳ Рассылка запущена для {len(user_ids)} пользователей...")

    success = 0
    blocked = 0

    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text_to_send, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)  # Защита от флуда
        except Exception:
            blocked += 1

    await callback.message.answer(
        f"📢 **Рассылка завершена!**\n\n"
        f"✅ Доставлено: `{success}`\n"
        f"❌ Не доставлено / заблокировали бота: `{blocked}`",
        reply_markup=admin_panel_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "cancel_broadcast", AdminBroadcastState.waiting_for_confirm)
async def cb_cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb_admin_main(callback, state)
