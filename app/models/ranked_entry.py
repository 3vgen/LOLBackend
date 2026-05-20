from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Boolean, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.db.base import Base


class RankedEntry(Base):
    __tablename__ = "ranked_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    puuid: Mapped[str] = mapped_column(String(78), ForeignKey("players.puuid"), index=True)

    queue_type: Mapped[str] = mapped_column(String(32))   # RANKED_SOLO_5x5 / RANKED_FLEX_SR
    tier: Mapped[str | None] = mapped_column(String(16))  # DIAMOND, MASTER
    rank: Mapped[str | None] = mapped_column(String(4))   # I, II, III, IV
    league_points: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    hot_streak: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    player: Mapped["Player"] = relationship(back_populates="ranked_entries")
