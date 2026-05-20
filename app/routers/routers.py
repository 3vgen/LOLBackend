from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.connections import get_db
from app.models import Player
from app.schemas.schemas import PlayerOut
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



