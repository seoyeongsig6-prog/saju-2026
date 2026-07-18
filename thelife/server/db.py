"""저장소 — DATABASE_URL(Postgres, 영구 저장)이 있으면 그쪽으로, 없으면 SQLite.

Render 무료 서버는 잠들 때 디스크가 초기화되므로, 실서비스/지속 테스트에는
Neon 등 외부 Postgres를 DATABASE_URL로 연결한다. 삶은 사라지면 안 되니까.
"""
import datetime
import json
import os
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Seoul")
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "thelife.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY, v TEXT
);
CREATE TABLE IF NOT EXISTS user_gauge (
    user_id TEXT PRIMARY KEY,
    luck INTEGER DEFAULT 30,
    ads_today INTEGER DEFAULT 0,
    ads_date TEXT
);
CREATE TABLE IF NOT EXISTS avatars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    name TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    category TEXT NOT NULL,
    scenario_json TEXT NOT NULL,
    state_json TEXT NOT NULL,
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
    status TEXT DEFAULT 'active',
    biography TEXT,
    started_day TEXT,
    ended_day TEXT
);
CREATE TABLE IF NOT EXISTS cast_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    name TEXT, role TEXT, note TEXT,
    affinity INTEGER DEFAULT 50,
    last_met TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    slot TEXT,
    kind TEXT NOT NULL,
    title TEXT,
    body TEXT,
    detail TEXT,                      -- 본편 — 탭하면 열리는 온전한 장면
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
    card_json TEXT,
    stage TEXT DEFAULT 'seed',
    boost REAL DEFAULT 0,
    day_started TEXT,
    outcome TEXT
);
CREATE TABLE IF NOT EXISTS interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avatar_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    slot_no INTEGER,
    size TEXT,
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
    conflict_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    luck_staked INTEGER NOT NULL,
    status TEXT DEFAULT 'open',
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
CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    title TEXT NOT NULL,
    genre TEXT,
    premise TEXT,                     -- 로그라인
    ending TEXT,                      -- 작가가 고정한 결말 — 이야기는 이곳으로 흐른다
    style TEXT,
    total_chapters INTEGER DEFAULT 25,
    characters_json TEXT,             -- 원형(아키타입) 기반 인물들
    relations_json TEXT,              -- 관계도
    beats_json TEXT,                  -- Save the Cat 15비트
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id INTEGER NOT NULL,
    no INTEGER NOT NULL,
    title TEXT,
    body TEXT,
    summary TEXT,                     -- 다음 회차 생성용 기억
    directive TEXT,                   -- 작가의 지시
    beat_idx INTEGER,
    created_at TEXT,
    updated_at TEXT
)
"""


class Conn:
    """sqlite3/psycopg 겸용 커넥션 — 코드는 sqlite 문법으로 쓰고 여기서 번역한다."""

    def __init__(self):
        if IS_PG:
            import psycopg
            from psycopg.rows import dict_row
            self.raw = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
        else:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.raw = sqlite3.connect(DB_PATH)
            self.raw.row_factory = sqlite3.Row

    @staticmethod
    def _tx(sql: str) -> str:
        if not IS_PG:
            return sql
        sql = sql.replace("?", "%s")
        sql = sql.replace("datetime('now','-30 minutes')", "(now() - interval '30 minutes')")
        sql = sql.replace("datetime('now')", "now()")
        return sql

    def execute(self, sql: str, params=()):
        return self.raw.execute(self._tx(sql), params)

    def insert_id(self, sql: str, params=()) -> int:
        """INSERT 후 생성된 id — 백엔드별 방식 차이를 흡수한다."""
        if IS_PG:
            cur = self.raw.execute(self._tx(sql) + " RETURNING id", params)
            return cur.fetchone()["id"]
        return self.raw.execute(sql, params).lastrowid

    def commit(self):
        if not IS_PG:
            self.raw.commit()

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        self.close()
        return False


def connect() -> Conn:
    return Conn()


def init() -> None:
    with connect() as c:
        for stmt in SCHEMA.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            if IS_PG:
                stmt = stmt.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                                    "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
            c.execute(stmt)
        c.execute("INSERT INTO gauge (id, luck) VALUES (1, 30) ON CONFLICT (id) DO NOTHING")
        for ddl in (  # 구버전 DB 마이그레이션 (이미 있으면 조용히 통과)
            "ALTER TABLE active_conflicts ADD COLUMN card_json TEXT",
            "ALTER TABLE cast_members ADD COLUMN last_met TEXT",
            "ALTER TABLE events ADD COLUMN detail TEXT",
            "ALTER TABLE avatars ADD COLUMN user_id TEXT",
        ):
            try:
                c.execute(ddl)
            except Exception:
                pass


def kv_get(c: Conn, k: str, default: str = "") -> str:
    row = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return row["v"] if row else default


def kv_set(c: Conn, k: str, v: str) -> None:
    c.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))


def real_now() -> datetime.datetime:
    return datetime.datetime.now(TZ)


def virtual_now(c: Conn) -> datetime.datetime:
    """시간 빨리감기(테스트) 오프셋을 더한 현재 시각."""
    offset = int(kv_get(c, "time_offset_days", "0"))
    return real_now() + datetime.timedelta(days=offset)


def vtoday(c: Conn) -> str:
    return virtual_now(c).date().isoformat()


def j(row_or_str):
    if row_or_str is None:
        return None
    return json.loads(row_or_str)
