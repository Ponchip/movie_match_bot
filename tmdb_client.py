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
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "page": page}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return (await response.json()).get('results', [])
            return []

async def get_movie_details(movie_id: int) -> dict:
    url = f"{TMDB_BASE_URL}/movie/{movie_id}"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                poster_path = data.get('poster_path')
                release_date = data.get('release_date')
                return {
                    'tmdb_id': data['id'],
                    'title': data.get('title', 'Без названия'),
                    'year': int(release_date[:4]) if release_date and len(release_date) >= 4 else None,
                    'rating': round(data.get('vote_average', 0), 1),
                    'poster_url': f"{IMAGE_BASE_URL}{poster_path}" if poster_path else None,
                    'description': data.get('overview', 'Описание отсутствует')
                }
            return None

async def get_next_movie(exclude_tmdb_ids: list = None, genre_ids: list = None) -> dict:
    if exclude_tmdb_ids is None:
        exclude_tmdb_ids = []
    
    for page_num in range(1, 10):
        movies = await get_popular_movies(page_num)
        if not movies:
            continue
        if genre_ids:
            movies = [m for m in movies if any(g in genre_ids for g in m.get('genre_ids', []))]
        for movie in movies:
            if movie['id'] not in exclude_tmdb_ids:
                result = await get_movie_details(movie['id'])
                if result:
                    return result
    
    all_movies = await get_popular_movies(1)
    for movie in all_movies:
        if movie['id'] not in exclude_tmdb_ids:
            return await get_movie_details(movie['id'])
    
    if all_movies:
        return await get_movie_details(random.choice(all_movies)['id'])
    return None