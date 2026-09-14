import asyncio
import logging
import os
import sys
from typing import Optional

# Настройка UTF-8 для Windows-консоли (поддержка эмодзи и кириллицы)
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
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
    add_photo,
    count_photos,
    delete_photo,
    get_photo_by_id,
    get_photos,
    init_db,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MaximPhotoBot")

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    """Приветственное сообщение и базовая инструкция."""
    bot_info = await bot.get_me()
    text = (
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"Этот бот позволяет моментально отправлять твои сохранённые фото в любых чатах через инлайн-режим.\n\n"
        f"<b>Как это работает:</b>\n"
        f"1. 📸 Просто <b>скинь мне фото сюда в ЛС</b> (можно с подписью-описанием).\n"
        f"2. 💬 В любом диалоге или группе начни писать: <code>@{bot_info.username}</code>\n"
        f"3. 🖼 Появится меню с твоими картинками — нажимай на любую, и она мгновенно отправится другу!\n\n"
        f"<b>Поиск по фото:</b>\n"
        f"Если добавить фото с подписью (например, <i>мем с котом</i>), то при вызове "
        f"<code>@{bot_info.username} кот</code> найдутся именно подходящие фото.\n\n"
        f"<b>Доступные команды:</b>\n"
        f"• /list — просмотр и удаление сохранённых фото\n"
        f"• /count — количество сохранённых фото\n"
        f"• /myid — узнать свой Telegram ID (для настройки доступа в .env)"
    )
    await message.answer(text)


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    """Показывает пользователю его Telegram ID."""
    user_id = message.from_user.id
    is_adm = config.is_admin(user_id)
    status = "👑 Администратор" if is_adm else "👤 Обычный пользователь"
    await message.answer(
        f"Ваш Telegram ID: <code>{user_id}</code>\n"
        f"Статус доступа: {status}\n\n"
        f"<i>Укажите этот ID в файле <code>.env</code> в строке <code>ADMIN_ID={user_id}</code>, "
        f"чтобы только вы могли управлять коллекцией фото.</i>"
    )


@router.message(Command("count"))
async def cmd_count(message: Message):
    """Показывает общее количество фото в базе."""
    total = await count_photos()
    await message.answer(f"📊 В базе сейчас сохранено фото: <b>{total}</b>")


@router.message(F.photo)
async def handle_incoming_photo(message: Message, bot: Bot):
    """Обработка входящих фотографий для сохранения в базу."""
    user_id = message.from_user.id
    logger.info(f"Получено фото от пользователя ID: {user_id}")

    if not config.is_admin(user_id):
        logger.warning(f"Пользователь {user_id} не админ. Доступ запрещен.")
        await message.answer(
            "⛔️ У вас нет прав для добавления фотографий в эту подборку.\n"
            "Добавлять фото может только владелец бота (администратор)."
        )
        return

    # Берем вариант фото с максимальным разрешением
    photo = message.photo[-1]
    file_id = photo.file_id
    caption = message.caption or ""

    photo_id = await add_photo(file_id=file_id, caption=caption)
    logger.info(f"Фото успешно сохранено в базу! ID: {photo_id}, caption: '{caption}'")
    bot_info = await bot.get_me()

    desc_text = f"\nПодпись: <i>{caption}</i>" if caption else " (без подписи)"
    await message.answer(
        f"✅ <b>Фото успешно сохранено!</b> [ID: #{photo_id}]{desc_text}\n\n"
        f"Теперь ты можешь отправить его в любом чате:\n"
        f"Напиши <code>@{bot_info.username}</code> и выбери картинку!"
    )


@router.message(F.document)
async def handle_document(message: Message):
    """Предупреждение, если фото отправлено как файл без сжатия."""
    await message.answer(
        "⚠️ Вы отправили файл как документ.\n\n"
        "Чтобы фотографию можно было отправлять в инлайн-режиме, отправьте её "
        "<b>как фотографию (сжатое изображение)</b>, а не как файл!"
    )



@router.message(Command("list"))
async def cmd_list(message: Message):
    """Выводит список последних фото с кнопками для удаления."""
    user_id = message.from_user.id
    if not config.is_admin(user_id):
        await message.answer("⛔️ Эта команда доступна только администратору.")
        return

    photos = await get_photos(limit=20)
    if not photos:
        await message.answer(
            "📭 У вас пока нет сохранённых фото.\n"
            "Отправьте мне картинку в ЛС, чтобы добавить!"
        )
        return

    text = "<b>📸 Список последних сохранённых фото:</b>\n\n"
    keyboard_buttons = []

    for p in photos:
        pid = p["id"]
        cap = p["caption"] if p["caption"] else "без названия"
        # Обрезаем длинные подписи для читаемости
        if len(cap) > 25:
            cap = cap[:22] + "..."
        text += f"• <b>#{pid}</b>: {cap}\n"
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"👁 Показать #{pid}", callback_data=f"view:{pid}"),
            InlineKeyboardButton(text=f"🗑 Удалить #{pid}", callback_data=f"del:{pid}")
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("view:"))
async def cb_view_photo(query: CallbackQuery):
    """Показывает превью фото по ID."""
    try:
        photo_id = int(query.data.split(":")[1])
        photo = await get_photo_by_id(photo_id)
        if not photo:
            await query.answer("❌ Фото не найдено или уже удалено.", show_alert=True)
            return

        caption = f"Фото #{photo['id']}"
        if photo["caption"]:
            caption += f"\nПодпись: {photo['caption']}"

        del_kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🗑 Удалить это фото", callback_data=f"del:{photo['id']}")
            ]]
        )
        await query.message.answer_photo(
            photo=photo["file_id"],
            caption=caption,
            reply_markup=del_kb
        )
        await query.answer()
    except Exception as e:
        logger.error(f"Ошибка при показе фото: {e}")
        await query.answer("Ошибка при отображении фото.")


