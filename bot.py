import asyncio
import logging
import os
import sys
from typing import Optional

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
    Message,
)

import config
from database import (
    add_friend, add_photo, count_friends, count_photos,
    delete_photo, get_friend, get_friends, get_photo_by_id,
    get_photos, init_db, is_friend, remove_friend,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MaximPhotoBot")

router = Router()
PER_PAGE = 5


# ══════════════════ FSM ══════════════════

class AddFriendState(StatesGroup):
    waiting = State()


# ══════════════════ AUTH HELPER ══════════════════

async def is_authorized(uid: int) -> bool:
    return config.is_admin(uid) or await is_friend(uid)


# ══════════════════ KEYBOARDS ══════════════════

def kb_main(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📸 Фото", callback_data="m:ph"),
         InlineKeyboardButton(text="👥 Друзі", callback_data="m:fr")],
        [InlineKeyboardButton(text="ℹ️ Як користуватися", callback_data="m:help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_photos_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Переглянути всі", callback_data="pl:0")],
        [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="m:main")],
    ])


def kb_photo_list(photos: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for p in photos:
        cap = p["caption"] or "без назви"
        if len(cap) > 22:
            cap = cap[:19] + "…"
        rows.append([
            InlineKeyboardButton(text=f"🖼 #{p['id']}: {cap}", callback_data=f"pv:{p['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"pd:{p['id']}"),
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"pl:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"· {page + 1}/{total_pages} ·", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"pl:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="m:ph")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_photo_view(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Видалити це фото", callback_data=f"pd:{pid}")],
        [InlineKeyboardButton(text="⬅️ До списку", callback_data="pl:0")],
    ])


def kb_confirm_delete_photo(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"pdc:{pid}"),
         InlineKeyboardButton(text="❌ Ні", callback_data="pl:0")],
    ])


def kb_friends(friends: list, is_admin: bool) -> InlineKeyboardMarkup:
    rows = []
    for f in friends:
        name = f["first_name"] or f["username"] or str(f["user_id"])
        row = [InlineKeyboardButton(text=f"👤 {name}", callback_data="noop")]
        if is_admin:
            row.append(InlineKeyboardButton(text="❌", callback_data=f"fd:{f['user_id']}"))
        rows.append(row)
    if is_admin:
        rows.append([InlineKeyboardButton(text="➕ Додати друга", callback_data="fa")])
    rows.append([InlineKeyboardButton(text="⬅️ Головне меню", callback_data="m:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm_delete_friend(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Так, видалити", callback_data=f"fdc:{uid}"),
         InlineKeyboardButton(text="❌ Ні", callback_data="m:fr")],
    ])


def kb_back(target: str = "m:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Головне меню", callback_data=target)],
    ])


def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="m:fr")],
    ])


# ══════════════════ RENDER HELPERS ══════════════════

async def render_main(user, bot_username: str) -> tuple[str, InlineKeyboardMarkup]:
    total = await count_photos()
    is_adm = config.is_admin(user.id)
    role = "👑 Адмін" if is_adm else "👤 Друг"
    text = (
        f"{'═' * 26}\n"
        f"  👋 <b>{user.first_name}</b>  {role}\n"
        f"{'═' * 26}\n\n"
        f"  📸  Фото в колекції: <b>{total}</b>\n"
        f"  🤖  Інлайн: <code>@{bot_username}</code>\n\n"
        f"  Обери дію нижче ⤵️"
    )
    return text, kb_main(is_adm)


async def render_photo_list(page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    total = await count_photos()
    if total == 0:
        text = "📭 <b>Колекція порожня</b>\n\nНадішли мені фото, щоб додати!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="m:ph")]
        ])
        return text, kb
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    photos = await get_photos(limit=PER_PAGE, offset=page * PER_PAGE)
    text = (
        f"📸 <b>Фото</b>  ·  {total} шт.  ·  стор. {page + 1}/{total_pages}\n"
        f"{'─' * 30}\n"
    )
    for p in photos:
        cap = p["caption"] or "без назви"
        text += f"  • <b>#{p['id']}</b> — {cap}\n"
    text += f"{'─' * 30}\n🖼 — переглянути  ·  🗑 — видалити"
    return text, kb_photo_list(photos, page, total_pages)


async def render_friends(is_admin: bool) -> tuple[str, InlineKeyboardMarkup]:
    friends = await get_friends()
    total = len(friends)
    text = (
        f"👥 <b>Друзі</b>  ·  {total} чол.\n"
        f"{'─' * 30}\n"
    )
    if total == 0:
        text += "  Поки що нікого немає\n"
        if is_admin:
            text += "\n  💡 Натисни <b>➕ Додати друга</b>"
    else:
        for f in friends:
            name = f["first_name"] or "—"
            uname = f" · @{f['username']}" if f["username"] else ""
            text += f"  👤 <b>{name}</b>{uname}\n      ID: <code>{f['user_id']}</code>\n"
    text += f"{'─' * 30}"
    return text, kb_friends(friends, is_admin)


