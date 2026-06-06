import aiosqlite
from datetime import datetime

DB_NAME = "movie_match.db"

async def init_db():
    """Инициализация всех таблиц"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Пользователи
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            created_at TEXT,
            last_active TEXT
        )""")
        
        # Кэш фильмов из TMDB
        await db.execute("""CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id INTEGER UNIQUE,
            title TEXT,
            year INTEGER,
            rating REAL,
            poster_url TEXT,
            description TEXT,
            genres TEXT
        )""")
        
        # Свайпы пользователей
        await db.execute("""CREATE TABLE IF NOT EXISTS swipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tmdb_id INTEGER,
            swipe_type TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")
        
        # Приглашения
        await db.execute("""CREATE TABLE IF NOT EXISTS invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER,
            invitee_id INTEGER,
            created_at TEXT
        )""")
        
        # Показанные фильмы (чтобы не повторять)
        await db.execute("""CREATE TABLE IF NOT EXISTS shown_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tmdb_id INTEGER,
            shown_at TEXT
        )""")
        
        # Жанры пользователей
        await db.execute("""CREATE TABLE IF NOT EXISTS user_genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            genre_id INTEGER,
            genre_name TEXT
        )""")
        
        # Совместные сессии свайпинга
        await db.execute("""CREATE TABLE IF NOT EXISTS match_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_code TEXT UNIQUE,
            creator_id INTEGER,
            partner_id INTEGER,
            created_at TEXT,
            is_active INTEGER DEFAULT 1
        )""")
        
        await db.commit()
        print("✅ База данных инициализирована")

# === Пользователи ===
async def add_user(user_id: int, username: str, full_name: str):
    """Добавляет или обновляет пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT INTO users (id, username, full_name, created_at, last_active) 
                           VALUES (?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET 
                           username=excluded.username, 
                           full_name=excluded.full_name,
                           last_active=excluded.last_active""",
                        (user_id, username, full_name, datetime.now().isoformat(), datetime.now().isoformat()))
        await db.commit()

async def update_user_activity(user_id: int):
    """Обновляет время последней активности"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET last_active = ? WHERE id = ?",
                        (datetime.now().isoformat(), user_id))
        await db.commit()

# === Фильмы ===
async def save_movie(movie_data: dict):
    """Сохраняет фильм в кэш"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT OR IGNORE INTO movies 
                           (tmdb_id, title, year, rating, poster_url, description, genres) 
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (movie_data['tmdb_id'], movie_data['title'], movie_data['year'],
                         movie_data['rating'], movie_data['poster_url'], movie_data['description'],
                         str(movie_data.get('genres', []))))
        await db.commit()

async def get_movie_by_tmdb_id(tmdb_id: int):
    """Получает фильм по tmdb_id"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT tmdb_id, title, year, rating, poster_url, description FROM movies WHERE tmdb_id = ?",
            (tmdb_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                'tmdb_id': row[0],
                'title': row[1],
                'year': row[2],
                'rating': row[3],
                'poster_url': row[4],
                'description': row[5]
            }
        return None

# === Свайпы ===
async def save_swipe(user_id: int, tmdb_id: int, swipe_type: str):
    """Сохраняет свайп"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT INTO swipes (user_id, tmdb_id, swipe_type, created_at) 
                           VALUES (?, ?, ?, ?)""",
                        (user_id, tmdb_id, swipe_type, datetime.now().isoformat()))
        await db.commit()

async def get_user_likes(user_id: int) -> list:
    """Получает все лайки пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""SELECT s.tmdb_id, m.title, m.year, m.rating, m.poster_url
                                    FROM swipes s
                                    JOIN movies m ON s.tmdb_id = m.tmdb_id
                                    WHERE s.user_id = ? AND s.swipe_type = 'like'
                                    ORDER BY s.created_at DESC""",
                                 (user_id,))
        return await cursor.fetchall()

async def get_user_stats(user_id: int) -> dict:
    """Получает статистику пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""SELECT swipe_type, COUNT(*) 
                                    FROM swipes WHERE user_id = ? 
                                    GROUP BY swipe_type""",
                                 (user_id,))
        stats = dict(await cursor.fetchall())
        
        cursor = await db.execute("SELECT COUNT(*) FROM shown_movies WHERE user_id = ?", (user_id,))
        shown = (await cursor.fetchone())[0]
        
        return {
            'likes': stats.get('like', 0),
            'dislikes': stats.get('dislike', 0),
            'total_swipes': stats.get('like', 0) + stats.get('dislike', 0),
            'shown_movies': shown
        }