@router.callback_query(F.data.startswith("del:"))
async def cb_delete_photo(query: CallbackQuery):
    """Удаляет фото по ID из базы."""
    user_id = query.from_user.id
    if not config.is_admin(user_id):
        await query.answer("⛔️ Только администратор может удалять фото.", show_alert=True)
        return

    try:
        photo_id = int(query.data.split(":")[1])
        deleted = await delete_photo(photo_id)
        if deleted:
            await query.answer(f"✅ Фото #{photo_id} удалено!", show_alert=True)
            # Если сообщение было текстом со списком, обновляем список
            if query.message.text and "Список последних" in query.message.text:
                photos = await get_photos(limit=20)
                if not photos:
                    await query.message.edit_text("📭 Все сохранённые фото удалены.")
                    return
                text = "<b>📸 Список последних сохранённых фото:</b>\n\n"
                keyboard_buttons = []
                for p in photos:
                    pid = p["id"]
                    cap = p["caption"] if p["caption"] else "без названия"
                    if len(cap) > 25:
                        cap = cap[:22] + "..."
                    text += f"• <b>#{pid}</b>: {cap}\n"
                    keyboard_buttons.append([
                        InlineKeyboardButton(text=f"👁 Показать #{pid}", callback_data=f"view:{pid}"),
                        InlineKeyboardButton(text=f"🗑 Удалить #{pid}", callback_data=f"del:{pid}")
                    ])
                keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                await query.message.edit_text(text, reply_markup=keyboard)
            elif query.message.photo:
                # Если удалили через превью фото
                await query.message.delete()
        else:
            await query.answer("Фото уже было удалено.", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при удалении фото: {e}")
        await query.answer("Произошла ошибка при удалении.")


@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery):
    """
    Обработка инлайн-запросов (@username_бота [текст_поиска]).
    Возвращает список сохранённых фото через InlineQueryResultCachedPhoto.
    """
    query_text = inline_query.query.strip()
    photos = await get_photos(query=query_text, limit=50)

    if not photos:
        # Если фото нет в базе или поиск ничего не нашел
        msg_text = (
            "🔍 Фото не найдены."
            if query_text
            else "📭 В боте пока нет фото. Отправь фото боту в ЛС, чтобы добавить!"
        )
        results = [
            InlineQueryResultArticle(
                id="empty_info",
                title="Нет фото для отправки",
                description=msg_text,
                input_message_content=InputTextMessageContent(
                    message_text=f"💡 <i>{msg_text}</i>",
                    parse_mode=ParseMode.HTML
                )
            )
        ]
        await inline_query.answer(
            results=results,
            cache_time=config.CACHE_TIME,
            is_personal=True
        )
        return

    results = []
    for p in photos:
        cap = p["caption"] if p["caption"] else None
        results.append(
            InlineQueryResultCachedPhoto(
                id=str(p["id"]),
                photo_file_id=p["file_id"],
                title=cap or f"Фото #{p['id']}",
                description=cap if cap else None,
                caption=cap,
                parse_mode=ParseMode.HTML if cap else None
            )
        )

    await inline_query.answer(
        results=results,
        cache_time=config.CACHE_TIME,
        is_personal=True
    )


async def main():
    """Точка входа запуска бота."""
    if not config.BOT_TOKEN:
        logger.error(
            "❌ ОШИБКА: BOT_TOKEN не задан! "
            "Создайте файл .env на основе .env.example и укажите токен бота от @BotFather."
        )
        return

    # Инициализация базы данных
    await init_db()
    logger.info("База данных SQLite инициализирована.")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(router)

    bot_me = await bot.get_me()
    logger.info(f"Бот @{bot_me.username} успешно запущен!")
    logger.info(f"Режим кэша инлайна: {config.CACHE_TIME} сек.")
    if config.ADMIN_IDS:
        logger.info(f"Администраторы бота: {list(config.ADMIN_IDS)}")
    else:
        logger.warning(
            "⚠️ ADMIN_ID не настроен! Любой пользователь сможет добавлять фото. "
            "Настоятельно рекомендуется указать свой ID в .env!"
        )

    # Запуск веб-сервера для облачных платформ (Render, Koyeb и др.)
    port = int(os.getenv("PORT", "0"))
    if port:
        from aiohttp import web
        async def ping_handler(request):
            return web.Response(text="OK - MaximPhotoBot is running!")
        app = web.Application()
        app.router.add_get("/", ping_handler)
        app.router.add_get("/health", ping_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Веб-сервер проверки статуса запущен на порту {port}")

    # Запуск поллинга (drop_pending_updates=False, чтобы получить отправленные ранее сообщения)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
