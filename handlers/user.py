import time
import html
from collections import defaultdict
from aiogram import Router, F, Bot, BaseMiddleware
from aiogram.types import (
    Message,
    CallbackQuery,
    PreCheckoutQuery,
    LabeledPrice,
    FSInputFile,
    ChatMemberUpdated,
    TelegramObject,
)
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, KICKED, MEMBER
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
import database as db
from keyboards import (
    main_menu_kb,
    catalog_kb,
    prompt_card_kb,
    my_purchases_kb,
    referral_menu_kb,
    referrals_list_back_kb,
    cancel_kb,
)
from states import PromoState
from utils import calculate_final_price, get_prompt_file_info

router = Router()

# In-memory трекер времени переходов по реферальным ссылкам (referrer_id -> [ts, ...])
ref_transitions_history = defaultdict(list)


class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user and user.id not in ADMIN_IDS:
            if await db.is_user_banned(user.id):
                if hasattr(event, "message") and event.message:
                    await event.message.answer("⛔️ Вы заблокированы в этом боте администратором.")
                elif hasattr(event, "answer"):
                    await event.answer("⛔️ Вы заблокированы администратором бота.", show_alert=True)
                return
        return await handler(event, data)


router.message.middleware(BanMiddleware())
router.callback_query.middleware(BanMiddleware())


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    user = message.from_user

    # Обработка реферального кода
    referrer_id = None
    if command.args:
        raw_args = command.args.strip()
        if raw_args.startswith("ref_"):
            raw_id = raw_args[4:]
        elif raw_args.startswith("ref"):
            raw_id = raw_args[3:]
        else:
            raw_id = raw_args
        if raw_id.isdigit():
            referrer_id = int(raw_id)

    # Защита от одновременной накрутки рефералов
    if referrer_id and referrer_id != user.id:
        existing_user = await db.get_user(user.id)
        if not existing_user:
            # 1. Если реферер уже заблокирован за накрутку
            if await db.is_user_banned(referrer_id):
                await db.upsert_user(user.id, user.username, user.first_name, None)
                await db.ban_user(user.id, f"Автобан: переход по ссылке забаненного накрутчика (ID: {referrer_id})")
                await message.answer("⛔️ Ссылка недействительна (аккаунт заблокирован за нарушения).")
                return

            # 2. Проверка одновременных переходов (burst окно <= 3.5 сек)
            now = time.time()
            recent_transitions = [t for t in ref_transitions_history[referrer_id] if now - t <= 3.5]
            db_delta = await db.get_recent_referral_delta(referrer_id)

            is_burst = (len(recent_transitions) >= 1) or (db_delta is not None and db_delta <= 3)

            if is_burst:
                interval = (now - recent_transitions[-1]) if recent_transitions else (db_delta or 0.0)
                # Блокируем накрутчика
                ban_reason = f"Автобан: одновременный переход по рефке (интервал {interval:.2f} сек)"
                await db.ban_user(referrer_id, ban_reason)
                # Чистим ботов реферера и аннулируем накрученные звёзды
                deleted_bots, deducted_stars = await db.clean_referrer_bots(referrer_id)
                # Регистрируем и блокируем текущего бота
                await db.upsert_user(user.id, user.username, user.first_name, None)
                await db.ban_user(user.id, f"Автобан: бот для накрутки рефералов (интервал {interval:.2f} сек)")
                ref_transitions_history[referrer_id].append(now)

                # Оповещаем администраторов
                ref_info = await db.get_user(referrer_id)
                ref_tag = f"@{ref_info['username']}" if ref_info and ref_info.get("username") else f"ID {referrer_id}"
                bot_tag = f"@{user.username}" if user.username else f"ID {user.id}"
                alert_text = (
                    f"🚨 <b>ОБНАРУЖЕНА ОДНОВРЕМЕННАЯ НАКРУТКА РЕФЕРАЛОВ!</b>\n\n"
                    f"👤 <b>Реферер (накрутчик):</b> {ref_tag} (<code>{referrer_id}</code>)\n"
                    f"🤖 <b>Бот-реферал:</b> {bot_tag} (<code>{user.id}</code>)\n"
                    f"⏱ <b>Интервал перехода:</b> <code>{interval:.2f} сек</code>\n\n"
                    f"🛡 <b>Принятые меры:</b>\n"
                    f"• Реферер <code>{referrer_id}</code> заблокирован навсегда.\n"
                    f"• Входящий аккаунт <code>{user.id}</code> заблокирован.\n"
                    f"• Удалено пустых рефералов: <b>{deleted_bots}</b>\n"
                    f"• Списано звёзд с баланса: <b>{deducted_stars} ⭐️</b>"
                )
                for adm in ADMIN_IDS:
                    try:
                        await bot.send_message(chat_id=adm, text=alert_text, parse_mode="HTML")
                    except Exception:
                        pass

                await message.answer("⛔️ Вы заблокированы за попытку одновременной накрутки рефералов.")
                return

            # Фиксируем переход в истории
            ref_transitions_history[referrer_id].append(now)
            ref_transitions_history[referrer_id] = [t for t in ref_transitions_history[referrer_id] if now - t <= 60.0]

    is_new, actual_ref, rewards = await db.upsert_user(user.id, user.username, user.first_name, referrer_id)

    # Оповещаем пригласившего
    if is_new and actual_ref:
        try:
            ref_stats = await db.get_user_ref_stats(actual_ref)
            u_title = f"@{user.username}" if user.username else f"{user.first_name} (ID: `{user.id}`)"
            ref_msg = (
                f"👤 **Новый реферал!**\n\n"
                f"По твоей ссылке присоединился: {u_title}\n"
                f"Всего приглашено: **{ref_stats['referrals_count']}** чел."
            )
            if rewards:
                for m_cnt, m_stars in rewards:
                    ref_msg += (
                        f"\n\n🎉 **Бонус достигнут!** За {m_cnt} рефералов тебе начислено **+{m_stars} ⭐️** на баланс!\n"
                        f"Текущий баланс: **{ref_stats['balance']} ⭐️**"
                    )
            await bot.send_message(chat_id=actual_ref, text=ref_msg, parse_mode="Markdown")
        except Exception:
            pass

    user_data = await db.get_user(user.id)
    user_balance = user_data.get("balance", 0) if user_data else 0

    text = (
        f"👋 **Привет, {user.first_name or 'друг'}!**\n\n"
        f"Добро пожаловать в магазин **«Промты от BazedDll»** — эксклюзивные системные промты и рабочие спецификации для нейросетей.\n\n"
        f"⭐️ **Твой баланс:** `{user_balance} ⭐️`\n\n"
        f"⚡️ **Что внутри:**\n"
        f"• Тюнинг и системные роли для Claude Sonnet, Gemini 3.5, Step-5-preview, Grok, DeepSeek, GLM, Qwen\n"
        f"• Сверхдешевые цены — **до 35 ⭐️** за промт!\n"
        f"• Оплата через **Telegram Stars** или **с баланса рефералов**\n"
        f"• Рефералка: зови друзей и получай звёзды на халяву!\n\n"
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
        f"👥 **Как получить звёзды бесплатно?**\n"
        f"Зайдите в раздел **«👥 Рефералка и баланс»**, скопируйте ссылку и отправьте друзьям:\n"
        f"• 5 друзей -> **+5 ⭐️** на баланс\n"
        f"• 10 друзей -> **+10 ⭐️** на баланс\n"
        f"• 15 друзей -> **+15 ⭐️** на баланс\n"
        f"Накопленные звёзды можно тратить на покупку любых промтов прямо с баланса!\n\n"
        f"📁 **Как получить купленный промт?**\n"
        f"Сразу после оплаты бот присылает исходный `.txt` файл. "
        f"Также файл в любое время доступен в разделе **«📁 Мои покупки»**.\n\n"
        f"🎟 **Как применить промокод?**\n"
        f"Нажмите кнопку **«🎟 Промокод»** в главном меню или в карточке любого промта и отправьте код в чат.\n\n"
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
    user_data = await db.get_user(user_id)
    user_balance = user_data.get("balance", 0) if user_data else 0

    text = (
        f"🏠 **Главное меню**\n\n"
        f"⭐️ Твой баланс: `{user_balance} ⭐️`\n\n"
        f"Выбирай нужный раздел ниже:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=main_menu_kb(user_id), parse_mode="Markdown")
    await callback.answer()


# -------------------- РЕФЕРАЛКА И БАЛАНС --------------------

@router.callback_query(F.data == "nav_referral")
async def cb_referral(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    ref_stats = await db.get_user_ref_stats(user_id)

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        f"👤 **Реферальная программа и Баланс**\n\n"
        f"⭐️ **Твой баланс:** `{ref_stats['balance']} ⭐️`\n"
        f"👥 **Приглашено друзей:** `{ref_stats['referrals_count']} чел.`\n"
        f"🎁 **Всего получено бонусов:** `{ref_stats['total_earned']} ⭐️`\n\n"
        f"🔗 **Твоя персональная реферальная ссылка:**\n"
        f"`{ref_link}`\n"
        f"_(Нажми на ссылку, чтобы скопировать)_\n\n"
        f"⚡️ **Бонусы за приглашения:**\n"
        f"• За **5** рефералов -> **+5 ⭐️** на баланс\n"
        f"• За **10** рефералов -> **+10 ⭐️** на баланс\n"
        f"• За **15** рефералов -> **+15 ⭐️** на баланс\n"
        f"• За **20** рефералов -> **+20 ⭐️** на баланс\n\n"
        f"🎯 До следующей награды осталось: **{ref_stats['needed_for_next']}** реф.\n\n"
        f"💡 **Оплата с баланса:**\n"
        f"Звёздами с баланса можно оплачивать любые промты в каталоге — без реальных затрат!"
    )
    await callback.message.edit_text(text, reply_markup=referral_menu_kb(), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "nav_my_referrals")
async def cb_my_referrals(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    referrals = await db.get_user_referrals(user_id, limit=20)

    if not referrals:
        await callback.message.edit_text(
            "👥 **Список рефералов пуст**\n\n"
            "Вы пока никого не пригласили.\n"
            "Скопируйте реферальную ссылку и отправьте друзьям или в каналы!",
            reply_markup=referrals_list_back_kb(),
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    text_lines = [
        f"👥 **Ваши приглашённые друзья (последние {len(referrals)}):**\n"
    ]
    for idx, r in enumerate(referrals, 1):
        uname = f"@{r['username']}" if r.get("username") else f"ID {r['user_id']}"
        dt = r["created_at"][:10] if r.get("created_at") else ""
        text_lines.append(f"{idx}. {uname} — `{dt}`")

    text_lines.append("\nПродолжайте приглашать, чтобы зарабатывать звёзды на баланс!")
    await callback.message.edit_text("\n".join(text_lines), reply_markup=referrals_list_back_kb(), parse_mode="Markdown")
    await callback.answer()


# -------------------- КАТАЛОГ И КАРТОЧКА ПРОМТА --------------------

@router.callback_query(F.data == "nav_catalog")
async def cb_catalog(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = callback.from_user.id
    prompts = await db.get_all_prompts(active_only=True)
    purchased = await db.get_user_purchased_prompts(user_id)
    purchased_ids = {p["id"] for p in purchased}

    text = (
        f"🛒 **Каталог системных промтов**\n\n"
        f"Здесь собраны все доступные промты. Нажмите на любой, чтобы посмотреть описание и приобрести:\n\n"
        f"Все цены указаны в ⭐️ Telegram Stars. Можно оплатить картой Stars или с внутреннего баланса рефералов."
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
        await callback.answer("Промт не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    is_admin = user_id in ADMIN_IDS
    has_purchased = is_admin or await db.has_user_purchased(user_id, prompt_id)

    user_data = await db.get_user(user_id)
    user_balance = user_data.get("balance", 0) if user_data else 0

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

    text_lines.append(f"\n⭐️ **Ваш баланс:** `{user_balance} ⭐️`")

    if has_purchased:
        text_lines.append("\n✅ **У вас уже есть доступ к этому промту!**")

    text = "\n".join(text_lines)

    await callback.message.edit_text(
        text,
        reply_markup=prompt_card_kb(prompt_id, has_purchased, final_price, bool(promo_data), user_balance),
        parse_mode="Markdown"
    )
    await callback.answer()


# -------------------- ОПЛАТА С БАЛАНСА --------------------

@router.callback_query(F.data.startswith("buy_balance:"))
async def cb_buy_balance(callback: CallbackQuery, bot: Bot) -> None:
    prompt_id = callback.data.split(":")[1]
    prompt = await db.get_prompt(prompt_id)
    if not prompt:
        await callback.answer("Промт не найден!", show_alert=True)
        return

    user_id = callback.from_user.id
    if await db.has_user_purchased(user_id, prompt_id):
        await callback.answer("Вы уже приобрели этот промт!", show_alert=True)
        return

    user_data = await db.get_user(user_id)
    user_balance = user_data.get("balance", 0) if user_data else 0

    active_promo_code = await db.get_user_active_promo(user_id)
    promo_data = None
    if active_promo_code:
        valid, _, promo = await db.check_promo_eligibility(user_id, active_promo_code)
        if valid:
            promo_data = promo

    final_price, _, _ = calculate_final_price(prompt["price"], promo_data)

    if user_balance < final_price:
        await callback.answer(
            f"Недостаточно звёзд на балансе! Требуется: {final_price} ⭐️, у вас: {user_balance} ⭐️",
            show_alert=True
        )
        return

    # Списываем баланс
    new_balance = await db.update_user_balance(user_id, -final_price)
    promo_code = promo_data["code"] if promo_data else None

    # Записываем покупку
    await db.record_purchase(
        user_id=user_id,
        prompt_id=prompt_id,
        price_paid=final_price,
        promo_code=promo_code,
        charge_id="BALANCE_PAYMENT"
    )

    if promo_code:
        await db.apply_promo_usage(promo_code, user_id)
        await db.set_user_active_promo(user_id, None)

    # Отправляем файл
    file_info = get_prompt_file_info(prompt["filename"])
    clean_filename = f"{prompt['title'].replace('/', '_')}.txt"
    if file_info["exists"]:
        doc = FSInputFile(path=file_info["path"], filename=clean_filename)
        await callback.message.answer_document(
            document=doc,
            caption=(
                f"🎉 **Промт успешно оплачен с баланса!**\n\n"
                f"💎 **{prompt['title']}**\n"
                f"⭐️ Списано с баланса: `{final_price} ⭐️`\n"
                f"💰 Остаток баланса: `{new_balance} ⭐️`\n\n"
                f"Файл прикреплен выше 👆\n"
                f"Промт навсегда добавлен в ваш раздел «📁 Мои покупки»."
            ),
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer(
            f"✅ Промт **{prompt['title']}** оплачен с баланса ({final_price} ⭐️)!\n"
            f"Остаток: `{new_balance} ⭐️`."
        )

    # Оповещаем админов
    for admin_id in ADMIN_IDS:
        try:
            u_lbl = f"@{callback.from_user.username}" if callback.from_user.username else f"ID {user_id}"
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"💳 **Покупка с баланса!**\n\n"
                    f"👤 Покупатель: {u_lbl}\n"
                    f"💎 Промт: **{prompt['title']}**\n"
                    f"⭐️ Сумма: `{final_price} ⭐️` (с баланса)\n"
                    f"💰 Остаток на счете юзера: `{new_balance} ⭐️`"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await callback.answer("Успешно оплачено с баланса!")


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
            user_data = await db.get_user(user_id)
            user_balance = user_data.get("balance", 0) if user_data else 0
            await message.answer(
                f"{text}\n\nВозвращаемся к промту **{prompt['title']}**...",
                reply_markup=prompt_card_kb(return_prompt_id, False, final_price, True, user_balance),
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
        await callback.answer("Промт не найден!", show_alert=True)
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
        await callback.answer("Промт не найден!", show_alert=True)
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
        await callback.answer("Промт не найден!", show_alert=True)
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
        await callback.answer("Промт не найден!", show_alert=True)
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


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def on_user_blocked_bot(event: ChatMemberUpdated) -> None:
    """Пользователь заблокировал бота."""
    await db.set_user_blocked(event.from_user.id, True)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def on_user_unblocked_bot(event: ChatMemberUpdated) -> None:
    """Пользователь разблокировал бота."""
    await db.set_user_blocked(event.from_user.id, False)