# === Показанные фильмы ===
async def mark_movie_shown(user_id: int, tmdb_id: int):
    """Помечает фильм как показанный"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT INTO shown_movies (user_id, tmdb_id, shown_at) 
                           VALUES (?, ?, ?)""",
                        (user_id, tmdb_id, datetime.now().isoformat()))
        await db.commit()

async def get_shown_tmdb_ids(user_id: int) -> list:
    """Получает все tmdb_id показанных фильмов"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT tmdb_id FROM shown_movies WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

# === Жанры ===
async def save_user_genre(user_id: int, genre_id: int, genre_name: str):
    """Сохраняет выбранный жанр"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, не добавлен ли уже этот жанр
        cursor = await db.execute("""SELECT id FROM user_genres 
                                    WHERE user_id = ? AND genre_id = ?""",
                                 (user_id, genre_id))
        if not await cursor.fetchone():
            await db.execute("""INSERT INTO user_genres (user_id, genre_id, genre_name) 
                               VALUES (?, ?, ?)""",
                            (user_id, genre_id, genre_name))
            await db.commit()

async def get_user_genres(user_id: int) -> list:
    """Получает жанры пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""SELECT genre_id, genre_name FROM user_genres 
                                    WHERE user_id = ?""",
                                 (user_id,))
        return await cursor.fetchall()

async def clear_user_genres(user_id: int):
    """Удаляет все жанры пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM user_genres WHERE user_id = ?", (user_id,))
        await db.commit()

# === Приглашения и мэтчи ===
async def save_invitation(inviter_id: int, invitee_id: int):
    """Сохраняет приглашение"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT INTO invitations (inviter_id, invitee_id, created_at) 
                           VALUES (?, ?, ?)""",
                        (inviter_id, invitee_id, datetime.now().isoformat()))
        await db.commit()

async def get_mutual_matches(user1_id: int, user2_id: int) -> list:
    """Находит фильмы, которые лайкнули оба пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""SELECT m.tmdb_id, m.title, m.year, m.rating, m.poster_url
                                    FROM swipes s1
                                    JOIN swipes s2 ON s1.tmdb_id = s2.tmdb_id
                                    JOIN movies m ON s1.tmdb_id = m.tmdb_id
                                    WHERE s1.user_id = ? AND s1.swipe_type = 'like'
                                    AND s2.user_id = ? AND s2.swipe_type = 'like'
                                    ORDER BY s1.created_at DESC""",
                                 (user1_id, user2_id))
        return await cursor.fetchall()

async def get_all_friends(user_id: int) -> list:
    """Получает всех друзей (кого пригласил и кто пригласил)"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Кого пригласил я
        cursor = await db.execute("""SELECT u.id, u.username, u.full_name, 'invited' as type
                                    FROM invitations i
                                    JOIN users u ON i.invitee_id = u.id
                                    WHERE i.inviter_id = ?""",
                                 (user_id,))
        invited = await cursor.fetchall()
        
        # Кто пригласил меня
        cursor = await db.execute("""SELECT u.id, u.username, u.full_name, 'invited_by' as type
                                    FROM invitations i
                                    JOIN users u ON i.inviter_id = u.id
                                    WHERE i.invitee_id = ?""",
                                 (user_id,))
        invited_by = await cursor.fetchall()
        
        return invited + invited_by

async def check_new_matches(user_id: int, tmdb_id: int) -> list:
    """Проверяет, есть ли новые мэтчи после лайка"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Находим всех друзей
        friends = await get_all_friends(user_id)
        new_matches = []
        
        for friend_id, _, _, _ in friends:
            # Проверяем, лайкнул ли друг этот фильм
            cursor = await db.execute("""SELECT s.user_id FROM swipes s
                                        WHERE s.user_id = ? AND s.tmdb_id = ? AND s.swipe_type = 'like'""",
                                     (friend_id, tmdb_id))
            if await cursor.fetchone():
                # Получаем информацию о фильме
                cursor = await db.execute("""SELECT title, year FROM movies WHERE tmdb_id = ?""",
                                         (tmdb_id,))
                movie = await cursor.fetchone()
                if movie:
                    new_matches.append({
                        'friend_id': friend_id,
                        'title': movie[0],
                        'year': movie[1]
                    })
        
        return new_matches

# === Сброс данных ===
async def reset_user_data(user_id: int):
    """Сбрасывает все данные пользователя (кроме приглашений)"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM swipes WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM shown_movies WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM user_genres WHERE user_id = ?", (user_id,))
        await db.commit()