# collector.py
import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from app.models import Player, Match, MatchParticipant, RankedEntry

from app.schemas.schemas import (
    RiotAccountResponse,
    RiotSummonerResponse,
    RiotRankedEntryResponse,
    RiotMatchResponse,
)

logger = logging.getLogger(__name__)

PLATFORM = "https://euw1.api.riotgames.com"
REGIONAL = "https://europe.api.riotgames.com"

MATCH_COUNT = 20
SOLOQ_QUEUE = 420


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Токен-бакет на два лимита dev-ключа: 20 rps и 100 per 2 min.
    При 429 читает Retry-After и ждёт.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._per_second_tokens = 20
        self._per_second_refill = 1.0
        self._per_second_last = asyncio.get_event_loop().time()

        self._per_2min_tokens = 100
        self._per_2min_refill = 120.0
        self._per_2min_last = asyncio.get_event_loop().time()

    async def acquire(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()

            elapsed_s = now - self._per_second_last
            self._per_second_tokens = min(
                20,
                self._per_second_tokens + elapsed_s * (20 / self._per_second_refill)
            )
            self._per_second_last = now

            elapsed_2m = now - self._per_2min_last
            self._per_2min_tokens = min(
                100,
                self._per_2min_tokens + elapsed_2m * (100 / self._per_2min_refill)
            )
            self._per_2min_last = now

            if self._per_second_tokens < 1:
                await asyncio.sleep(self._per_second_refill / 20)
            if self._per_2min_tokens < 1:
                await asyncio.sleep(self._per_2min_refill / 100)

            self._per_second_tokens -= 1
            self._per_2min_tokens -= 1


# ---------------------------------------------------------------------------
# Riot HTTP клиент
# ---------------------------------------------------------------------------

class RiotClient:
    def __init__(self, api_key: str):
        self._headers = {"X-Riot-Token": api_key}
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._limiter = RateLimiter()

    async def _get(self, url: str, params: dict | None = None) -> dict | None:
        """
        - 429 - ждём Retry-After, повторяем (не считается попыткой)
        - 5xx - экспоненциальный backoff, до 3 попыток
        - 403 - fail-fast (ключ протух)
        - 404 - None (не ретраим)
        """
        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            await self._limiter.acquire()

            try:
                r = await self._client.get(url, headers=self._headers, params=params)
            except httpx.TransportError as e:
                logger.warning(f"Transport error {url}: {e}, attempt {attempt + 1}")
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            if r.status_code == 200:
                return r.json()

            if r.status_code == 404:
                logger.info(f"404 for {url} — skipping")
                return None

            if r.status_code == 403:
                raise RuntimeError(
                    "Riot API returned 403 — API key is expired or invalid. "
                    "Renew it at developer.riotgames.com"
                )

            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 5))
                logger.warning(f"429 rate limit — waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                continue  # не считаем за попытку

            if r.status_code >= 500:
                logger.warning(f"Riot {r.status_code} for {url}, attempt {attempt + 1}")
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            r.raise_for_status()

        raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")

    async def get_account(self, game_name: str, tag_line: str) -> dict | None:
        url = f"{REGIONAL}/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}"
        return await self._get(url)

    async def get_summoner(self, puuid: str) -> dict | None:
        url = f"{PLATFORM}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return await self._get(url)

    async def get_ranked(self, puuid: str) -> list[dict]:
        url = f"{PLATFORM}/lol/league/v4/entries/by-puuid/{puuid}"
        return await self._get(url) or []

    async def get_match_ids(self, puuid: str, count: int = MATCH_COUNT) -> list[str]:
        url = f"{REGIONAL}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return await self._get(url, params={"queue": SOLOQ_QUEUE, "count": count}) or []

    async def get_match(self, match_id: str) -> dict | None:
        url = f"{REGIONAL}/lol/match/v5/matches/{match_id}"
        return await self._get(url)

    async def close(self):
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Сохранение в БД (upsert — не плодим дубли)
# ---------------------------------------------------------------------------

async def upsert_player(session: AsyncSession, account: dict, summoner: dict) -> None:
    acc = RiotAccountResponse.model_validate(account)
    smn = RiotSummonerResponse.model_validate(summoner)

    # updated_at не указываем — SQLAlchemy проставит сам через default/onupdate
    stmt = pg_insert(Player).values(
        puuid=acc.puuid,
        game_name=acc.gameName,
        tag_line=acc.tagLine,
        summoner_level=smn.summonerLevel,
        profile_icon_id=smn.profileIconId,
    ).on_conflict_do_update(
        index_elements=["puuid"],
        set_={
            "game_name": acc.gameName,
            "tag_line": acc.tagLine,
            # "summoner_id": smn.id,
            "summoner_level": smn.summonerLevel,
            "profile_icon_id": smn.profileIconId,
            "updated_at": datetime.now(timezone.utc),  # при upsert onupdate не срабатывает
        }
    )
    await session.execute(stmt)


async def upsert_ranked(session: AsyncSession, puuid: str, entries: list[dict]) -> None:
    for raw in entries:
        entry = RiotRankedEntryResponse.model_validate(raw)

        stmt = pg_insert(RankedEntry).values(
            puuid=puuid,
            queue_type=entry.queueType,
            tier=entry.tier,
            rank=entry.rank,
            league_points=entry.leaguePoints,
            wins=entry.wins,
            losses=entry.losses,
            hot_streak=entry.hotStreak,
        ).on_conflict_do_update(
            index_elements=["puuid", "queue_type"],  # UniqueConstraint из модели
            set_={
                "tier": entry.tier,
                "rank": entry.rank,
                "league_points": entry.leaguePoints,
                "wins": entry.wins,
                "losses": entry.losses,
                "hot_streak": entry.hotStreak,
                # "updated_at": datetime.now(timezone.utc),
            }
        )
        await session.execute(stmt)


async def upsert_match(session: AsyncSession, raw: dict) -> None:
    match = RiotMatchResponse.model_validate(raw)
    match_id = raw["metadata"]["matchId"]

    stmt = pg_insert(Match).values(
        match_id=match_id,
        queue_id=match.info.queueId,
        game_mode=match.info.gameMode,
        game_version=match.info.gameVersion,
        game_duration=match.info.gameDuration,
        game_start=match.info.gameCreation, # уже datetime UTC из Pydantic
        raw_json=raw,
    ).on_conflict_do_nothing(index_elements=["match_id"])
    await session.execute(stmt)

    # for p in match.info.participants:
    #     stmt = pg_insert(MatchParticipant).values(
    #         match_id=match_id,
    #         puuid=p.puuid,
    #         champion_id=p.championId,
    #         champion_name=p.championName,
    #         team_position=p.teamPosition,
    #         kills=p.kills,
    #         deaths=p.deaths,
    #         assists=p.assists,
    #         win=p.win,
    #         total_damage_dealt=p.totalDamageDealtToChampions,
    #         gold_earned=p.goldEarned,
    #         cs=p.cs,                        # вычислен в Pydantic как computed_field
    #         challenges_json=p.challenges,
    #     ).on_conflict_do_nothing()
    #     await session.execute(stmt)


# Главная функция сбора данных

async def collect_player(
    game_name: str,
    tag_line: str,
    api_key: str,
    database_url: str,
) -> None:
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    client = RiotClient(api_key)

    try:
        logger.info(f"Starting collection for {game_name}#{tag_line}")

        # 1. PUUID
        account_data = await client.get_account(game_name, tag_line)
        if not account_data:
            raise RuntimeError(f"Player {game_name}#{tag_line} not found")
        puuid = account_data["puuid"]
        logger.info(f"Resolved PUUID: {puuid[:16]}...")

        # 2. Профиль + ранг
        summoner_data = await client.get_summoner(puuid)
        if not summoner_data:
            raise RuntimeError(f"Summoner not found for puuid {puuid}")
        ranked_data = await client.get_ranked(puuid)

        # 3. Сохраняем игрока и ранг
        async with session_factory() as session:
            async with session.begin():
                await upsert_player(session, account_data, summoner_data)
                await upsert_ranked(session, puuid, ranked_data)
        logger.info("Player and ranked saved")

        # 4. Список ID матчей
        match_ids = await client.get_match_ids(puuid)
        logger.info(f"Got {len(match_ids)} match IDs")

        # 5. Какие матчи уже есть в БД — не ходим в Riot повторно
        async with session_factory() as session:
            result = await session.execute(
                select(Match.match_id).where(Match.match_id.in_(match_ids))
            )
            existing_ids = {row[0] for row in result}

        new_ids = [mid for mid in match_ids if mid not in existing_ids]
        logger.info(f"New: {len(new_ids)}, skipping existing: {len(existing_ids)}")

        # 6. Тянем и сохраняем только новые матчи
        for match_id in new_ids:
            match_data = await client.get_match(match_id)
            if not match_data:
                logger.warning(f"Match {match_id} returned 404, skipping")
                continue

            async with session_factory() as session:
                async with session.begin():
                    await upsert_match(session, match_data)

            logger.info(f"Saved match {match_id}")

        logger.info(f"Collection complete for {game_name}#{tag_line}")

    finally:
        await client.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Запуск напрямую
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    print(os.environ["DATABASE_URL"])
    print(os.environ["RIOT_API_KEY"])

    logging.basicConfig(level=logging.INFO)

    asyncio.run(collect_player(
        game_name="G2 SkewMond",
        tag_line="3327",
        api_key=os.environ["RIOT_API_KEY"],
        database_url=os.environ["DATABASE_URL"],
    ))