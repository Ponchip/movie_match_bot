import aiohttp
import os
import random
import logging
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
            logging.error(f"TMDB API error: {response.status}")
            return []

async def get_movie_details(movie_id: int) -> dict:
    url = f"{TMDB_BASE_URL}/movie/{movie_id}"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "append_to_response": "translations"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                return None
            data = await response.json()
            
            # Получаем русское описание
            overview = data.get('overview', '')
            
            # Если описания нет на русском — ищем в переводах
            if not overview or len(overview.strip()) < 20:
                translations = data.get('translations', {}).get('translations', [])
                for t in translations:
                    if t.get('iso_639_1') == 'ru':
                        ru_overview = t.get('data', {}).get('overview', '')
                        if ru_overview and len(ru_overview.strip()) >= 20:
                            overview = ru_overview
                            break
            
            # Если описания всё равно нет — фильм не локализован, пропускаем
            if not overview or len(overview.strip()) < 20:
                return None
            
            # Получаем жанры
            genres_data = data.get('genres', [])
            genres = [g['name'] for g in genres_data] if genres_data else []
            
            poster_path = data.get('poster_path')
            release_date = data.get('release_date')
            
            title = data.get('title', '')
            original_title = data.get('original_title', '')
            
            # Если название не локализовано (совпадает с оригиналом) — пропускаем
            if title == original_title and not any(c.isalpha() and ord(c) > 127 for c in title):
                return None
            
            return {
                'tmdb_id': data['id'],
                'title': title or original_title,
                'year': int(release_date[:4]) if release_date and len(release_date) >= 4 else None,
                'rating': round(data.get('vote_average', 0), 1),
                'poster_url': f"{IMAGE_BASE_URL}{poster_path}" if poster_path else None,
                'description': overview.strip(),
                'genres': genres
            }

async def get_next_movie(exclude_tmdb_ids: list = None, genre_ids: list = None) -> dict:
    if exclude_tmdb_ids is None:
        exclude_tmdb_ids = []
    
    # Проверяем больше страниц, т.к. многие фильмы могут быть отфильтрованы
    for page_num in range(1, 15):
        movies = await get_popular_movies(page_num)
        if not movies:
            continue
        if genre_ids:
            movies = [m for m in movies if any(g in genre_ids for g in m.get('genre_ids', []))]
        for movie in movies:
            if movie['id'] in exclude_tmdb_ids:
                continue
            result = await get_movie_details(movie['id'])
            if result:  # get_movie_details сам фильтрует нелокализованные
                return result
    
    # Если ничего не нашли — возвращаем None
    return None