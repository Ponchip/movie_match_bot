import aiosqlite
import os
from datetime import datetime

DB_NAME = "movie_match.db"

async def init_db():
    """Создает таблицы при первом запуске"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TEXT
            )
        """)
        
        # Таблица фильмов (кэш из TMDB)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY,
                tmdb_id INTEGER UNIQUE,
                title TEXT,
                year INTEGER,
                rating REAL,
                poster_url TEXT,
                description TEXT
            )
        """)
        
        # Таблица свайпов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS swipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                movie_id INTEGER,
                swipe_type TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (movie_id) REFERENCES movies(id)
            )
        """)
        
        # Таблица приглашений (кто кого пригласил)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invitee_id INTEGER,
                created_at TEXT
            )
        """)
        
        await db.commit()
        print("✅ База данных инициализирована")

async def add_user(user_id: int, username: str):
    """Добавляет пользователя в БД"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username, created_at) VALUES (?, ?, ?)",
            (user_id, username, datetime.now().isoformat())
        )
        await db.commit()

async def save_movie(movie_data: dict) -> int:
    """Сохраняет фильм в кэш и возвращает его ID"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """INSERT OR IGNORE INTO movies 
               (tmdb_id, title, year, rating, poster_url, description) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                movie_data['tmdb_id'],
                movie_data['title'],
                movie_data['year'],
                movie_data['rating'],
                movie_data['poster_url'],
                movie_data['description']
            )
        )
        await db.commit()
        
        # Получаем ID фильма
        cursor = await db.execute(
            "SELECT id FROM movies WHERE tmdb_id = ?",
            (movie_data['tmdb_id'],)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

async def save_swipe(user_id: int, movie_id: int, swipe_type: str):
    """Сохраняет свайп (like/dislike)"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO swipes (user_id, movie_id, swipe_type, created_at) VALUES (?, ?, ?, ?)",
            (user_id, movie_id, swipe_type, datetime.now().isoformat())
        )
        await db.commit()

async def get_user_swipes(user_id: int):
    """Получает все свайпы пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """SELECT m.title, m.year, s.swipe_type 
               FROM swipes s 
               JOIN movies m ON s.movie_id = m.id 
               WHERE s.user_id = ?""",
            (user_id,)
        )
        return await cursor.fetchall()

async def save_invitation(inviter_id: int, invitee_id: int):
    """Сохраняет факт приглашения"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO invitations (inviter_id, invitee_id, created_at) VALUES (?, ?, ?)",
            (inviter_id, invitee_id, datetime.now().isoformat())
        )
        await db.commit()