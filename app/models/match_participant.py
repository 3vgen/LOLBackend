from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Boolean, Float, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.db.base import Base
from sqlalchemy.dialects.postgresql import JSONB


class MatchParticipant(Base):
    __tablename__ = "match_participants"
    __table_args__ = (
        # один участник встречается в матче ровно один раз
        UniqueConstraint("match_id", "puuid", name="uq_participant_match_puuid"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(String(32), ForeignKey("matches.match_id"), index=True)
    # puuid: Mapped[str] = mapped_column(String(78), ForeignKey("players.puuid"), index=True)
    puuid: Mapped[str] = mapped_column(String(78), ForeignKey("players.puuid"), index=True)

    champion_id: Mapped[int] = mapped_column(Integer)
    champion_name: Mapped[str] = mapped_column(String(64))
    team_position: Mapped[str] = mapped_column(String(16))  # teamPosition, не individualPosition

    kills: Mapped[int] = mapped_column(Integer)  # assists
    deaths: Mapped[int] = mapped_column(Integer)  # deaths
    assists: Mapped[int] = mapped_column(Integer)
    win: Mapped[bool] = mapped_column(Boolean)

    total_damage_dealt: Mapped[int] = mapped_column(Integer)  # totalDamageDealt
    gold_earned: Mapped[int] = mapped_column(Integer)  # goldEarned
    cs: Mapped[int] = mapped_column(Integer)  # totalMinionsKilled + neutralMinionsKilled

    challenges_json: Mapped[dict | None] = mapped_column(JSONB)  # 126 полей — храним raw

    match: Mapped["Match"] = relationship(back_populates="participants")
    player: Mapped["Player"] = relationship(back_populates="participations")