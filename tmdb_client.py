import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
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

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    try:
        await db.add_user(message.from_user.id, message.from_user.username)
        
        args = message.text.split()
        ref_info = ""
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                inviter_id = int(args[1].replace("ref_", ""))
                await db.save_invitation(inviter_id, message.from_user.id)
                ref_info = " (ты пришел по приглашению друга!)"
            except ValueError:
                pass
        
        welcome_text = (
            f"👋 Привет, {message.from_user.full_name}{ref_info}!\n\n"
            f"Устали тратить по часу на споры, какой фильм включить?\n"
            f"Я помогу найти идеальный вариант за 2 минуты.\n\n"
            f"👇 Жми на кнопки, чтобы оценивать фильмы. А если вы свайпаете с другом — я покажу ваши совпадения!"
        )
        
        await message.answer(welcome_text)
        await send_next_movie(message)
    except Exception as e:
        logging.error(f"Ошибка в /start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуй позже.")

async def send_next_movie(message: types.Message):
    try:
        movie = await tmdb_client.get_next_movie()
        
        if not movie:
            await message.answer("❌ Не удалось загрузить фильм. Попробуй позже.")
            return
        
        movie_id = await db.save_movie(movie)
        user_current_movie[message.from_user.id] = movie_id
        
        movie_text = (
            f"🎬 **{movie['title']}** ({movie['year']})\n"
            f"⭐ Рейтинг: {movie['rating']}\n\n"
            f"_{movie['description'][:200]}..._"
        )
        
        if movie['poster_url']:
            await message.answer_photo(
                photo=movie['poster_url'],
                caption=movie_text,
                parse_mode="Markdown",
                reply_markup=get_swipe_keyboard()
            )
        else:
            await message.answer(
                movie_text,
                parse_mode="Markdown",
                reply_markup=get_swipe_keyboard()
            )
    except Exception as e:
        logging.error(f"Ошибка загрузки фильма: {e}")
        await message.answer("❌ Не удалось загрузить фильм. Попробуй позже.")

def get_swipe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👎 Пропустить", callback_data="swipe_left"),
            InlineKeyboardButton(text="👍 Нравится", callback_data="swipe_right")
        ],
        [
            InlineKeyboardButton(text="👥 Пригласить друга", callback_data="invite_friend")
        ]
    ])

@dp.callback_query(lambda c: c.data in ['swipe_left', 'swipe_right', 'invite_friend'])
async def process_swipe(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        movie_id = user_current_movie.get(user_id)
        
        if callback.data == 'swipe_left':
            await callback.answer("Пропущено ❌")
            if movie_id:
                await db.save_swipe(user_id, movie_id, "dislike")
            await callback.message.delete()
            await send_next_movie(callback.message)
            
        elif callback.data == 'swipe_right':
            await callback.answer("Добавлено в избранное ❤️")
            if movie_id:
                await db.save_swipe(user_id, movie_id, "like")
            await callback.message.delete()
            await send_next_movie(callback.message)
            
        elif callback.data == 'invite_friend':
            invite_link = f"https://t.me/{bot.username}?start=ref_{user_id}"
            await callback.message.answer(
                f"🔗 Отправь эту ссылку другу/партнеру:\n\n`{invite_link}`\n\n"
                f"Когда он перейдет по ней и тоже поставит ❤️ этому фильму, вы получите мэтч!",
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"Ошибка обработки свайпа: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

# ==== HTTP-сервер для Render.com ====
async def health_check(request):
    return web.Response(text="OK")

async def run_web_server():
    """Запускает простой HTTP-сервер, чтобы Render видел открытый порт"""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render ожидает порт из переменной окружения PORT
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"🌐 Health check сервер запущен на порту {port}")

async def main():
    await db.init_db()
    
    # Запускаем HTTP-сервер параллельно с polling
    await run_web_server()
    
    print("🚀 Бот запущен на Render.com!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())