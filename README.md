# LOLBackend

Backend-сервис для сбора и отображения статистики игроков League of Legends через Riot Games API.

## Переменные окружения

```env
RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/lolstats
```

> **Важно:** Riot Developer Key живёт 24 часа. Обновлять вручную на [developer.riotgames.com](https://developer.riotgames.com).

---

Сбор данных и API намеренно разделены: коллектор пишет в БД, API только читает. Riot API никогда не дёргается из API-хэндлеров.

---

## API эндпоинты
```
| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/healthz` | Healthcheck |
| `GET` | `/players?game_name=&tag_line=` | Найти игрока по Riot ID |
| `GET` | `/players/{puuid}/ranked` | Профиль + ранговая статистика |
| `GET` | `/players/{puuid}/matches` | Последние матчи (`?limit=20&offset=0`) |
| `GET` | `/players/{puuid}/champions` | Агрегаты по чемпионам (`?limit=10`) |
| `POST` | `/admin/players/collect?game_name=&tag_line=` | Триггер сбора данных |
```
Полная документация с примерами запросов и схемами ответов – `/docs`.

---

## Схема базы данных

```
players
  puuid (PK)          – единственный стабильный идентификатор Riot
  game_name, tag_line – Riot ID, индексированы для поиска
  summoner_level, profile_icon_id
  updated_at

ranked_entries
  puuid (FK – players)
  queue_type          – RANKED_SOLO_5x5 / RANKED_FLEX_SR
  tier, rank, lp, wins, losses
  UNIQUE (puuid, queue_type)

matches
  match_id (PK)       – например EUW1_7829724695
  queue_id, game_mode, game_version (патч "16.8"), game_duration
  game_start (TIMESTAMPTZ, UTC)
  raw_json (JSONB)    – сырой ответ Riot для перепарсинга

match_participants
  match_id (FK – matches), puuid (FK – players)
  champion, position, kills/deaths/assists, win, cs, damage
  challenges_json (JSONB) – 126 полей Riot, храним raw
  UNIQUE (match_id, puuid)
```

Идентичность игрока строится на `puuid` – Riot ID (`game_name#tag_line`) меняется и используется только для поиска. `summonerId` и `accountId` депрекейтнуты, в схеме не используются как ключи.

---

## Глубина истории и стратегия обновления

### Глубина: последние 20 матчей SoloQ (queue_id=420)

Выбрано осознанно:
- Dev-ключ имеет лимит 100 запросов / 2 минуты. 20 матчей = 1 запрос на список + 20 запросов на детали = **21 запрос** на полный сбор одного игрока, что укладывается в лимиты с запасом.
- 20 матчей покрывают ~2–4 недели активной игры и достаточны для агрегатов по чемпионам.
- Остальные режимы (Flex, ARAM, Arena) обрабатываются корректно но без специальной аналитики – как указано в задании.

Глубину легко изменить через константу `MATCH_COUNT` в `collector.py`.

### Стратегия обновления: инкрементальная

Повторный запуск не плодит дубли и не ходит в Riot за тем что уже есть:

1. **Игрок и ранг** – upsert по `puuid`. Всегда обновляются при запуске (ранг меняется часто).
2. **Матчи** – перед запросом к Riot сравниваем список ID с тем что уже есть в БД. Тянем только новые. Уже сохранённые матчи никогда не перезапрашиваются – исторические данные не меняются.
3. **Триггер** – `POST /admin/players/collect` запускает сбор асинхронно (202 Accepted), не блокируя запрос.

Первый запуск:  тянем 20 матчей из Riot – сохраняем все 20
Второй запуск:  тянем список ID – 17 уже в БД – тянем только 3 новых

---

## Обработка ошибок Riot API
```
| Код | Поведение |
|-----|-----------|
| `200` | Успех |
| `404` | Пропускаем (старый матч или удалённый аккаунт), не ретраим |
| `403` | Fail-fast: ключ протух, понятное сообщение об ошибке |
| `429` | Читаем `Retry-After`, ждём, повторяем (не считается попыткой) |
| `5xx` | Экспоненциальный backoff, до 3 попыток |
```
Rate limiter – токен-бакет на два лимита dev-ключа одновременно: 20 rps и 100 per 2 min.

---

## Структура проекта

```
app/
├── core/
│   ├── config.py          # настройки через pydantic-settings
├── db/
│   ├── base.py            # DeclarativeBase (только Base, без импортов моделей)
│   └── connections.py     # async engine + session factory
├── models/
│   ├── __init__.py        # собирает все модели (нужно для Alembic)
│   ├── player.py
│   ├── ranked_entry.py
│   ├── match.py
│   └── match_participant.py
├── schemas/
│   └── schemas.py         # Pydantic модели: Riot response + public API out
├── services/
│   └── collector.py       # сбор данных из Riot API
├── routers/
│   └── routers.py         # FastAPI эндпоинты
└── main.py
```
---
alembic/                   # миграции
docker-compose.yml
Dockerfile
.env.example


В `docker compose up` миграции применяются автоматически перед стартом API.

---

## Известные ограничения

- **Dev-ключ живёт 24 часа** – при истечении сервис вернёт 403 с понятным сообщением. Обновление ключа в `.env` + рестарт контейнера.
- **Только SoloQ** аналитика – остальные режимы сохраняются в БД корректно, но отдельных агрегатов по ним нет.
- **Нет авторизации** на `/admin` эндпоинтах – по условию задания не требуется.