# ══════════════════ /START ══════════════════

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    if not await is_authorized(uid):
        await message.answer(
            f"👋 Привіт, <b>{message.from_user.first_name}</b>!\n\n"
            f"⛔️ У тебе поки немає доступу.\n"
            f"Попроси адміністратора додати тебе.\n\n"
            f"🆔 Твій ID: <code>{uid}</code>\n"
            f"<i>Скинь цей ID адміну</i>"
        )
        return

    bot_me = await bot.get_me()
    text, kb = await render_main(message.from_user, bot_me.username)
    await message.answer(text, reply_markup=kb)


# ══════════════════ NAVIGATION ══════════════════

@router.callback_query(F.data == "noop")
async def cb_noop(q: CallbackQuery):
    await q.answer()


@router.callback_query(F.data == "m:main")
async def cb_main(q: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    if not await is_authorized(q.from_user.id):
        await q.answer("⛔️ Немає доступу", show_alert=True)
        return
    bot_me = await bot.get_me()
    text, kb = await render_main(q.from_user, bot_me.username)
    try:
        await q.message.edit_text(text, reply_markup=kb)
    except Exception:
        await q.message.answer(text, reply_markup=kb)
    await q.answer()


@router.callback_query(F.data == "m:help")
async def cb_help(q: CallbackQuery, bot: Bot):
    bot_me = await bot.get_me()
    text = (
        f"<b>ℹ️ Як користуватися</b>\n"
        f"{'─' * 30}\n\n"
        f"<b>📸 Додати фото:</b>\n"
        f"Просто надішли картинку сюди в чат.\n"
        f"Можна додати підпис для пошуку!\n\n"
        f"<b>💬 Надіслати фото другу:</b>\n"
        f"В будь-якому чаті набери:\n"
        f"<code>@{bot_me.username} </code>\n"
        f"Обери фото з меню — воно полетить!\n\n"
        f"<b>🔍 Пошук:</b>\n"
        f"<code>@{bot_me.username} кот</code>\n"
        f"Знайде фото з підписом «кот»\n\n"
        f"<b>👥 Друзі:</b>\n"
        f"Адмін додає друзів, які теж\n"
        f"можуть додавати та видаляти фото."
    )
    await q.message.edit_text(text, reply_markup=kb_back())
    await q.answer()


# ══════════════════ PHOTO MENU ══════════════════

@router.callback_query(F.data == "m:ph")
async def cb_photos_menu(q: CallbackQuery):
    if not await is_authorized(q.from_user.id):
        await q.answer("⛔️ Немає доступу", show_alert=True)
        return
    total = await count_photos()
    text = (
        f"<b>📸 Фото</b>  ·  {total} шт.\n"
        f"{'─' * 30}\n\n"
        f"💡 Щоб <b>додати</b> нове фото —\n"
        f"просто надішли картинку сюди в чат\n"
        f"(можна з підписом для пошуку)"
    )
    await q.message.edit_text(text, reply_markup=kb_photos_menu())
    await q.answer()


@router.callback_query(F.data.startswith("pl:"))
async def cb_photo_list(q: CallbackQuery):
    if not await is_authorized(q.from_user.id):
        await q.answer("⛔️ Немає доступу", show_alert=True)
        return
    page = int(q.data.split(":")[1])
    text, kb = await render_photo_list(page)
    try:
        await q.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await q.answer()


@router.callback_query(F.data.startswith("pv:"))
async def cb_photo_view(q: CallbackQuery):
    if not await is_authorized(q.from_user.id):
        await q.answer("⛔️ Немає доступу", show_alert=True)
        return
    pid = int(q.data.split(":")[1])
    photo = await get_photo_by_id(pid)
    if not photo:
        await q.answer("❌ Фото не знайдено", show_alert=True)
        return
    cap = f"📸 <b>Фото #{photo['id']}</b>"
    if photo["caption"]:
        cap += f"\n📝 {photo['caption']}"
    await q.message.answer_photo(
        photo=photo["file_id"], caption=cap,
        reply_markup=kb_photo_view(photo["id"])
    )
    await q.answer()


@router.callback_query(F.data.startswith("pd:"))
async def cb_photo_delete_ask(q: CallbackQuery):
    if not await is_authorized(q.from_user.id):
        await q.answer("⛔️ Немає доступу", show_alert=True)
        return
    pid = int(q.data.split(":")[1])
    photo = await get_photo_by_id(pid)
    if not photo:
        await q.answer("❌ Фото вже видалено", show_alert=True)
        return
    cap = photo["caption"] or "без назви"
    text = (
        f"🗑 <b>Видалити фото #{pid}?</b>\n\n"
        f"📝 Підпис: <i>{cap}</i>"
    )
    try:
        await q.message.edit_text(text, reply_markup=kb_confirm_delete_photo(pid))
    except Exception:
        await q.message.answer(text, reply_markup=kb_confirm_delete_photo(pid))
    await q.answer()


@router.callback_query(F.data.startswith("pdc:"))
async def cb_photo_delete_confirm(q: CallbackQuery):
    if not await is_authorized(q.from_user.id):
        await q.answer("⛔️ Немає доступу", show_alert=True)
        return
    pid = int(q.data.split(":")[1])
    deleted = await delete_photo(pid)
    if deleted:
        await q.answer(f"✅ Фото #{pid} видалено!", show_alert=True)
        logger.info(f"Фото #{pid} видалено користувачем {q.from_user.id}")
    else:
        await q.answer("❌ Фото вже було видалено", show_alert=True)
    text, kb = await render_photo_list(0)
    try:
        await q.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass


# ══════════════════ PHOTO RECEPTION ══════════════════

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot, state: FSMContext):
    uid = message.from_user.id
    if not await is_authorized(uid):
        await message.answer(
            f"⛔️ Немає доступу.\n"
            f"🆔 Твій ID: <code>{uid}</code>\n"
            f"Попроси адміністратора додати тебе."
        )
        return
    await state.clear()
    photo = message.photo[-1]
    caption = message.caption or ""
    pid = await add_photo(file_id=photo.file_id, caption=caption, added_by=uid)
    bot_me = await bot.get_me()
    desc = f"\n📝 <i>{caption}</i>" if caption else ""
    await message.answer(
        f"✅ <b>Фото збережено!</b>  #{pid}{desc}\n\n"
        f"Надішли в будь-якому чаті:\n"
        f"<code>@{bot_me.username}</code>",
        reply_markup=kb_main(config.is_admin(uid))
    )
    logger.info(f"Фото #{pid} додано від {uid}, caption: '{caption}'")


@router.message(F.document)
async def handle_document(message: Message):
    if not await is_authorized(message.from_user.id):
        return
    await message.answer(
        "⚠️ Надішли фото <b>як зображення</b> (зі стисненням),\n"
        "а не як файл!",
        reply_markup=kb_back()
    )


# ══════════════════ FRIENDS MENU ══════════════════

@router.callback_query(F.data == "m:fr")
async def cb_friends_menu(q: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = q.from_user.id
    if not await is_authorized(uid):
        await q.answer("⛔️ Немає доступу", show_alert=True)
        return
    text, kb = await render_friends(config.is_admin(uid))
    try:
        await q.message.edit_text(text, reply_markup=kb)
    except Exception:
        await q.message.answer(text, reply_markup=kb)
    await q.answer()


@router.callback_query(F.data == "fa")
async def cb_friend_add(q: CallbackQuery, state: FSMContext):
    if not config.is_admin(q.from_user.id):
        await q.answer("⛔️ Тільки адмін", show_alert=True)
        return
    await state.set_state(AddFriendState.waiting)
    await q.message.edit_text(
        f"<b>➕ Додати друга</b>\n"
        f"{'─' * 30}\n\n"
        f"Надішли мені одне з:\n\n"
        f"  1️⃣ <b>Перешли</b> повідомлення від друга\n"
        f"  2️⃣ Напиши його <b>числовий ID</b>\n\n"
        f"<i>Друг може дізнатися свій ID,\n"
        f"написавши /start цьому боту</i>",
        reply_markup=kb_cancel()
    )
    await q.answer()


@router.message(AddFriendState.waiting, F.text)
async def handle_friend_text(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        await state.clear()
        return
    text = message.text.strip()
    if not text.isdigit():
        await message.answer(
            "❌ Це не схоже на ID.\n\n"
            "Надішли <b>числовий ID</b> друга\n"
            "або <b>перешли</b> його повідомлення.",
            reply_markup=kb_cancel()
        )
        return
    friend_id = int(text)
    await _do_add_friend(message, state, friend_id, "", "")


@router.message(AddFriendState.waiting, F.forward_from)
async def handle_friend_forward(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        await state.clear()
        return
    fwd = message.forward_from
    await _do_add_friend(message, state, fwd.id, fwd.username or "", fwd.first_name or "")


@router.message(AddFriendState.waiting)
async def handle_friend_other(message: Message, state: FSMContext):
    """Якщо друг приховав пересилання або надіслано щось інше."""
    if not config.is_admin(message.from_user.id):
        await state.clear()
        return
    await message.answer(
        "❌ Не вдалося отримати ID.\n\n"
        "Можливо, у друга ввімкнена приватність\n"
        "пересиланих повідомлень.\n\n"
        "Попроси його написати /start цьому боту\n"
        "і надіслати тобі свій <b>числовий ID</b>.",
        reply_markup=kb_cancel()
    )


async def _do_add_friend(message: Message, state: FSMContext,
                          friend_id: int, username: str, first_name: str):
    admin_id = message.from_user.id
    if config.is_admin(friend_id):
        await message.answer("ℹ️ Це адміністратор — додавати не потрібно!",
                             reply_markup=kb_back("m:fr"))
        await state.clear()
        return
    added = await add_friend(friend_id, username, first_name, admin_id)
    await state.clear()
    name = first_name or username or str(friend_id)
    if added:
        logger.info(f"Друг {friend_id} ({name}) доданий адміном {admin_id}")
        await message.answer(
            f"✅ <b>{name}</b> доданий як друг!\n"
            f"ID: <code>{friend_id}</code>\n\n"
            f"Тепер він може додавати\n"
            f"та видаляти фото 📸",
            reply_markup=kb_back("m:fr")
        )
    else:
        await message.answer(
            f"ℹ️ <b>{name}</b> вже є другом!",
            reply_markup=kb_back("m:fr")
        )


@router.callback_query(F.data.startswith("fd:"))
async def cb_friend_delete_ask(q: CallbackQuery):
    if not config.is_admin(q.from_user.id):
        await q.answer("⛔️ Тільки адмін", show_alert=True)
        return
    fuid = int(q.data.split(":")[1])
    friend = await get_friend(fuid)
    if not friend:
        await q.answer("❌ Друга не знайдено", show_alert=True)
        return
    name = friend["first_name"] or friend["username"] or str(fuid)
    await q.message.edit_text(
        f"❌ <b>Видалити друга?</b>\n\n"
        f"👤 <b>{name}</b>\n"
        f"ID: <code>{fuid}</code>",
        reply_markup=kb_confirm_delete_friend(fuid)
    )
    await q.answer()


@router.callback_query(F.data.startswith("fdc:"))
async def cb_friend_delete_confirm(q: CallbackQuery, state: FSMContext):
    if not config.is_admin(q.from_user.id):
        await q.answer("⛔️ Тільки адмін", show_alert=True)
        return
    fuid = int(q.data.split(":")[1])
    removed = await remove_friend(fuid)
    if removed:
        await q.answer("✅ Друга видалено!", show_alert=True)
        logger.info(f"Друг {fuid} видалений адміном {q.from_user.id}")
    else:
        await q.answer("❌ Друга вже видалено", show_alert=True)
    text, kb = await render_friends(True)
    try:
        await q.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass


# ══════════════════ INLINE QUERY ══════════════════

@router.inline_query()
async def handle_inline(iq: InlineQuery):
    query_text = iq.query.strip()
    photos = await get_photos(query=query_text, limit=50)

    if not photos:
        msg = "🔍 Нічого не знайдено" if query_text else "📭 Колекція порожня"
        results = [
            InlineQueryResultArticle(
                id="empty", title="Немає фото",
                description=msg,
                input_message_content=InputTextMessageContent(
                    message_text=f"💡 <i>{msg}</i>", parse_mode=ParseMode.HTML
                )
            )
        ]
        await iq.answer(results=results, cache_time=config.CACHE_TIME, is_personal=True)
        return

    results = []
    for p in photos:
        cap = p["caption"] if p["caption"] else None
        results.append(
            InlineQueryResultCachedPhoto(
                id=str(p["id"]),
                photo_file_id=p["file_id"],
                title=cap or f"Фото #{p['id']}",
                description=cap,
                caption=cap,
                parse_mode=ParseMode.HTML if cap else None,
            )
        )
    await iq.answer(results=results, cache_time=config.CACHE_TIME, is_personal=True)


# ══════════════════ MAIN ══════════════════

async def main():
    if not config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не задано! Заповни .env файл.")
        return

    await init_db()
    logger.info("БД ініціалізовано.")

    bot = Bot(token=config.BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    bot_me = await bot.get_me()
    logger.info(f"Бот @{bot_me.username} запущено!")
    if config.ADMIN_IDS:
        logger.info(f"Адміни: {list(config.ADMIN_IDS)}")

    # Health-check веб-сервер для хостингу (Render / Koyeb)
    port = int(os.getenv("PORT", "0"))
    if port:
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text="OK - MaximPhotoBot is running!"))
        app.router.add_get("/health", lambda r: web.Response(text="OK"))
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        logger.info(f"Health-check сервер на порту {port}")

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинено.")
