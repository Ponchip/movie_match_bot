import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from aiohttp import web

import database as db
import tmdb_client

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_current_movie = {}

GENRES = {
    28: "Боевик", 12: "Приключения", 16: "Мультфильм", 35: "Комедия",
    80: "Криминал", 18: "Драма", 14: "Фэнтези", 27: "Ужасы",
    9648: "Детектив", 10749: "Мелодрама", 878: "Фантастика", 53: "Триллер"
}

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    
    args = message.text.split()
    ref_info = ""
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            inviter_id = int(args[1].replace("ref_", ""))
            await db.save_invitation(inviter_id, message.from_user.id)
            ref_info = " (ты пришел по приглашению друга! 🎉)"
        except ValueError:
            pass
    
    welcome_text = (
        f"👋 Привет, {message.from_user.full_name}{ref_info}!\n\n"
        f"Устали тратить по часу на споры, какой фильм включить?\n"
        f"1. Выбери жанры командой /genres\n"
        f"2. Свайпай фильмы 👍 или 👎\n"
        f"3. Пригласи друга, чтобы найти совпадения!"
    )
    await message.answer(welcome_text)
    await send_next_movie(message)

@dp.message(Command("genres"))
async def cmd_genres(message: types.Message):
    keyboard = []
    row = []
    for i, (genre_id, genre_name) in enumerate(GENRES.items()):
        row.append(InlineKeyboardButton(text=genre_name, callback_data=f"genre_{genre_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    await message.answer("🎭 Выбери любимые жанры (можно несколько):", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@dp.callback_query(lambda c: c.data.startswith("genre_"))
async def process_genre_selection(callback: types.CallbackQuery):
    genre_id = int(callback.data.replace("genre_", ""))
    genre_name = GENRES.get(genre_id, "Неизвестный")
    await db.save_user_genre(callback.from_user.id, genre_id, genre_name)
    await callback.answer(f"✅ {genre_name} добавлен!")
    
    await callback.message.answer(
        f"Отлично! Теперь я буду предлагать фильмы в жанре '{genre_name}'.\n"
        f"Нажми кнопку ниже, чтобы продолжить свайпать.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Продолжить свайпать", callback_data="start_swiping")]
        ])
    )

@dp.callback_query(lambda c: c.data == "start_swiping")
async def start_swiping(callback: types.CallbackQuery):
    await callback.message.delete()
    await send_next_movie(callback.message)

async def send_next_movie(message: types.Message):
    try:
        user_id = message.from_user.id
        shown_ids = await db.get_shown_movie_ids(user_id)
        user_genres = await db.get_user_genres(user_id)
        genre_ids = [g[0] for g in user_genres] if user_genres else None
        
        movie = await tmdb_client.get_next_movie(exclude_ids=shown_ids, genre_ids=genre_ids)
        if not movie:
            await message.answer("❌ Фильмы закончились или не удалось загрузить. Попробуй позже или измени жанры (/genres).")
            return
        
        movie_id = await db.save_movie(movie)
        await db.mark_movie_shown(user_id, movie_id)
        user_current_movie[user_id] = movie_id
        
        movie_text = f"🎬 **{movie['title']}** ({movie['year']})\n⭐ Рейтинг: {movie['rating']}\n\n_{movie['description'][:200]}..._"
        
        if movie['poster_url']:
            await message.answer_photo(photo=movie['poster_url'], caption=movie_text, parse_mode="Markdown", reply_markup=get_swipe_keyboard())
        else:
            await message.answer(movie_text, parse_mode="Markdown", reply_markup=get_swipe_keyboard())
    except Exception as e:
        logging.error(f"Ошибка загрузки фильма: {e}")
        await message.answer("❌ Ошибка загрузки. Попробуй позже.")

def get_swipe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👎 Пропустить", callback_data="swipe_left"),
         InlineKeyboardButton(text="👍 Нравится", callback_data="swipe_right")],
        [InlineKeyboardButton(text="👥 Проверить совпадения с другом", callback_data="check_matches")]
    ])

@dp.callback_query(lambda c: c.data in ['swipe_left', 'swipe_right', 'check_matches'])
async def process_swipe(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        movie_id = user_current_movie.get(user_id)
        
        if callback.data == 'swipe_left':
            await callback.answer("Пропущено ❌")
            if movie_id: await db.save_swipe(user_id, movie_id, "dislike")
            await callback.message.delete()
            await send_next_movie(callback.message)
            
        elif callback.data == 'swipe_right':
            await callback.answer("Добавлено в избранное ❤️")
            if movie_id: await db.save_swipe(user_id, movie_id, "like")
            await callback.message.delete()
            await send_next_movie(callback.message)
            
        elif callback.data == 'check_matches':
            bot_info = await bot.get_me()
            invite_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
            await callback.message.answer(
                f"🔗 Отправь эту ссылку другу:\n\n`{invite_link}`\n\n"
                f"Когда он тоже поставит 👍 этому фильму, вы получите мэтч! 🔥",
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"Ошибка свайпа: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

# Health check для Render.com
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
    
    # Получаем информацию о боте (нужно для username)
    global bot
    bot_info = await bot.get_me()
    print(f"✅ Бот @{bot_info.username} запущен!")
    
    await run_web_server()
    await dp.start_polling(bot)
    