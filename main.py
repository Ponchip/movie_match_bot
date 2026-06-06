import os
import logging
import asyncio
import random
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from dotenv import load_dotenv
from aiohttp import web

import database as db
import tmdb_client

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Используем movie_cache вместо user_state для избежания конфликта с FSM
movie_cache = {}

GENRES = {
    28: "Боевик", 12: "Приключения", 16: "Мультфильм", 35: "Комедия",
    80: "Криминал", 18: "Драма", 14: "Фэнтези", 27: "Ужасы",
    9648: "Детектив", 10749: "Мелодрама", 878: "Фантастика", 53: "Триллер"
}

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎬 Свайпать"), KeyboardButton(text="🎭 Жанры")],
        [KeyboardButton(text="🔥 Совпадения"), KeyboardButton(text="👥 Пригласить")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="❓ Помощь")]
    ],
    resize_keyboard=True
)

def get_swipe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👎 Пропустить", callback_data="swipe_left"),
         InlineKeyboardButton(text="👍 Нравится", callback_data="swipe_right")]
    ])

def get_genres_keyboard() -> InlineKeyboardMarkup:
    keyboard, row = [], []
    for genre_id, genre_name in GENRES.items():
        row.append(InlineKeyboardButton(text=genre_name, callback_data=f"genre_{genre_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_next_movie(target):
    user_id = target.from_user.id
    chat_id = target.chat.id
    try:
        shown_ids = await db.get_shown_tmdb_ids(user_id)
        user_genres = await db.get_user_genres(user_id)
        genre_ids = [g[0] for g in user_genres] if user_genres else None
        
        movie = await tmdb_client.get_next_movie(exclude_tmdb_ids=shown_ids, genre_ids=genre_ids)
        if not movie:
            await bot.send_message(chat_id, "❌ Фильмы закончились. Выбери другие жанры (/genres).")
            return
        
        movie_id = await db.save_movie(movie)
        await db.mark_movie_shown(user_id, movie_id)
        
        movie_cache[user_id] = {
            "tmdb_id": movie['tmdb_id'], 
            "movie_id": movie_id, 
            "movie": movie
        }
        
        movie_text = (
            f"🎬 **{movie['title']}** ({movie['year']})\n"
            f"⭐ Рейтинг: {movie['rating']}\n\n"
            f"_{movie['description'][:200]}..._"
        )
        
        if movie['poster_url']:
            await bot.send_photo(chat_id, movie['poster_url'], caption=movie_text,
                                 parse_mode="Markdown", reply_markup=get_swipe_keyboard())
        else:
            await bot.send_message(chat_id, movie_text, parse_mode="Markdown",
                                   reply_markup=get_swipe_keyboard())
    except Exception as e:
        logging.error(f"Ошибка загрузки фильма: {e}")
        await bot.send_message(chat_id, "❌ Ошибка загрузки. Попробуй позже.")

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    
    args = message.text.split()
    ref_info = ""
    inviter_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            inviter_id = int(args[1].replace("ref_", ""))
            if inviter_id != message.from_user.id:
                await db.save_invitation(inviter_id, message.from_user.id)
                inviter_name = await db.get_username_by_id(inviter_id)
                ref_info = f"\n\n🎉 Ты пришёл по приглашению от {inviter_name}!"
        except ValueError:
            pass
    
    welcome_text = (
        f"👋 Привет, {message.from_user.full_name}!{ref_info}\n\n"
        f"Я помогу тебе и друзьям найти идеальный фильм за 2 минуты.\n\n"
        f"👇 Пользуйся кнопками ниже или командами:"
    )
    await message.answer(welcome_text, reply_markup=MAIN_KEYBOARD)
    
    if inviter_id:
        await show_matches(message.from_user.id, message.chat.id)
    else:
        await send_next_movie(message)

@dp.message(Command("genres"))
async def cmd_genres(message: Message):
    await message.answer("🎭 Выбери любимые жанры (можно несколько):", reply_markup=get_genres_keyboard())

@dp.message(Command("matches"))
async def cmd_matches(message: Message):
    await show_matches(message.from_user.id, message.chat.id)

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = await db.get_user_stats(message.from_user.id)
    friends = await db.get_friends(message.from_user.id)
    genres = await db.get_user_genres(message.from_user.id)
    text = (
        f"📊 **Твоя статистика**\n\n"
        f"❤️ Лайков: {stats['like']}\n"
        f"👎 Пропущено: {stats['dislike']}\n"
        f"👥 Друзей: {len(friends)}\n"
        f"🎭 Жанров выбрано: {len(genres)}"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("history"))
async def cmd_history(message: Message):
    history = await db.get_user_history(message.from_user.id, limit=10)
    if not history:
        await message.answer("📜 История пуста. Начни свайпать! 🎬")
        return
    text = "📜 **Последние 10 фильмов:**\n\n"
    for title, year, poster, swipe_type, created_at in history:
        emoji = "❤️" if swipe_type == "like" else "👎"
        text += f"{emoji} **{title}** ({year})\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("random"))
async def cmd_random(message: Message):
    likes = await db.get_user_likes(message.from_user.id)
    if not likes:
        await message.answer("❤️ Сначала лайкни несколько фильмов!")
        return
    tmdb_id, title, year, poster = random.choice(likes)
    text = f"🎲 **Случайный фильм из твоих лайков:**\n\n🎬 {title} ({year})"
    if poster:
        await message.answer_photo(poster, caption=text, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "❓ **Как пользоваться ботом:**\n\n"
        "🎬 **Свайпать** — получать новый фильм\n"
        "🎭 **Жанры** — выбрать любимые жанры\n"
        "🔥 **Совпадения** — что вы лайкнули с другом\n"
        "👥 **Пригласить** — отправить ссылку другу\n"
        "📊 **Статистика** — сколько фильмов оценил\n\n"
        "Дополнительные команды:\n"
        "📜 /history — история свайпов\n"
        "🎲 /random — случайный из лайкнутых\n\n"
        "💡 Пригласи друга и сравнивайте вкусы!"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(lambda m: m.text == "🎬 Свайпать")
async def btn_swipe(message: Message):
    await send_next_movie(message)

@dp.message(lambda m: m.text == "🎭 Жанры")
async def btn_genres(message: Message):
    await cmd_genres(message)

@dp.message(lambda m: m.text == "🔥 Совпадения")
async def btn_matches(message: Message):
    await show_matches(message.from_user.id, message.chat.id)

@dp.message(lambda m: m.text == "👥 Пригласить")
async def btn_invite(message: Message):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    text = (
        f"🔗 **Твоя ссылка-приглашение:**\n\n`{link}`\n\n"
        f"Отправь её другу. Когда он начнёт свайпать — "
        f"вы сможете сравнивать вкусы! 🔥"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(lambda m: m.text == "📊 Статистика")
async def btn_stats(message: Message):
    await cmd_stats(message)

@dp.message(lambda m: m.text == "❓ Помощь")
async def btn_help(message: Message):
    await cmd_help(message)

@dp.callback_query(lambda c: c.data.startswith("genre_"))
async def process_genre(callback: CallbackQuery):
    genre_id = int(callback.data.replace("genre_", ""))
    genre_name = GENRES.get(genre_id, "Неизвестный")
    await db.save_user_genre(callback.from_user.id, genre_id, genre_name)
    await callback.answer(f"✅ {genre_name} добавлен!", show_alert=True)
    await callback.message.answer(
        f"🎭 Жанр **{genre_name}** добавлен!\n"
        f"Теперь будет больше фильмов в этом жанре. "
        f"Нажми 🎬 Свайпать, чтобы продолжить.",
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data in ['swipe_left', 'swipe_right'])
async def process_swipe(callback: CallbackQuery):
    user_id = callback.from_user.id
    state = movie_cache.get(user_id)
    
    if not state:
        await callback.answer("⏳ Нажми 🎬 Свайпать", show_alert=True)
        return
    
    movie_id = state['movie_id']
    tmdb_id = state['tmdb_id']
    
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    if callback.data == 'swipe_left':
        await db.save_swipe(user_id, movie_id, "dislike")
        await callback.answer("Пропущено ❌")
    else:
        await db.save_swipe(user_id, movie_id, "like")
        friends = await db.get_friends(user_id)
        matched_friend = None
        for friend_id in friends:
            mutual = await db.get_mutual_likes(user_id, friend_id)
            if any(m[0] == tmdb_id for m in mutual):
                matched_friend = friend_id
                break
        if matched_friend:
            friend_name = await db.get_username_by_id(matched_friend)
            await callback.answer(f"🔥 МЭТЧ! {friend_name} тоже лайкнул!", show_alert=True)
            await callback.message.answer(
                f"🔥 **МЭТЧ!**\n\nТы и {friend_name} оба лайкнули этот фильм! "
                f"Отличный выбор для совместного просмотра 🍿",
                parse_mode="Markdown"
            )
        else:
            await callback.answer("Добавлено в избранное ❤️")
    
    if user_id in movie_cache:
        del movie_cache[user_id]
    await send_next_movie(callback.message)

async def show_matches(user_id: int, chat_id: int):
    friends = await db.get_friends(user_id)
    if not friends:
        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        text = (
            f"👥 **У тебя пока нет друзей в боте.**\n\n"
            f"Отправь эту ссылку другу:\n`{link}`\n\n"
            f"Когда он начнёт свайпать — вы сможете сравнивать вкусы! 🔥"
        )
        await bot.send_message(chat_id, text, parse_mode="Markdown")
        return
    
    total_mutual = 0
    full_text = "🔥 **Твои совпадения с друзьями:**\n\n"
    for friend_id in friends:
        friend_name = await db.get_username_by_id(friend_id)
        mutual = await db.get_mutual_likes(user_id, friend_id)
        if mutual:
            total_mutual += len(mutual)
            full_text += f"👤 **{friend_name}** — {len(mutual)} совпадений:\n"
            for tmdb_id, title, year, poster, rating in mutual[:5]:
                full_text += f"  🎬 {title} ({year}) ⭐{rating}\n"
            if len(mutual) > 5:
                full_text += f"  ... и ещё {len(mutual) - 5}\n"
            full_text += "\n"
    
    if total_mutual == 0:
        full_text += "😔 Пока нет совпадений. Свайпайте больше!"
    
    await bot.send_message(chat_id, full_text, parse_mode="Markdown")

async def health_check(request):
    return web.Response(text="OK")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"🌐 Health check сервер запущен на порту {port}")

async def main():
    await db.init_db()
    await run_web_server()
    bot_info = await bot.get_me()
    print(f"🚀 Бот @{bot_info.username} запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())