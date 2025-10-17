from __future__ import annotations

import datetime
from pydantic import BaseModel

from database.models import MovieStatusEnum


class MovieListItemSchema(BaseModel):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str


class MovieListResponseSchema(BaseModel):
    movies: list["MovieListItemSchema"]
    prev_page: str | None
    next_page: str | None
    total_pages: int
    total_items: int


class CountryOutSchema(BaseModel):
    id: int
    code: str
    name: str | None = None


class NamedEntitySchema(BaseModel):
    id: int
    name: str


class MovieDetailSchema(BaseModel):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str
    status: MovieStatusEnum
    budget: float
    revenue: float

    country: "CountryOutSchema"
    genres: list["NamedEntitySchema"]
    actors: list["NamedEntitySchema"]
    languages: list["NamedEntitySchema"]


class MovieCreateSchema(BaseModel):
    name: str
    date: datetime.date
    score: float
    overview: str
    status: MovieStatusEnum
    budget: float
    revenue: float

    country: str
    genres: list[str] = []
    actors: list[str] = []
    languages: list[str] = []


class MovieUpdateSchema(BaseModel):
    name: str | None = None
    date: datetime.date | None = None
    score: float | None = None
    overview: str | None = None
    status: MovieStatusEnum | None = None
    budget: float | None = None
    revenue: float | None = None
