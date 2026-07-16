"""SQLite 저장소 — 아바타 상태, 시즌, 사건 로그, 행운 게이지."""
import datetime
import json
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Seoul")
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "thelife.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY, v TEXT
);
CREATE TABLE IF NOT EXISTS avatars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    category TEXT NOT NULL,            -- 역사 | 현실
    scenario_json TEXT NOT NULL,       -- 세계 텍스처 팩 (커스텀은 생성본)
    state_json TEXT NOT NULL,          -- 위치/재산/건강/감정/흉터
    last_sim_day TEXT,
    last_seen_at TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    no INTEGER NOT NULL,
    goal TEXT NOT NULL,
    milestones_json TEXT NOT NULL,
    milestone_idx INTEGER DEFAULT 0,
    interventions_left INTEGER DEFAULT 3,
    status TEXT DEFAULT 'active',      -- active | done
    biography TEXT,
    started_day TEXT,
    ended_day TEXT
);
CREATE TABLE IF NOT EXISTS cast_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    name TEXT, role TEXT, note TEXT,
    affinity INTEGER DEFAULT 50
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    slot TEXT,
    kind TEXT NOT NULL,                -- beat | daily | intervention | season | scar
    title TEXT,
    body TEXT,
    read INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS schedules (
    avatar_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    slots_json TEXT NOT NULL,
    PRIMARY KEY (avatar_id, day)
);
CREATE TABLE IF NOT EXISTS active_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    card_id TEXT NOT NULL,
    card_json TEXT,                    -- 즉흥 발제된 갈등의 구조 (LLM 생성)
    stage TEXT DEFAULT 'seed',         -- seed | rise | climax | done
    boost REAL DEFAULT 0,
    day_started TEXT,
    outcome TEXT                       -- good | bad | NULL
);
CREATE TABLE IF NOT EXISTS interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    slot_no INTEGER,
    size TEXT,                         -- 소 | 중 | 대
    luck_spent INTEGER,
    title TEXT, body TEXT,
    day TEXT
);
CREATE TABLE IF NOT EXISTS gauge (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    luck INTEGER DEFAULT 0,
    ads_today INTEGER DEFAULT 0,
    ads_date TEXT
);
CREATE TABLE IF NOT EXISTS hunches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    conflict_id INTEGER NOT NULL,      -- active_conflicts.id
    direction TEXT NOT NULL,           -- good | bad
    luck_staked INTEGER NOT NULL,
    status TEXT DEFAULT 'open',        -- open | won | lost | refunded
    payout INTEGER DEFAULT 0,
    created_day TEXT,
    resolved_day TEXT
);
CREATE TABLE IF NOT EXISTS state_history (
    avatar_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    money INTEGER,
    health INTEGER,
    PRIMARY KEY (avatar_id, day)
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        c.execute("INSERT OR IGNORE INTO gauge (id, luck) VALUES (1, 30)")
        for ddl in (  # 기존 DB 마이그레이션
            "ALTER TABLE active_conflicts ADD COLUMN card_json TEXT",
            "ALTER TABLE cast_members ADD COLUMN last_met TEXT",
        ):
            try:
                c.execute(ddl)
            except Exception:
                pass


def kv_get(c: sqlite3.Connection, k: str, default: str = "") -> str:
    row = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return row["v"] if row else default


def kv_set(c: sqlite3.Connection, k: str, v: str) -> None:
    c.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))


def real_now() -> datetime.datetime:
    return datetime.datetime.now(TZ)


def virtual_now(c: sqlite3.Connection) -> datetime.datetime:
    """시간 빨리감기(테스트) 오프셋을 더한 현재 시각."""
    offset = int(kv_get(c, "time_offset_days", "0"))
    return real_now() + datetime.timedelta(days=offset)


def vtoday(c: sqlite3.Connection) -> str:
    return virtual_now(c).date().isoformat()


def j(row_or_str):
    if row_or_str is None:
        return None
    return json.loads(row_or_str)
