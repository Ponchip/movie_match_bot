import aiohttp
import os
import random
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

GENRE_MAP = {
    28: "Боевик", 12: "Приключения", 16: "Мультфильм", 35: "Комедия",
    80: "Криминал", 99: "Документальный", 18: "Драма", 10751: "Семейный",
    14: "Фэнтези", 36: "История", 27: "Ужасы", 10402: "Музыка",
    9648: "Детектив", 10749: "Мелодрама", 878: "Фантастика",
    10770: "ТВ фильм", 53: "Триллер", 10752: "Военный", 37: "Вестерн"
}

_session = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None

async def get_popular_movies(page: int = 1, genre_ids: list = None) -> list:
    """Получает популярные фильмы, опционально фильтруя по жанрам"""
    url = f"{TMDB_BASE_URL}/discover/movie" if genre_ids else f"{TMDB_BASE_URL}/movie/popular"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU",
        "page": page,
        "sort_by": "popularity.desc"
    }
    if genre_ids:
        params["with_genres"] = ",".join(map(str, genre_ids))

    session = await get_session()
    async with session.get(url, params=params) as response:
        if response.status == 200:
            data = await response.json()
            return data.get('results', [])
        print(f"❌ Ошибка TMDB API: {response.status}")
        return []

async def get_movie_details(tmdb_id: int) -> dict:
    """Получает детальную информацию о фильме"""
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU"}
    
    session = await get_session()
    async with session.get(url, params=params) as response:
        if response.status == 200:
            data = await response.json()
            poster_path = data.get('poster_path')
            release_date = data.get('release_date')
            genres = data.get('genres', [])
            
            return {
                'tmdb_id': data['id'],
                'title': data['title'],
                'year': int(release_date[:4]) if release_date and len(release_date) >= 4 else None,
                'rating': round(data.get('vote_average', 0), 1),
                'poster_url': f"{IMAGE_BASE_URL}{poster_path}" if poster_path else None,
                'description': data.get('overview', 'Описание отсутствует'),
                'genres': [g['id'] for g in genres]
            }
        return None

async def get_next_movie(exclude_tmdb_ids: list = None, genre_ids: list = None) -> dict:
    """Получает следующий фильм, исключая уже показанные (оптимизировано)"""
    if exclude_tmdb_ids is None:
        exclude_tmdb_ids = []
    
    # Используем set для мгновенного поиска O(1)
    exclude_set = set(exclude_tmdb_ids)

    # Проверяем 5 страниц (достаточно для большинства случаев)
    for page_num in range(1, 6):
        movies = await get_popular_movies(page_num, genre_ids)
        if not movies:
            continue
        
        # Сначала фильтруем на уровне Python, чтобы не делать лишних API-запросов
        available_movies = [m for m in movies if m['id'] not in exclude_set]
        
        if available_movies:
            # Берем случайный фильм из доступных для разнообразия
            chosen_movie = random.choice(available_movies)
            return await get_movie_details(chosen_movie['id'])

    return None

async def search_movie(query: str) -> list:
    """Ищет фильм по названию"""
    url = f"{TMDB_BASE_URL}/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU",
        "query": query
    }
    
    session = await get_session()
    async with session.get(url, params=params) as response:
        if response.status == 200:
            data = await response.json()
            results = []
            for movie in data.get('results', [])[:5]:
                details = await get_movie_details(movie['id'])
                if details:
                    results.append(details)
            return results
        return []