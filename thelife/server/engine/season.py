"""시즌 오케스트레이션 — 따라잡기 시뮬레이션, 시즌 완결, 전기 생성."""
import datetime
import json
import sqlite3

from .. import db
from . import conflicts, narrative, schedule


def load_avatar(c: sqlite3.Connection):
    row = c.execute("SELECT * FROM avatars ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None, None, None
    avatar = dict(row)
    scenario = json.loads(avatar["scenario_json"])
    srow = c.execute(
        "SELECT * FROM seasons WHERE avatar_id=? ORDER BY no DESC LIMIT 1", (avatar["id"],)
    ).fetchone()
    season = dict(srow) if srow else None
    if season:
        season["milestones"] = json.loads(season["milestones_json"])
    return avatar, scenario, season


def catch_up(c: sqlite3.Connection, avatar: dict, scenario: dict, season: dict,
             cards: list, cards_by_id: dict, max_days: int = 14) -> None:
    """마지막 시뮬레이션 이후의 날들을 굴린다 — 세계는 계속 살아 있었다."""
    if season is None or season["status"] != "active":
        return
    today = db.vtoday(c)
    last = avatar["last_sim_day"] or today
    d_last = datetime.date.fromisoformat(last)
    d_today = datetime.date.fromisoformat(today)
    if d_today <= d_last:
        return

    days = []
    d = d_last
    while d < d_today:
        d += datetime.timedelta(days=1)
        days.append(d.isoformat())
    if len(days) > max_days:  # 아주 오래 비웠으면 최근 위주로
        days = days[-max_days:]

    for day in days:
        slots = schedule.ensure_schedule(c, avatar["id"], scenario, day)
        conflicts.daily_tick(c, avatar, season, day, scenario, cards, cards_by_id, slots)
        if season["milestone_idx"] >= len(season["milestones"]):
            finish_season(c, avatar, scenario, season, day)
            break

    c.execute("UPDATE avatars SET last_sim_day=? WHERE id=?", (today, avatar["id"]))
    avatar["last_sim_day"] = today


def finish_season(c: sqlite3.Connection, avatar: dict, scenario: dict, season: dict, day: str) -> None:
    bio = narrative.biography_text(c, avatar, scenario, season)
    c.execute(
        "UPDATE seasons SET status='done', biography=?, ended_day=? WHERE id=?",
        (bio, day, season["id"]),
    )
    season["status"] = "done"
    season["biography"] = bio
    c.execute(
        "INSERT INTO events (avatar_id, season_id, day, kind, title, body, created_at) "
        "VALUES (?,?,?,?,?,?,datetime('now'))",
        (avatar["id"], season["id"], day, "season", "목표를 이루다",
         f"{avatar['name']}이(가) 마침내 해냈다 — \"{season['goal']}\". 완결된 이야기가 남았다."),
    )


def start_season(c: sqlite3.Connection, avatar_id: int, no: int, goal: str,
                 milestones: list, day: str) -> int:
    cur = c.execute(
        "INSERT INTO seasons (avatar_id, no, goal, milestones_json, started_day) VALUES (?,?,?,?,?)",
        (avatar_id, no, goal, json.dumps(milestones, ensure_ascii=False), day),
    )
    return cur.lastrowid
