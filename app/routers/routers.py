from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db.connections import get_db
from app.models import Player, Match, MatchParticipant
from app.schemas.schemas import PlayerOut, RankedEntryOut, MatchParticipantOut, MatchOut, ChampionAggregateOut
from app.services.collector import collect_player
import logging
import asyncio
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@router.get("/players/{riot_id}", response_model=PlayerOut)
async def get_player_by_riot_id(
    riot_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        game_name, tag_line = riot_id.split("#", 1)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid Riot ID format. Use game_name#tag_line"
        )

    stmt = (
        select(Player)
        .where(
            Player.game_name == game_name,
            Player.tag_line == tag_line,
        )
    )

    result = await db.execute(stmt)
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    return player


@router.get("/players/{puuid}/ranked", response_model=PlayerOut)
async def get_player_ranked(
        puuid: str,
        session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(Player)
        .where(Player.puuid == puuid)
        .options(selectinload(Player.ranked_entries))  # не joinedload — избегаем дублей
    )
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    return PlayerOut(
        puuid=player.puuid,
        game_name=player.game_name,
        tag_line=player.tag_line,
        summoner_level=player.summoner_level,
        profile_icon_id=player.profile_icon_id,
        ranked=[
            RankedEntryOut(
                queue_type=r.queue_type,
                tier=r.tier,
                rank=r.rank,
                league_points=r.league_points,
                wins=r.wins,
                losses=r.losses,
            )
            for r in player.ranked_entries
        ],
    )


@router.get("/players/{puuid}/matches", response_model=list[MatchOut])
async def get_player_matches(
        puuid: str,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        session: AsyncSession = Depends(get_db),
):
    # Проверяем что игрок существует
    player = await session.get(Player, puuid)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Тянем участия игрока вместе с матчами
    result = await session.execute(
        select(MatchParticipant, Match)
        .join(Match, MatchParticipant.match_id == Match.match_id)
        .where(MatchParticipant.puuid == puuid)
        .order_by(Match.game_start.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()

    if not rows:
        return []

    return [
        MatchOut(
            match_id=match.match_id,
            game_version=match.game_version,
            queue_id=match.queue_id,
            game_mode=match.game_mode,
            game_duration=match.game_duration,
            game_start=match.game_start,
            stats=MatchParticipantOut(
                champion_name=p.champion_name,
                team_position=p.team_position,
                kills=p.kills,
                deaths=p.deaths,
                assists=p.assists,
                win=p.win,
                cs=p.cs,
                total_damage_dealt=p.total_damage_dealt,
            ),
        )
        for p, match in rows
    ]


@router.get("/admin/players/{puuid}/refresh")
async def refresh_player_by_puuid(
    puuid: str,
):
    await collect_player(
        game_name="G2 SkewMond",
        tag_line="3327",
        api_key=settings.RIOT_API_KEY,
        database_url=settings.DATABASE_URL,
    )


@router.get("/players/{puuid}/champions", response_model=list[ChampionAggregateOut])
async def get_champion_aggregates(
        puuid: str,
        limit: int = Query(default=10, ge=1, le=50, description="Топ N чемпионов"),
        session: AsyncSession = Depends(get_db),
):
    player = await session.get(Player, puuid)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    result = await session.execute(
        select(
            MatchParticipant.champion_name,
            func.count().label("games"),
            func.sum(
                func.cast(MatchParticipant.win, Integer)
            ).label("wins"),
            func.avg(MatchParticipant.kills).label("avg_kills"),
            func.avg(MatchParticipant.deaths).label("avg_deaths"),
            func.avg(MatchParticipant.assists).label("avg_assists"),
        )
        .where(MatchParticipant.puuid == puuid)
        .group_by(MatchParticipant.champion_name)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        ChampionAggregateOut(
            champion_name=row.champion_name,
            games=row.games,
            wins=row.wins,
            losses=row.games - row.wins,
            winrate=round(row.wins / row.games * 100, 1),
            avg_kills=round(float(row.avg_kills), 2),
            avg_deaths=round(float(row.avg_deaths), 2),
            avg_assists=round(float(row.avg_assists), 2),
            kda=round(
                (float(row.avg_kills) + float(row.avg_assists)) / max(float(row.avg_deaths), 1),
                2
            ),
        )
        for row in rows
    ]

