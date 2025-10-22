from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import get_db, MovieModel
from database.models import CountryModel, GenreModel, ActorModel, LanguageModel
from schemas.movies import (
    MovieListResponseSchema,
    MovieListItemSchema,
    MovieDetailSchema,
    MovieCreateSchema,
    MovieUpdateSchema,
    CountryOutSchema,
    NamedEntitySchema,
)
import datetime


router = APIRouter()

BASE_PATH = "/theater/movies/"


@router.get("/movies/", response_model=MovieListResponseSchema)
async def list_movies(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count(MovieModel.id))
    result = await db.execute(count_stmt)
    total_items = result.scalar_one()

    if total_items == 0:
        raise HTTPException(status_code=404, detail="No movies found.")

    total_pages = (total_items + per_page - 1) // per_page
    offset = (page - 1) * per_page

    if page < 1 or page > total_pages:
        raise HTTPException(status_code=404, detail="No movies found.")

    stmt = (
        select(MovieModel)
        .order_by(MovieModel.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    movies_result = await db.execute(stmt)
    movies: list[MovieModel] = movies_result.scalars().all()

    items = [
        MovieListItemSchema(
            id=m.id,
            name=m.name,
            date=m.date,
            score=m.score,
            overview=m.overview,
        )
        for m in movies
    ]

    prev_page = f"{BASE_PATH}?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"{BASE_PATH}?page={page + 1}&per_page={per_page}" if page < total_pages else None

    return MovieListResponseSchema(
        movies=items,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


@router.get("/movies/{movie_id}/", response_model=MovieDetailSchema)
async def get_movie_details(movie_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(MovieModel)
        .where(MovieModel.id == movie_id)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages),
        )
    )
    result = await db.execute(stmt)
    movie: MovieModel | None = result.scalars().first()

    if movie is None:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    return MovieDetailSchema(
        id=movie.id,
        name=movie.name,
        date=movie.date,
        score=movie.score,
        overview=movie.overview,
        status=movie.status,
        budget=float(movie.budget),
        revenue=float(movie.revenue),
        country=CountryOutSchema(id=movie.country.id, code=movie.country.code, name=movie.country.name),
        genres=[NamedEntitySchema(id=g.id, name=g.name) for g in movie.genres],
        actors=[NamedEntitySchema(id=a.id, name=a.name) for a in movie.actors],
        languages=[NamedEntitySchema(id=lang.id, name=lang.name) for lang in movie.languages],
    )


def _validate_movie_payload_for_create(payload: MovieCreateSchema) -> None:
    today = datetime.date.today()
    if len(payload.name) > 255:
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if payload.date > today + datetime.timedelta(days=365):
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if not (0 <= payload.score <= 100):
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if payload.budget < 0 or payload.revenue < 0:
        raise HTTPException(status_code=400, detail="Invalid input data.")


def _validate_movie_payload_for_update(payload: MovieUpdateSchema) -> None:
    today = datetime.date.today()
    if payload.name is not None and len(payload.name) > 255:
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if payload.date is not None and payload.date > today + datetime.timedelta(days=365):
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if payload.score is not None and not (0 <= payload.score <= 100):
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if payload.budget is not None and payload.budget < 0:
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if payload.revenue is not None and payload.revenue < 0:
        raise HTTPException(status_code=400, detail="Invalid input data.")


async def _get_or_create_country(db: AsyncSession, code: str) -> CountryModel:
    stmt = select(CountryModel).where(CountryModel.code == code)
    result = await db.execute(stmt)
    country = result.scalars().first()
    if country is None:
        country = CountryModel(code=code)
        db.add(country)
        await db.flush()
    return country


async def _get_or_create_named(db: AsyncSession, model, name: str):
    stmt = select(model).where(model.name == name)
    result = await db.execute(stmt)
    obj = result.scalars().first()
    if obj is None:
        obj = model(name=name)
        db.add(obj)
        await db.flush()
    return obj


@router.post("/movies/", response_model=MovieDetailSchema, status_code=201)
async def create_movie(payload: MovieCreateSchema, db: AsyncSession = Depends(get_db)):
    _validate_movie_payload_for_create(payload)

    dup_stmt = select(MovieModel).where(
        (MovieModel.name == payload.name) & (MovieModel.date == payload.date)
    )
    dup_result = await db.execute(dup_stmt)
    if dup_result.scalars().first() is not None:
        detail_msg = (
            "A movie with the name "
            f"'{payload.name}' and release date '{payload.date.isoformat()}' already exists."
        )
        raise HTTPException(status_code=409, detail=detail_msg)

    country = await _get_or_create_country(db, payload.country)

    genres = [await _get_or_create_named(db, GenreModel, g) for g in payload.genres]
    actors = [await _get_or_create_named(db, ActorModel, a) for a in payload.actors]
    languages = [
        await _get_or_create_named(db, LanguageModel, lang)
        for lang in payload.languages
    ]

    movie = MovieModel(
        name=payload.name,
        date=payload.date,
        score=payload.score,
        overview=payload.overview,
        status=payload.status,
        budget=payload.budget,
        revenue=payload.revenue,
        country=country,
        genres=genres,
        actors=actors,
        languages=languages,
    )

    db.add(movie)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        detail_msg = (
            "A movie with the name "
            f"'{payload.name}' and release date '{payload.date.isoformat()}' already exists."
        )
        raise HTTPException(status_code=409, detail=detail_msg)

    await db.refresh(movie)

    return await get_movie_details(movie.id, db)


@router.delete("/movies/{movie_id}/", status_code=204)
async def delete_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(MovieModel).where(MovieModel.id == movie_id)
    result = await db.execute(stmt)
    movie = result.scalars().first()
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    await db.execute(delete(MovieModel).where(MovieModel.id == movie_id))
    await db.commit()
    return Response(status_code=204)


@router.patch("/movies/{movie_id}/")
async def update_movie(movie_id: int, payload: MovieUpdateSchema, db: AsyncSession = Depends(get_db)):
    stmt = select(MovieModel).where(MovieModel.id == movie_id)
    result = await db.execute(stmt)
    movie = result.scalars().first()

    if movie is None:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    _validate_movie_payload_for_update(payload)

    for field in ["name", "date", "score", "overview", "status", "budget", "revenue"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(movie, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid input data.")

    return {"detail": "Movie updated successfully."}
