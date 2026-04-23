import json
import os
from datetime import datetime

RATINGS_FILE = os.path.join(os.path.dirname(__file__), "ratings.json")


def load_ratings() -> dict:
    if not os.path.exists(RATINGS_FILE):
        return {}
    with open(RATINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_rating(movie: str, user_id: int, username: str, rating: float) -> list:
    data = load_ratings()
    if movie not in data:
        data[movie] = []
    data[movie] = [r for r in data[movie] if r["user_id"] != user_id]
    data[movie].append({
        "user_id": user_id,
        "username": username,
        "rating": rating,
        "timestamp": datetime.now().isoformat(),
    })
    with open(RATINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data[movie]


def get_movie_ratings(movie: str) -> list:
    data = load_ratings()
    for key in data:
        if key.lower().startswith(movie.lower()):
            return data[key], key
    return [], movie


def get_top_movies(limit: int = 10) -> list:
    data = load_ratings()
    results = []
    for movie, ratings in data.items():
        if ratings:
            avg = sum(r["rating"] for r in ratings) / len(ratings)
            results.append({"movie": movie, "average": avg, "count": len(ratings)})
    return sorted(results, key=lambda x: x["average"], reverse=True)[:limit]
