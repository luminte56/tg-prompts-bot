import asyncio
import html
import re
from typing import Dict, Any, List, Optional
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import ADMIN_IDS
import database as db
from keyboards import (
    admin_panel_kb,
    admin_users_kb,
    admin_bans_menu_kb,
    admin_banned_users_list_kb,
    admin_antibot_menu_kb,
    admin_scanned_bots_kb,
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
    AdminChangeBalanceState,
    AdminBanState,
    AdminDeleteUserState,
    AdminCleanReferrerState,
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


# -------------------- СПИСОК ЮЗЕРОВ И БАЛАНСЫ --------------------

PAGE_SIZE = 15


async def render_users_page(callback: CallbackQuery, page: int = 0, only_active: bool = True) -> None:
    summary = await db.get_users_summary()
    total_count = await db.count_users(only_active=only_active)
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    offset = page * PAGE_SIZE

    users = await db.get_all_users_with_stats(only_active=only_active, limit=PAGE_SIZE, offset=offset)
    filter_title = "🟢 Только активные (не заблокали)" if only_active else "📋 Все пользователи (с заблокировавшими)"

    header = (
        f"👥 <b>База пользователей бота</b>\n\n"
        f"📊 <b>Сводка:</b>\n"
        f"• Всего запустили бота: <b>{summary['total']}</b>\n"
        f"• 🟢 Активных (не заблокали): <b>{summary['active']}</b>\n"
        f"• 🔴 Заблокировали бота: <b>{summary['blocked']}</b>\n"
        f"• ⛔️ Забанено админом: <b>{summary.get('banned', 0)}</b>\n\n"
        f"🔍 Фильтр: <i>{filter_title}</i>\n"
        f"📄 Страница: <b>{page + 1} из {total_pages}</b>\n\n"
    )

    if not users:
        text = header + "<i>Пользователей по данному фильтру не найдено.</i>"
    else:
        lines = [header]
        for idx, u in enumerate(users, start=offset + 1):
            name = html.escape(u.get("first_name") or "Пользователь")
            uname = f"@{html.escape(u['username'])}" if u.get("username") else "без @"
            if u.get("is_banned"):
                status_badge = f"⛔️ Забанен ({html.escape(u.get('ban_reason') or 'бан')})"
            elif u.get("is_blocked"):
                status_badge = "🔴 Заблокировал"
            else:
                status_badge = "🟢 Активен"
            created = str(u.get("created_at") or "")[:16]
            ref_badge = f" | 👤 Реферер: <code>{u['referrer_id']}</code>" if u.get("referrer_id") else ""
            lines.append(
                f"{idx}. <b>{name}</b> ({uname}) — {status_badge}\n"
                f"   🆔 ID: <code>{u['user_id']}</code>{ref_badge}\n"
                f"   ⭐️ Баланс: <b>{u.get('balance', 0)} ⭐️</b> | 👥 Рефов: <b>{u.get('referrals_count', 0)}</b> | 🛒 Покупок: <b>{u.get('purchases_count', 0)}</b>\n"
                f"   🕒 Рег: <code>{created}</code>\n"
            )
        text = "\n".join(lines)

    kb = admin_users_kb(page=page, total_pages=total_pages, only_active=only_active)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data == "admin_users_list")
async def cb_admin_users_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await callback.answer()
    try:
        await render_users_page(callback, page=0, only_active=True)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка загрузки списка: {e}")


@router.callback_query(F.data.startswith("admin_users_page:"))
async def cb_admin_users_page(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await callback.answer()
    parts = callback.data.split(":")
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    only_active = bool(int(parts[2])) if len(parts) > 2 and parts[2].isdigit() else True
    await render_users_page(callback, page=page, only_active=only_active)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "admin_users_sync_blocks")
