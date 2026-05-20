from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.connections import get_db
from app.models import Player
from app.schemas.schemas import PlayerOut

router = APIRouter()


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