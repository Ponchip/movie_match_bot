import aiohttp
import os
import random
from dotenv import load_dotenv

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

async def get_popular_movies(page: int = 1) -> list:
    url = f"{TMDB_BASE_URL}/movie/popular"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU",
        "page": page
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('results', [])
            else:
                print(f"❌ Ошибка TMDB API: {response.status}")
                return []

async def get_movie_details(movie_id: int) -> dict:
    url = f"{TMDB_BASE_URL}/movie/{movie_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                
                poster_path = data.get('poster_path')
                poster_url = f"{IMAGE_BASE_URL}{poster_path}" if poster_path else None
                
                release_date = data.get('release_date')
                year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
                
                return {
                    'tmdb_id': data['id'],
                    'title': data['title'],
                    'year': year,
                    'rating': round(data.get('vote_average', 0), 1),
                    'poster_url': poster_url,
                    'description': data.get('overview', 'Описание отсутствует')
                }
            else:
                print(f"❌ Ошибка получения деталей фильма: {response.status}")
                return None

async def get_next_movie(page: int = 1) -> dict:
    """Получает следующий фильм для свайпа"""
    movies = await get_popular_movies(page)
    if not movies:
        return None
    
    random_movie = random.choice(movies)
    return await get_movie_details(random_movie['id'])