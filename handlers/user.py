from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    PreCheckoutQuery,
    LabeledPrice,
    FSInputFile,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
import database as db
from keyboards import (
    main_menu_kb,
    catalog_kb,
    prompt_card_kb,
    my_purchases_kb,
    cancel_kb,
)
from states import PromoState
from utils import calculate_final_price, get_prompt_file_info

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    await db.upsert_user(user.id, user.username, user.first_name)

    text = (
        f"👋 **Привет, {user.first_name or 'друг'}!**\n\n"
        f"Добро пожаловать в магазин эксклюзивных системных промтов и рабочих спецификаций для нейросетей.\n\n"
        f"⚡️ **Что внутри:**\n"
        f"• Тюнинг и системные роли для Claude Sonnet, Gemini, Grok, DeepSeek, GLM, Qwen\n"
        f"• Оффенсив-ресерч, Windows Internals, реверс, чистый кодинг без морализаторства и шаблонной нудятины\n"
        f"• Сверхдешевые цены — **до 35 ⭐️** за промт!\n"
        f"• Официальная и моментальная оплата через **Telegram Stars**\n"
        f"• Все купленные промты навсегда сохраняются в твоем личном кабинете\n\n"
        f"Выбери нужный раздел в меню ниже 👇"
    )
    await message.answer(text, reply_markup=main_menu_kb(user.id), parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await show_help(message, message.from_user.id)


@router.callback_query(F.data == "nav_faq")
async def cb_faq(callback: CallbackQuery) -> None:
    await show_help(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


async def show_help(target_message: Message, user_id: int, edit: bool = False) -> None:
    text = (
        f"ℹ️ **Справка и частые вопросы:**\n\n"
        f"⭐️ **Что такое Telegram Stars?**\n"
        f"Это официальная внутренняя валюта Telegram для покупки цифровых товаров. "
        f"При нажатии кнопки «Купить» открывается нативное окно оплаты. "
        f"Если у вас нет Stars, Telegram предложит купить их в один клик с банковской карты или баланса App Store / Google Play / Fragment.\n\n"
        f"📁 **Как получить купленный промт?**\n"
        f"Сразу после оплаты бот присылает исходный `.txt` файл. "
        f"Также файл в любое время доступен в разделе **«📁 Мои покупки»**.\n\n"
        f"🎟 **Как применить промокод?**\n"
        f"Нажмите кнопку **«🎟 Промокод»** в главном меню или в карточке любого промта и отправьте код в чат.\n\n"
        f"🛠 **Как использовать промт в нейросети?**\n"
        f"Скопируйте содержимое файла в поле «Custom Instructions / System Prompt» в настройках вашей модели, веб-интерфейсе или API.\n\n"
        f"💬 **Поддержка:** Если возникли вопросы или пожелания, обратитесь к администратору."
    )
    if edit:
        await target_message.edit_text(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    else:
        await target_message.answer(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")


@router.callback_query(F.data == "nav_main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = callback.from_user.id
    text = (
        f"🏠 **Главное меню**\n\n"
        f"Выбирай нужный раздел ниже:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "nav_catalog")
async def cb_catalog(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = callback.from_user.id
    prompts = await db.get_all_prompts(active_only=True)
    purchased = await db.get_user_purchased_prompts(user_id)
    purchased_ids = {p["id"] for p in purchased}

    text = (
        f"🛒 **Каталог системных промтов**\n\n"
        f"Здесь собраны все доступные промты. Нажмите на любой, чтобы посмотреть подробное описание, размер и приобрести:\n\n"
        f"Все цены указаны в ⭐️ Telegram Stars."
    )
    await callback.message.edit_text(
        text,
        reply_markup=catalog_kb(prompts, purchased_ids),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("show_prompt:"))
async def cb_show_prompt(callback: CallbackQuery) -> None:
    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Пromt не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    is_admin = user_id in ADMIN_IDS
    has_purchased = is_admin or await db.has_user_purchased(user_id, prompt_id)

    # Проверяем промокод
    active_promo_code = await db.get_user_active_promo(user_id)
    promo_data = None
    if active_promo_code:
        valid, _, promo = await db.check_promo_eligibility(user_id, active_promo_code)
        if valid:
            promo_data = promo

    final_price, discount, promo_info = calculate_final_price(prompt["price"], promo_data)
    file_info = get_prompt_file_info(prompt["filename"])

    text_lines = [
        f"💎 **{prompt['title']}**\n",
        f"📝 **Описание:**",
        f"{prompt['description']}\n",
        f"📊 **Характеристики:**",
        f"• Размер: `{file_info['size_kb']} КБ` (~`{file_info['char_count']}` символов)",
        f"• Формат: `.txt` (UTF-8)",
        f"• Базовая цена: `{prompt['price']} ⭐️`"
    ]

    if promo_info and not has_purchased:
        text_lines.append(f"\n{promo_info}")
        text_lines.append(f"🔥 **Итоговая цена со скидкой:** `{final_price} ⭐️`")

    if has_purchased:
        text_lines.append("\n✅ **У вас уже есть доступ к этому промту!**")

    text = "\n".join(text_lines)

    await callback.message.edit_text(
        text,
        reply_markup=prompt_card_kb(prompt_id, has_purchased, final_price, bool(promo_data)),
        parse_mode="Markdown"
    )
    await callback.answer()


# -------------------- ПРОМОКОДЫ --------------------

@router.callback_query(F.data == "nav_enter_promo")
async def cb_enter_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoState.waiting_for_code)
    await state.update_data(return_prompt_id=None)
    await callback.message.edit_text(
        "🎟 **Активация промокода**\n\n"
        "Отправь в ответном сообщении промокод на скидку:",
        reply_markup=cancel_kb("nav_main_menu"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("enter_promo_for:"))
async def cb_enter_promo_for_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    prompt_id = callback.data.split(":")[1]
    await state.set_state(PromoState.waiting_for_code)
    await state.update_data(return_prompt_id=prompt_id)
    await callback.message.edit_text(
        "🎟 **Активация промокода**\n\n"
        "Отправь в ответном сообщении промокод на скидку:",
        reply_markup=cancel_kb(f"show_prompt:{prompt_id}"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(PromoState.waiting_for_code)
async def process_promo_code_input(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    user_id = message.from_user.id

    valid, reason, promo = await db.check_promo_eligibility(user_id, code)
    if not valid:
        await message.answer(
            f"❌ **Ошибка активации:** {reason}\n\n"
            f"Попробуй ввести другой промокод или вернись в меню:",
            reply_markup=cancel_kb("nav_main_menu"),
            parse_mode="Markdown"
        )
        return

    # Сохраняем активный промокод
    await db.set_user_active_promo(user_id, code)

    data = await state.get_data()
    return_prompt_id = data.get("return_prompt_id")
    await state.clear()

    discount_desc = f"{promo['discount_percent']}%" if promo["discount_percent"] > 0 else f"{promo['discount_stars']} ⭐️"
    text = (
        f"🎉 **Промокод `{code}` успешно применен!**\n\n"
        f"Твоя скидка: **{discount_desc}** на следующую покупку."
    )

    if return_prompt_id:
        prompt = await db.get_prompt(return_prompt_id)
        if prompt:
            final_price, _, promo_info = calculate_final_price(prompt["price"], promo)
            await message.answer(
                f"{text}\n\nВозвращаемся к промту **{prompt['title']}**...",
                reply_markup=prompt_card_kb(return_prompt_id, False, final_price, True),
                parse_mode="Markdown"
            )
            return

    await message.answer(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")


# -------------------- ПОКУПКА ЧЕРЕЗ TELEGRAM STARS --------------------

@router.callback_query(F.data.startswith("buy_prompt:"))
async def cb_buy_prompt(callback: CallbackQuery, bot: Bot) -> None:
    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Пromt не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    if await db.has_user_purchased(user_id, prompt_id):
        await callback.answer("Вы уже приобрели этот промт!", show_alert=True)
        return

    active_promo_code = await db.get_user_active_promo(user_id)
    promo_data = None
    if active_promo_code:
        valid, _, promo = await db.check_promo_eligibility(user_id, active_promo_code)
        if valid:
            promo_data = promo
        else:
            await db.set_user_active_promo(user_id, None)

    final_price, discount, promo_info = calculate_final_price(prompt["price"], promo_data)

    if final_price <= 0:
        # Бесплатная выдача по 100% промокоду
        await process_free_grant(callback.message, user_id, prompt, promo_data)
        await callback.answer()
        return

    # Отправляем официальный инвойс Telegram Stars
    payload = f"buy:{prompt_id}:{user_id}:{final_price}"
    if promo_data:
        payload += f":{promo_data['code']}"

    try:
        await callback.message.answer_invoice(
            title=f"{prompt['title']}",
            description=f"Системный промт: {prompt['description'][:200]}",
            payload=payload,
            provider_token="",  # Для Stars пусто
            currency="XTR",
            prices=[LabeledPrice(label=prompt['title'][:30], amount=final_price)],
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"Ошибка создания счета: {e}", show_alert=True)


@router.callback_query(F.data.startswith("claim_free:"))
async def cb_claim_free(callback: CallbackQuery) -> None:
    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Пromt не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    active_promo_code = await db.get_user_active_promo(user_id)
    promo_data = None
    if active_promo_code:
        valid, _, promo = await db.check_promo_eligibility(user_id, active_promo_code)
        if valid:
            promo_data = promo

    final_price, _, _ = calculate_final_price(prompt["price"], promo_data)
    if final_price > 0:
        await callback.answer("Цена изменилась, требуется оплата.", show_alert=True)
        return

    await process_free_grant(callback.message, user_id, prompt, promo_data)
    await callback.answer()


async def process_free_grant(target_message: Message, user_id: int, prompt: dict, promo: dict) -> None:
    promo_code = promo["code"] if promo else None
    await db.record_purchase(
        user_id=user_id,
        prompt_id=prompt["id"],
        price_paid=0,
        promo_code=promo_code,
        charge_id=f"FREE_{promo_code}"
    )

    if promo_code:
        await db.apply_promo_usage(promo_code, user_id)
        await db.set_user_active_promo(user_id, None)

    file_info = get_prompt_file_info(prompt["filename"])
    if file_info["exists"]:
        clean_filename = f"{prompt['title'].replace('/', '_')}.txt"
        doc = FSInputFile(path=file_info["path"], filename=clean_filename)
        await target_message.answer_document(
            document=doc,
            caption=(
                f"🎉 **Поздравляем! Промт получен бесплатно по промокоду!**\n\n"
                f"💎 **{prompt['title']}**\n\n"
                f"Файл прикреплен выше 👆\n"
                f"Промт навсегда добавлен в ваш раздел «📁 Мои покупки»."
            ),
            parse_mode="Markdown"
        )
    else:
        await target_message.answer(
            f"✅ Промт **{prompt['title']}** успешно активирован!\n(Файл временно недоступен на диске, обратитесь к админу)."
        )


@router.pre_checkout_query()
async def handle_pre_checkout(query: PreCheckoutQuery) -> None:
    # Одобряем платеж Telegram Stars
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message, bot: Bot) -> None:
    sp = message.successful_payment
    payload_parts = sp.invoice_payload.split(":")
    # payload format: buy:prompt_id:user_id:final_price[:promo_code]
    prompt_id = payload_parts[1]
    user_id = int(payload_parts[2])
    price_paid = sp.total_amount
    charge_id = sp.telegram_payment_charge_id
    promo_code = payload_parts[4] if len(payload_parts) > 4 else None

    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await message.answer("⚠️ Оплата принята, но промт не найден в базе. Напишите администратору!")
        return

    # Записываем покупку
    await db.record_purchase(
        user_id=user_id,
        prompt_id=prompt_id,
        price_paid=price_paid,
        promo_code=promo_code,
        charge_id=charge_id
    )

    # Если был промокод - фиксируем использование и сбрасываем
    if promo_code:
        await db.apply_promo_usage(promo_code, user_id)
        await db.set_user_active_promo(user_id, None)

    # Отправляем файл пользователю
    file_info = get_prompt_file_info(prompt["filename"])
    if file_info["exists"]:
        clean_filename = f"{prompt['title'].replace('/', '_')}.txt"
        doc = FSInputFile(path=file_info["path"], filename=clean_filename)
        await message.answer_document(
            document=doc,
            caption=(
                f"✅ **Оплата прошла успешно!**\n\n"
                f"💎 **{prompt['title']}**\n"
                f"⭐️ Оплачено: `{price_paid} ⭐️`\n\n"
                f"Твой промт готов к работе. Скачай `.txt` файл выше и скопируй в настройки своей модели.\n"
                f"Также промт всегда доступен в разделе «📁 Мои покупки»."
            ),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"✅ **Оплата прошла успешно ({price_paid} ⭐️)!**\n"
            f"Промт **{prompt['title']}** добавлен в ваш профиль."
        )

    # Оповещаем администраторов
    for admin_id in ADMIN_IDS:
        try:
            user_mention = f"@{message.from_user.username}" if message.from_user.username else f"ID {user_id}"
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"💰 **Новая покупка!**\n\n"
                    f"👤 Покупатель: {user_mention}\n"
                    f"💎 Промт: **{prompt['title']}**\n"
                    f"⭐️ Сумма: `{price_paid} ⭐️`\n"
                    f"🎟 Промокод: `{promo_code or 'нет'}`\n"
                    f"🆔 Charge ID: `{charge_id}`"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass


# -------------------- СКАЧИВАНИЕ И ПРОСМОТР ТЕКСТА --------------------

@router.callback_query(F.data.startswith("download_prompt:"))
async def cb_download_prompt(callback: CallbackQuery) -> None:
    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Пromt не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    is_admin = user_id in ADMIN_IDS
    if not is_admin and not await db.has_user_purchased(user_id, prompt_id):
        await callback.answer("Сначала необходимо приобрести этот промт!", show_alert=True)
        return

    file_info = get_prompt_file_info(prompt["filename"])
    if not file_info["exists"]:
        await callback.answer("Файл на сервере не найден!", show_alert=True)
        return

    clean_filename = f"{prompt['title'].replace('/', '_')}.txt"
    doc = FSInputFile(path=file_info["path"], filename=clean_filename)

    await callback.message.answer_document(
        document=doc,
        caption=f"📥 **{prompt['title']}**\nРазмер: `{file_info['size_kb']} КБ`",
        parse_mode="Markdown"
    )
    await callback.answer("Файл отправлен!")


@router.callback_query(F.data.startswith("view_text_prompt:"))
async def cb_view_text_prompt(callback: CallbackQuery) -> None:
    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Пromt не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    is_admin = user_id in ADMIN_IDS
    if not is_admin and not await db.has_user_purchased(user_id, prompt_id):
        await callback.answer("Сначала необходимо приобрести этот промт!", show_alert=True)
        return

    file_info = get_prompt_file_info(prompt["filename"])
    if not file_info["exists"]:
        await callback.answer("Файл не найден!", show_alert=True)
        return

    text = file_info["text"]
    if len(text) <= 3500:
        await callback.message.answer(
            f"📄 **Текст промта: {prompt['title']}**\n\n```text\n{text}\n```",
            parse_mode="Markdown"
        )
    else:
        preview = text[:3200]
        await callback.message.answer(
            f"📄 **Фрагмент промта: {prompt['title']}**\n\n```text\n{preview}\n...\n```\n"
            f"✂️ *Текст слишком большой ({len(text)} символов), используй кнопку скачивания файла выше.*",
            parse_mode="Markdown"
        )
    await callback.answer()


# -------------------- МОИ ПОКУПКИ --------------------

@router.callback_query(F.data == "nav_my_purchases")
async def cb_my_purchases(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    purchases = await db.get_user_purchased_prompts(user_id)

    if not purchases:
        await callback.message.edit_text(
            "📁 **Мои покупки**\n\n"
            "У вас пока нет купленных промтов.\n"
            "Загляните в наш каталог — там много мощного материала по сверхдешевым ценам!",
            reply_markup=catalog_kb(await db.get_all_prompts(active_only=True), set()),
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    text = (
        f"📁 **Ваша библиотека ({len(purchases)} шт.):**\n\n"
        f"Нажмите на любой промт ниже, чтобы моментально скачать его `.txt` файл:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=my_purchases_kb(purchases),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_fsm")
async def cb_cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb_main_menu(callback, state)