async def cb_admin_users_sync_blocks(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await callback.answer("Запускаю проверку блокировок...", show_alert=False)
    status_msg = await callback.message.answer(
        "⏳ <i>Проверяю статус блокировок пользователей через безопасный ping...</i>",
        parse_mode="HTML"
    )

    user_ids = await db.get_all_user_ids(only_active=False)
    checked = 0
    blocked_count = 0
    active_count = 0

    for uid in user_ids:
        try:
            # Отправка action 'typing' не отправляет реальных сообщений юзеру
            await bot.send_chat_action(chat_id=uid, action="typing")
            await db.set_user_blocked(uid, False)
            active_count += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            await db.set_user_blocked(uid, True)
            blocked_count += 1
        except Exception:
            pass

        checked += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ <b>Синхронизация блокировок завершена!</b>\n\n"
        f"👥 Всего проверено: <b>{checked}</b>\n"
        f"🟢 Активных (не заблокали): <b>{active_count}</b>\n"
        f"🔴 Заблокировали бота: <b>{blocked_count}</b>",
        parse_mode="HTML"
    )
    await render_users_page(callback, page=0, only_active=True)


@router.callback_query(F.data == "admin_users_export_txt")
async def cb_admin_users_export_txt(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await callback.answer()
    users = await db.get_all_users_export()
    if not users:
        await callback.message.answer("👥 В базе пока нет пользователей.")
        return

    lines = [
        f"=== СПИСОК ПОЛЬЗОВАТЕЛЕЙ БОТА (Всего: {len(users)}) ===",
        f"{'ID':<15} | {'СТАТУС':<15} | {'БАЛАНС':<8} | {'РЕФЫ':<6} | {'ПОКУПКИ':<8} | {'USERNAME':<20} | {'ИМЯ':<25} | {'РЕФЕРЕР':<12} | {'ДАТА РЕГИСТРАЦИИ'}",
        "-" * 135
    ]

    for u in users:
        if u.get("is_banned"):
            status_str = f"BANNED({u.get('ban_reason') or 'ban'})"
        elif u.get("is_blocked"):
            status_str = "BLOCKED"
        else:
            status_str = "ACTIVE"
        uname = f"@{u['username']}" if u.get("username") else "NO_USERNAME"
        name = (u.get("first_name") or "NO_NAME").replace("\n", " ")
        ref_id_str = str(u.get("referrer_id") or "-")
        lines.append(
            f"{u['user_id']:<15} | {status_str:<15} | {u.get('balance', 0):<8} | {u.get('referrals_count', 0):<6} | "
            f"{u.get('purchases_count', 0):<8} | {uname:<20} | {name:<25} | {ref_id_str:<12} | {u.get('created_at', '')}"
        )

    file_content = "\n".join(lines).encode("utf-8")
    doc = BufferedInputFile(file_content, filename="users_list.txt")
    await bot.send_document(
        chat_id=callback.message.chat.id,
        document=doc,
        caption=f"📁 <b>Полная выгрузка базы пользователей</b>\nВсего пользователей: <b>{len(users)}</b>",
        parse_mode="HTML"
    )


# -------------------- БЫСТРЫЕ КОМАНДЫ МОДЕРАЦИИ --------------------

@router.message(Command("ban"))
async def cmd_ban(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("ℹ️ Использование: <code>/ban &lt;user_id&gt; [причина]</code>", parse_mode="HTML")
        return

    target_id = int(parts[1])
    reason = parts[2] if len(parts) > 2 else "Нарушение правил / накрутка"

    if target_id in ADMIN_IDS:
        await message.answer("❌ Нельзя забанить администратора.")
        return

    ok = await db.ban_user(target_id, reason)
    if ok:
        await message.answer(
            f"⛔️ <b>Пользователь <code>{target_id}</code> успешно забанен!</b>\n"
            f"Причина: <i>{html.escape(reason)}</i>",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"⚠️ Пользователь с ID <code>{target_id}</code> не найден в базе.", parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("ℹ️ Использование: <code>/unban &lt;user_id&gt;</code>", parse_mode="HTML")
        return

    target_id = int(parts[1])
    ok = await db.unban_user(target_id)
    if ok:
        await message.answer(f"✅ <b>Пользователь <code>{target_id}</code> успешно разбанен!</b>", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Пользователь с ID <code>{target_id}</code> не найден в базе.", parse_mode="HTML")


@router.message(Command("deluser"))
async def cmd_deluser(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("ℹ️ Использование: <code>/deluser &lt;user_id&gt;</code>", parse_mode="HTML")
        return

    target_id = int(parts[1])
    if target_id in ADMIN_IDS:
        await message.answer("❌ Нельзя удалить администратора.")
        return

    ok, ref_id = await db.delete_user(target_id)
    if ok:
        ref_msg = f"\n👤 Счётчик рефералов у <code>{ref_id}</code> уменьшен на 1." if ref_id else ""
        await message.answer(f"🗑 <b>Пользователь <code>{target_id}</code> полностью удалён из базы!</b>{ref_msg}", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Пользователь с ID <code>{target_id}</code> не найден в базе.", parse_mode="HTML")


# -------------------- МЕНЮ УПРАВЛЕНИЯ БАНАМИ --------------------

@router.callback_query(F.data == "admin_bans_menu")
async def cb_admin_bans_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    banned = await db.get_banned_users()
    text = (
        f"🚫 <b>Управление банами</b>\n\n"
        f"Всего забанено: <b>{len(banned)}</b> чел.\n\n"
        f"Забаненные пользователи полностью блокируются на уровне middleware бота: "
        f"они не могут просматривать каталог, вводить промокоды, покупать или получать рефералов.\n\n"
        f"Быстрые команды в чат:\n"
        f"• <code>/ban &lt;ID&gt; [причина]</code>\n"
        f"• <code>/unban &lt;ID&gt;</code>\n"
        f"• <code>/deluser &lt;ID&gt;</code>"
    )
    await callback.message.edit_text(text, reply_markup=admin_bans_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin_ban_user")
async def cb_admin_ban_user(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminBanState.waiting_for_user_id)
    await callback.message.edit_text(
        "🚫 <b>Блокировка пользователя</b>\n\n"
        "Отправь цифровой <b>Telegram ID</b> пользователя, которого нужно забанить:",
        reply_markup=cancel_kb("admin_bans_menu"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminBanState.waiting_for_user_id)
async def process_ban_user_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ ID должен содержать только цифры. Попробуй ещё раз или нажми отмену:")
        return

    target_id = int(text)
    if target_id in ADMIN_IDS:
        await message.answer("❌ Нельзя забанить администратора бота.")
        return

    target = await db.get_user(target_id)
    if not target:
        await message.answer(f"⚠️ Пользователь с ID <code>{target_id}</code> не найден в базе. Введи другой ID:")
        return

    await state.update_data(ban_user_id=target_id)
    await state.set_state(AdminBanState.waiting_for_reason)
    uname = f"@{target['username']}" if target.get("username") else target.get("first_name") or "Пользователь"
    await message.answer(
        f"👤 Выбран: <b>{html.escape(uname)}</b> (ID: <code>{target_id}</code>)\n\n"
        f"Напиши причину бана (или отправь <code>-</code> для дефолтной причины 'Нарушение правил'):",
        reply_markup=cancel_kb("admin_bans_menu"),
        parse_mode="HTML"
    )


@router.message(AdminBanState.waiting_for_reason)
async def process_ban_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target_id = data.get("ban_user_id")
    await state.clear()

    raw_reason = message.text.strip()
    reason = "Нарушение правил / накрутка" if raw_reason == "-" else raw_reason

    await db.ban_user(target_id, reason)
    await message.answer(
        f"⛔️ <b>Пользователь <code>{target_id}</code> забанен!</b>\n"
        f"Причина: <i>{html.escape(reason)}</i>",
        reply_markup=admin_bans_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_banned_list")
async def cb_admin_banned_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    await callback.answer()
    banned = await db.get_banned_users()
    if not banned:
        await callback.message.edit_text(
            "📋 <b>Список забаненных пуст.</b>\nВ боте нет заблокированных пользователей.",
            reply_markup=admin_bans_menu_kb(),
            parse_mode="HTML"
        )
        return

    text_lines = [
        f"📋 <b>Забаненные пользователи ({len(banned)} чел.):</b>\n"
    ]
    for idx, u in enumerate(banned[:20], 1):
        uname = f"@{html.escape(u['username'])}" if u.get("username") else "без @"
        name = html.escape(u.get("first_name") or "Без имени")
        reason = html.escape(u.get("ban_reason") or "без причины")
        text_lines.append(
            f"{idx}. <b>{name}</b> ({uname})\n"
            f"   🆔 ID: <code>{u['user_id']}</code> | ⚠️ <i>{reason}</i>\n"
        )

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=admin_banned_users_list_kb(banned),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_quick_unban:"))
async def cb_admin_quick_unban(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    uid = int(callback.data.split(":")[1])
    await db.unban_user(uid)
    await callback.answer(f"Пользователь {uid} разбанен!", show_alert=True)
    await cb_admin_banned_list(callback)


# -------------------- АНТИБОТ И ОЧИСТКА НАКРУТКИ --------------------

def is_suspicious_account(user: Dict[str, Any]) -> tuple[bool, str]:
    """Эвристический детектор накрученных ботов со странными никами."""
    if user.get("purchases_count", 0) > 0:
        return False, ""

    uname = (user.get("username") or "").strip().lower()
    first_name = (user.get("first_name") or "").strip()
    is_blocked = user.get("is_blocked", 0)
    has_referrer = bool(user.get("referrer_id"))

    reasons = []

    if is_blocked:
        reasons.append("заблокировал бота")

    if uname:
        if re.search(r'^[a-z]{5,}\d{2,}$', uname):
            reasons.append(f"автоген-ник @{uname}")
        elif len(uname) >= 14 and re.search(r'\d{3,}', uname):
            reasons.append(f"хэш-ник @{uname}")
        elif re.search(r'bot|farm|ref|promo|boost|clicker|spam', uname):
            reasons.append(f"подозрительный @{uname}")
    else:
        if not first_name or first_name in ["None", "null", "User", "Deleted Account"]:
            reasons.append("пустое имя без @")
        elif first_name.isdigit() or re.match(r'^[0-9_\-\.\+]+$', first_name):
            reasons.append(f"цифровое имя '{first_name}'")
        elif len(first_name) >= 12 and " " not in first_name and re.search(r'\d', first_name):
            reasons.append(f"случайный набор букв '{first_name}'")

    if reasons:
        return True, ", ".join(reasons)

    return False, ""


@router.callback_query(F.data == "admin_antibot_menu")
async def cb_admin_antibot_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    text = (
        "🧹 <b>Антибот и очистка накрутки</b>\n\n"
        "Инструменты для удаления накрученных аккаунтов со странными никами:\n\n"
        "• <b>🔍 Сканировать накрутку (авто-поиск)</b> — поиск автогенерированных ников, цифровых имён и мертвых душ\n"
        "• <b>💀 Удалить мертвых ботов</b> — удаление пользователей с <code>is_blocked = 1</code> и 0 покупок\n"
        "• <b>🎯 Очистить накрутку по ID реферера</b> — удаление всех ботов у конкретного накрутчика с аннулированием его баланса\n"
        "• <b>🗑 Удалить пользователя по ID</b> — полное удаление конкретного аккаунта\n\n"
        "💡 <i>Также доступна быстрая команда:</i> <code>/deluser &lt;ID&gt;</code>"
    )
    await callback.message.edit_text(text, reply_markup=admin_antibot_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "antibot_scan")
async def cb_antibot_scan(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await callback.answer("Сканирую базу...")
    users = await db.get_all_users_raw()

    suspicious = []
    for u in users:
        is_bad, reason = is_suspicious_account(u)
        if is_bad:
            suspicious.append((u, reason))

    if not suspicious:
        await callback.message.edit_text(
            "✅ <b>Подозрительных накрученных пользователей не обнаружено!</b>\n\n"
            "Все пользователи в базе имеют корректные профили либо совершали покупки.",
            reply_markup=admin_antibot_menu_kb(),
            parse_mode="HTML"
        )
        return

    # Сохраняем ID найденных в FSM
    bad_uids = [u["user_id"] for u, _ in suspicious]
    await state.update_data(scanned_bad_uids=bad_uids)

    lines = [
        f"🚨 <b>Обнаружено подозрительных ботов/фейков: {len(suspicious)} шт.</b>\n"
    ]
    for idx, (u, reason) in enumerate(suspicious[:15], 1):
        name = html.escape(u.get("first_name") or "Без имени")
        uname = f"@{html.escape(u['username'])}" if u.get("username") else "без @"
        lines.append(
            f"{idx}. <b>{name}</b> ({uname})\n"
            f"   🆔 <code>{u['user_id']}</code> | ⚠️ <i>{reason}</i>\n"
        )

    if len(suspicious) > 15:
        lines.append(f"<i>...и ещё {len(suspicious) - 15} аккаунтов.</i>\n")

    lines.append("Нажми <b>🔥 Удалить всех найденных</b>, чтобы очистить базу от этой накрутки:")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_scanned_bots_kb(len(suspicious)),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "antibot_purge_all_scanned")
async def cb_antibot_purge_all_scanned(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    bad_uids = data.get("scanned_bad_uids", [])
    await state.clear()

    if not bad_uids:
        users = await db.get_all_users_raw()
        bad_uids = [u["user_id"] for u in users if is_suspicious_account(u)[0]]

    deleted_count = await db.delete_users_by_ids(bad_uids)
    await callback.answer(f"Удалено {deleted_count} ботов!", show_alert=True)
    await callback.message.edit_text(
        f"💥 <b>Накрутка успешно зачищена!</b>\n\n"
        f"🗑 Удалено фейковых пользователей: <b>{deleted_count}</b> шт.\n"
        f"База данных очищена от мусора.",
        reply_markup=admin_antibot_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "antibot_delete_dead")
async def cb_antibot_delete_dead(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    await callback.answer("Удаляю мертвых ботов...")
    count = await db.delete_dead_bots()
    await callback.message.edit_text(
        f"💀 <b>Очистка мёртвых душ завершена!</b>\n\n"
        f"Удалено аккаунтов, которые заблокировали бота и не совершили покупок: <b>{count}</b> шт.",
        reply_markup=admin_antibot_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "antibot_clean_referrer")
async def cb_antibot_clean_referrer(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminCleanReferrerState.waiting_for_referrer_id)
    await callback.message.edit_text(
        "🎯 <b>Очистка накрученных рефералов</b>\n\n"
        "Отправь цифровой <b>Telegram ID накрутчика</b>.\n"
        "Все его рефералы с 0 покупок будут удалены, а полученные за них бонусные Звёзды — списаны с баланса:",
        reply_markup=cancel_kb("admin_antibot_menu"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminCleanReferrerState.waiting_for_referrer_id)
async def process_clean_referrer_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуй ещё раз или отмени:")
        return

    ref_id = int(text)
    await state.clear()

    deleted, deducted = await db.clean_referrer_bots(ref_id)
    await message.answer(
        f"🎯 <b>Накрутка у пользователя <code>{ref_id}</code> ликвидирована!</b>\n\n"
        f"🗑 Удалено накрученных ботов: <b>{deleted}</b> шт.\n"
        f"⭐️ Списано нечестно полученных звёзд: <b>{deducted} ⭐️</b>\n"
        f"Счётчик рефералов обнулён.",
        reply_markup=admin_antibot_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "antibot_delete_user")
async def cb_antibot_delete_user(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminDeleteUserState.waiting_for_user_id)
    await callback.message.edit_text(
        "🗑 <b>Удаление пользователя по ID</b>\n\n"
        "Отправь цифровой <b>Telegram ID</b> пользователя для полного удаления из базы:",
        reply_markup=cancel_kb("admin_antibot_menu"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminDeleteUserState.waiting_for_user_id)
async def process_delete_user_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуй ещё раз или отмени:")
        return

    target_id = int(text)
    if target_id in ADMIN_IDS:
        await message.answer("❌ Нельзя удалить администратора бота.")
        return

    await state.clear()
    ok, ref_id = await db.delete_user(target_id)
    if ok:
        ref_msg = f"\n👤 Счётчик рефералов у <code>{ref_id}</code> уменьшен." if ref_id else ""
        await message.answer(
            f"🗑 <b>Пользователь <code>{target_id}</code> успешно удалён из базы!</b>{ref_msg}",
            reply_markup=admin_antibot_menu_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"⚠️ Пользователь с ID <code>{target_id}</code> не найден в базе.",
            reply_markup=admin_antibot_menu_kb(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "admin_change_balance")
async def cb_admin_change_balance(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminChangeBalanceState.waiting_for_user_id)
    await callback.message.edit_text(
        "💰 **Начисление / списание баланса**\n\n"
        "Введи цифровой **Telegram ID** пользователя:",
        reply_markup=cancel_kb("admin_main"),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminChangeBalanceState.waiting_for_user_id)
async def process_balance_user_id(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуй ещё раз:", reply_markup=cancel_kb("admin_main"))
        return

    target_user_id = int(text)
    user_record = await db.get_user(target_user_id)
    if not user_record:
        await message.answer(f"❌ Пользователь с ID `{target_user_id}` не найден в базе. Он должен хотя бы раз нажать /start в боте.", reply_markup=cancel_kb("admin_main"))
        return

    await state.update_data(target_user_id=target_user_id)
    await state.set_state(AdminChangeBalanceState.waiting_for_amount)

    current_balance = user_record.get("balance", 0)
    u_label = f"@{user_record['username']}" if user_record.get("username") else user_record.get("first_name", "")
    await message.answer(
        f"👤 Пользователь: {u_label} (`{target_user_id}`)\n"
        f"⭐️ Текущий баланс: `{current_balance} ⭐️`\n\n"
        f"Введи сумму для изменения (например, `10` чтобы начислить 10 ⭐️, или `-5` чтобы списать):",
        reply_markup=cancel_kb("admin_main"),
        parse_mode="Markdown"
    )


@router.message(AdminChangeBalanceState.waiting_for_amount)
async def process_balance_amount(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text.strip()
    try:
        delta = int(text)
    except ValueError:
        await message.answer("❌ Введи целое число (положительное для начисления, отрицательное для списания):")
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    new_balance = await db.update_user_balance(target_user_id, delta)

    # Оповещаем пользователя
    try:
        action_word = "начислено" if delta >= 0 else "списано"
        await bot.send_message(
            chat_id=target_user_id,
            text=(
                f"💳 **Изменение баланса!**\n\n"
                f"Администратор изменил ваш баланс: **{'+' if delta > 0 else ''}{delta} ⭐️** ({action_word}).\n"
                f"⭐️ Ваш текущий баланс: **{new_balance} ⭐️**."
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await message.answer(
        f"✅ **Баланс успешно обновлен!**\n\n"
        f"👤 ID: `{target_user_id}`\n"
        f"⭐️ Изменение: `{'+' if delta > 0 else ''}{delta} ⭐️`\n"
        f"💰 Новый баланс пользователя: `{new_balance} ⭐️`",
        reply_markup=admin_panel_kb(),
        parse_mode="Markdown"
    )


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
        await callback.answer("Доступ запрещен.", show_alert=True)
        return

    await callback.answer()
    stats = await db.get_stats()
    text_lines = [
        "📊 <b>Статистика продаж и бота White Lord IntelLab</b>\n",
        f"👥 Всего пользователей в базе: <code>{stats['total_users']}</code>",
        f"🛒 Всего совершено покупок: <code>{stats['total_sales']}</code>",
        f"⭐️ Всего заработано Stars: <code>{stats['total_revenue']} ⭐️</code>",
        f"🏷 Активных промокодов: <code>{stats['active_promos']}</code>",
        f"💎 Всего промтов в каталоге: <code>{stats['total_prompts']}</code>\n",
    ]

    if stats["recent_purchases"]:
        text_lines.append("🕒 <b>Последние покупки:</b>")
        for p in stats["recent_purchases"]:
            user_lbl = f"@{html.escape(p['username'])}" if p.get("username") else f"ID <code>{p['user_id']}</code>"
            promo_lbl = f" (промо: {html.escape(p['promo_code'])})" if p.get("promo_code") else ""
            title = html.escape(p.get("title") or "")
            text_lines.append(f"• <code>{p['purchased_at'][:16]}</code> | {user_lbl} -> <b>{title}</b> [{p['price_paid']} ⭐️]{promo_lbl}")
    else:
        text_lines.append("🕒 Покупок пока не было.")

    await callback.message.edit_text("\n".join(text_lines), reply_markup=admin_panel_kb(), parse_mode="HTML")


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
        except (TelegramForbiddenError, TelegramBadRequest):
            blocked += 1
            await db.set_user_blocked(uid, True)
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
