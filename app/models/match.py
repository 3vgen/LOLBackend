from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Boolean, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.db.base import Base
from sqlalchemy.dialects.postgresql import JSONB


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # EUW1_7829724695
    queue_id: Mapped[int] = mapped_column(Integer, index=True)            # 420 SoloQ
    game_mode: Mapped[str] = mapped_column(String(32))
    game_version: Mapped[str] = mapped_column(String(16))     # "16.8" — первые два сегмента gameVersion
    game_duration: Mapped[int] = mapped_column(Integer)  # секунды
    game_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # UTC

    raw_json: Mapped[dict] = mapped_column(JSONB)  # сырой ответ Riot целиком

    participants: Mapped[list["MatchParticipant"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )