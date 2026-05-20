# schemas.py
from datetime import datetime, timezone
from pydantic import BaseModel, field_validator, computed_field


class RiotBase(BaseModel):
    model_config = {"extra": "ignore"}


# Riot API response models (парсинг ответов Riot)

class RiotAccountResponse(RiotBase):
    puuid: str
    gameName: str
    tagLine: str


class RiotSummonerResponse(RiotBase):
    puuid: str
    id: str | None = None  # summonerId — нужен только для league-v4, не PK
    summonerLevel: int
    profileIconId: int


class RiotRankedEntryResponse(RiotBase):
    queueType: str
    tier: str | None = None
    rank: str | None = None
    leaguePoints: int = 0
    wins: int = 0
    losses: int = 0
    hotStreak: bool = False


class RiotParticipantResponse(RiotBase):
    puuid: str
    championId: int
    championName: str
    teamPosition: str  # используем это, не individualPosition
    kills: int
    deaths: int
    assists: int
    win: bool
    totalDamageDealtToChampions: int
    goldEarned: int
    totalMinionsKilled: int
    neutralMinionsKilled: int
    challenges: dict | None = None

    @computed_field
    @property
    def cs(self) -> int:
        return self.totalMinionsKilled + self.neutralMinionsKilled


class RiotMatchInfoResponse(RiotBase):
    queueId: int
    gameMode: str
    gameVersion: str  # "16.8.766.8562" - нормализуем в "16.8"
    gameDuration: int  # секунды
    gameCreation: int  # миллисекунды преобразуем в datetime
    participants: list[RiotParticipantResponse]

    @field_validator("gameCreation", mode="before")
    @classmethod
    def ms_to_utc(cls, v: int) -> datetime:
        """gameCreation приходит в миллисекундах — конвертируем в UTC datetime"""
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc)

    @field_validator("gameVersion", mode="before")
    @classmethod
    def parse_patch(cls, v: str) -> str:
        """'16.8.766.8562' → '16.8'"""
        parts = v.split(".")
        return f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else v

    # После валидаторов поля уже правильных типов
    gameCreation: datetime
    gameVersion: str  # уже нормализован в патч


class RiotMatchResponse(RiotBase):
    metadata: dict  # содержит matchId
    info: RiotMatchInfoResponse


# Public API response models (что отдаём наружу)

class RankedEntryOut(BaseModel):
    queue_type: str
    tier: str | None
    rank: str | None
    league_points: int
    wins: int
    losses: int

    @computed_field
    @property
    def winrate(self) -> float | None:
        total = self.wins + self.losses
        return round(self.wins / total * 100, 1) if total > 0 else None


class PlayerOut(BaseModel):
    puuid: str
    game_name: str
    tag_line: str
    summoner_level: int | None
    profile_icon_id: int | None
    ranked: list[RankedEntryOut] = []


class MatchParticipantOut(BaseModel):
    champion_name: str
    team_position: str
    kills: int
    deaths: int
    assists: int
    win: bool
    cs: int
    total_damage_dealt: int

    # @computed_field
    # @property
    # def kda(self) -> float:
    #     return round((self.kills + self.assists) / max(self.deaths, 1), 2)


class MatchOut(BaseModel):
    match_id: str
    patch: str
    queue_id: int
    game_mode: str
    game_duration: int
    game_start: datetime
    stats: MatchParticipantOut  # статистика целевого игрока


class ChampionAggregateOut(BaseModel):
    champion_name: str
    games: int
    wins: int
    losses: int
    winrate: float
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    kda: float
