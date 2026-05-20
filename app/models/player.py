from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Boolean, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.db.base import Base


class Player(Base):
    __tablename__ = "players"

    # PUUID — единственный идентификатор
    puuid: Mapped[str] = mapped_column(String(78), primary_key=True)

    # Riot ID — меняется, индексируем для поиска
    game_name: Mapped[str] = mapped_column(String(64), index=True)
    tag_line: Mapped[str] = mapped_column(Text, index=True)  # Text, не varchar — бывает не-ASCII

    # Summoner данные
    summoner_level: Mapped[int | None] = mapped_column(Integer)
    profile_icon_id: Mapped[int | None] = mapped_column(Integer)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
