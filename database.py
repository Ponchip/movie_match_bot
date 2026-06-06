import aiosqlite
from datetime import datetime

DB_NAME = "movie_match.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT, created_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY, tmdb_id INTEGER UNIQUE, title TEXT, 
            year INTEGER, rating REAL, poster_url TEXT, description TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS swipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            movie_id INTEGER, swipe_type TEXT, created_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, inviter_id INTEGER, 
            invitee_id INTEGER, created_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS shown_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            movie_id INTEGER, shown_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            genre_id INTEGER, genre_name TEXT)""")
        await db.commit()

async def add_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username, created_at) VALUES (?, ?, ?)",
            (user_id, username or "unknown", datetime.now().isoformat())
        )
        await db.commit()

async def save_movie(movie_data: dict) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT OR IGNORE INTO movies 
            (tmdb_id, title, year, rating, poster_url, description) VALUES (?, ?, ?, ?, ?, ?)""",
            (movie_data['tmdb_id'], movie_data['title'], movie_data.get('year'), 
             movie_data.get('rating', 0), movie_data.get('poster_url'), movie_data.get('description', '')))
        await db.commit()
        cursor = await db.execute("SELECT id FROM movies WHERE tmdb_id = ?", (movie_data['tmdb_id'],))
        row = await cursor.fetchone()
        return row[0] if row else None

async def save_swipe(user_id: int, movie_id: int, swipe_type: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO swipes (user_id, movie_id, swipe_type, created_at) VALUES (?, ?, ?, ?)",
            (user_id, movie_id, swipe_type, datetime.now().isoformat())
        )
        await db.commit()

async def mark_movie_shown(user_id: int, movie_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO shown_movies (user_id, movie_id, shown_at) VALUES (?, ?, ?)",
            (user_id, movie_id, datetime.now().isoformat())
        )
        await db.commit()

async def get_shown_tmdb_ids(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT m.tmdb_id FROM shown_movies s
            JOIN movies m ON s.movie_id = m.id
            WHERE s.user_id = ?
        """, (user_id,))
        return [row[0] for row in await cursor.fetchall()]

async def save_user_genre(user_id: int, genre_id: int, genre_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id FROM user_genres WHERE user_id = ? AND genre_id = ?", 
            (user_id, genre_id)
        )
        if await cursor.fetchone():
            return
        await db.execute(
            "INSERT INTO user_genres (user_id, genre_id, genre_name) VALUES (?, ?, ?)",
            (user_id, genre_id, genre_name)
        )
        await db.commit()

async def get_user_genres(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT genre_id, genre_name FROM user_genres WHERE user_id = ?", 
            (user_id,)
        )
        return await cursor.fetchall()

async def save_invitation(inviter_id: int, invitee_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id FROM invitations WHERE inviter_id = ? AND invitee_id = ?", 
            (inviter_id, invitee_id)
        )
        if await cursor.fetchone():
            return
        await db.execute(
            "INSERT INTO invitations (inviter_id, invitee_id, created_at) VALUES (?, ?, ?)",
            (inviter_id, invitee_id, datetime.now().isoformat())
        )
        await db.commit()

async def get_friends(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT DISTINCT 
                CASE WHEN inviter_id = ? THEN invitee_id ELSE inviter_id END as friend_id
            FROM invitations
            WHERE inviter_id = ? OR invitee_id = ?
        """, (user_id, user_id, user_id))
        return [row[0] for row in await cursor.fetchall()]

async def get_username_by_id(user_id: int) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0]:
            return f"@{row[0]}"
        return f"пользователь {user_id}"

async def get_user_likes(user_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT m.tmdb_id, m.title, m.year, m.poster_url
            FROM swipes s JOIN movies m ON s.movie_id = m.id
            WHERE s.user_id = ? AND s.swipe_type = 'like'
        """, (user_id,))
        return await cursor.fetchall()

async def get_mutual_likes(user_id: int, friend_id: int) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT m.tmdb_id, m.title, m.year, m.poster_url, m.rating
            FROM swipes s1
            JOIN swipes s2 ON s1.movie_id = s2.movie_id
            JOIN movies m ON s1.movie_id = m.id
            WHERE s1.user_id = ? AND s1.swipe_type = 'like'
            AND s2.user_id = ? AND s2.swipe_type = 'like'
        """, (user_id, friend_id))
        return await cursor.fetchall()

async def get_user_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT swipe_type, COUNT(*) FROM swipes 
            WHERE user_id = ? GROUP BY swipe_type
        """, (user_id,))
        stats = {'like': 0, 'dislike': 0}
        for row in await cursor.fetchall():
            stats[row[0]] = row[1]
        return stats

async def get_user_history(user_id: int, limit: int = 10) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT m.title, m.year, m.poster_url, s.swipe_type, s.created_at
            FROM swipes s JOIN movies m ON s.movie_id = m.id
            WHERE s.user_id = ?
            ORDER BY s.created_at DESC LIMIT ?
        """, (user_id, limit))
        return await cursor.fetchall()