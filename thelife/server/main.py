"""The Life — 관전형 AI 인생 게임 프로토타입 서버.

실행:  cd thelife && uvicorn server.main:app --reload --port 8000
GEMINI_API_KEY 환경변수가 있으면 실제 LLM으로, 없으면 목업 텍스트로 동작한다.
"""
import json

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from . import db
from .engine import conflicts, intervention, schedule, season as season_mod, world
from .llm import llm

app = FastAPI(title="The Life")
WEB = Path(__file__).resolve().parent.parent / "web"

db.init()
SCENARIOS = world.load_scenarios()
CARDS_BY_ID = world.load_conflict_cards()


def _loaded(c):
    """아바타 + 시나리오 + 시즌 로드 후 따라잡기 시뮬레이션까지."""
    avatar, scenario, season = season_mod.load_avatar(c)
    if avatar:
        season_mod.catch_up(c, avatar, scenario, season,
                            world.cards_for(scenario, CARDS_BY_ID), CARDS_BY_ID)
    return avatar, scenario, season


class SearchBody(BaseModel):
    name: str


class CustomBody(BaseModel):
    name: str
    age: str = "30"
    occupation: str = ""
    era: str = "현대 한국"
    persona: str = ""
    goal: str


class PresetBody(BaseModel):
    scenario_id: str


class SizeBody(BaseModel):
    size: str


class WarpBody(BaseModel):
    days: int = 1


class ContinueBody(BaseModel):
    mode: str  # continue | new
    goal: str = ""


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/presets")
def presets():
    return {
        "mock_mode": llm.is_mock,
        "presets": [
            {"id": s["id"], "name": s["name"], "type": s["type"],
             "era": s.get("era", ""), "goal": s.get("goal", "")}
            for s in SCENARIOS.values()
        ],
    }


@app.post("/api/search_person")
def search_person(body: SearchBody):
    name = body.name.strip()
    for s in SCENARIOS.values():
        if s["name"] == name:
            return {"found": True, "scenario_id": s["id"]}
    if world.is_living_famous(name):
        return {"found": False, "blocked": True, "message": world.BLOCK_MESSAGE}
    return {"found": False, "blocked": False,
            "message": "아직 이곳에 준비되지 않은 삶이에요. 프로토타입에서는 목록의 인물과 커스텀 아바타를 만날 수 있어요."}


def _create_avatar(c, scenario: dict, category: str):
    c.execute("DELETE FROM avatars")  # 프로토타입: 아바타 1명
    for t in ("seasons", "events", "schedules", "active_conflicts", "interventions", "cast_members"):
        c.execute(f"DELETE FROM {t}")
    day = db.vtoday(c)
    state = {"mood": "담담함", "notes": []}
    cur = c.execute(
        "INSERT INTO avatars (name, scenario_id, category, scenario_json, state_json, "
        "last_sim_day, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
        (scenario["name"], scenario["id"], category,
         json.dumps(scenario, ensure_ascii=False), json.dumps(state, ensure_ascii=False), day),
    )
    avatar_id = cur.lastrowid
    for m in scenario.get("cast", []):
        c.execute(
            "INSERT INTO cast_members (avatar_id, name, role, note, affinity) VALUES (?,?,?,?,?)",
            (avatar_id, m["name"], m.get("role", ""), m.get("note", ""), m.get("affinity", 50)),
        )
    sid = season_mod.start_season(c, avatar_id, 1, scenario["goal"], scenario["milestones"], day)
    c.execute(
        "INSERT INTO events (avatar_id, season_id, day, kind, title, body, created_at) "
        "VALUES (?,?,?,?,?,?,datetime('now'))",
        (avatar_id, sid, day, "season", "삶이 시작되다",
         f"{scenario['name']}의 이야기가 시작됐다. 목표 — \"{scenario['goal']}\". "
         f"그는 이 삶을 지켜보는 존재가 있다는 것을 모른다."),
    )
    return avatar_id


@app.post("/api/avatar/preset")
def create_preset(body: PresetBody):
    scenario = SCENARIOS.get(body.scenario_id)
    if not scenario:
        return {"ok": False, "error": "알 수 없는 시나리오"}
    with db.connect() as c:
        _create_avatar(c, scenario, scenario["type"])
    return {"ok": True}


@app.post("/api/avatar/custom")
def create_custom(body: CustomBody):
    if world.is_living_famous(body.name):
        return {"ok": False, "blocked": True, "message": world.BLOCK_MESSAGE}
    scenario = world.build_custom_scenario(body.model_dump())
    with db.connect() as c:
        _create_avatar(c, scenario, "현실")
    return {"ok": True}


@app.get("/api/state")
def state():
    with db.connect() as c:
        avatar, scenario, season = _loaded(c)
        if not avatar:
            return {"avatar": None}
        g = intervention.gauge(c)
        unread = c.execute(
            "SELECT COUNT(*) AS n FROM events WHERE avatar_id=? AND read=0", (avatar["id"],)
        ).fetchone()["n"]
        vnow = db.virtual_now(c)
        import datetime as _dt
        day0 = _dt.date.fromisoformat(season["started_day"])
        return {
            "avatar": {"name": avatar["name"], "category": avatar["category"],
                       "era": scenario.get("era", ""), "place": scenario.get("place", "")},
            "season": {"no": season["no"], "goal": season["goal"], "status": season["status"],
                       "interventions_left": season["interventions_left"],
                       "milestone_idx": season["milestone_idx"],
                       "milestones": season["milestones"],
                       "day_count": (vnow.date() - day0).days + 1},
            "gauge": {"luck": g["luck"], "ads_left": g["ads_left"]},
            "unread": unread,
            "vtime": vnow.strftime("%H:%M"),
            "vday": vnow.date().isoformat(),
            "mock_mode": llm.is_mock,
        }


@app.get("/api/now")
def now_scene():
    """'지금' — 현재 진행형 라이브 장면 (스트리밍)."""
    with db.connect() as c:
        avatar, scenario, season = _loaded(c)
        if not avatar:
            return {"error": "아바타가 없어요"}
        vnow = db.virtual_now(c)
        day, hhmm = vnow.date().isoformat(), vnow.strftime("%H:%M")
        slots = schedule.ensure_schedule(c, avatar["id"], scenario, day)
        slot = schedule.current_slot(slots, hhmm)
        note = conflicts.active_conflict_note(c, avatar["id"], CARDS_BY_ID)
        c.execute("UPDATE avatars SET last_seen_at=datetime('now') WHERE id=?", (avatar["id"],))
        c.commit()
        gen = list(  # 커넥션이 닫히기 전에 컨텍스트 준비를 끝낸다
            [avatar, scenario, slot, note, hhmm, day]
        )
    from .engine import narrative

    def streamer():
        with db.connect() as c2:
            for chunk in narrative.scene_stream(c2, gen[0], gen[1], gen[2], gen[3], gen[4], gen[5]):
                yield chunk

    return StreamingResponse(streamer(), media_type="text/plain; charset=utf-8")


@app.get("/api/feed")
def feed():
    """'그동안' — 마지막 방문 이후의 소식들 (읽음 처리)."""
    with db.connect() as c:
        avatar, scenario, season = _loaded(c)
        if not avatar:
            return {"events": []}
        rows = c.execute(
            "SELECT id, day, kind, title, body, read FROM events WHERE avatar_id=? "
            "ORDER BY id DESC LIMIT 60", (avatar["id"],),
        ).fetchall()
        c.execute("UPDATE events SET read=1 WHERE avatar_id=?", (avatar["id"],))
        return {"events": [dict(r) for r in rows]}


@app.get("/api/story")
def story():
    """'이야기' — 마일스톤 진행, 대사건 아카이브, 완결 전기."""
    with db.connect() as c:
        avatar, scenario, season = _loaded(c)
        if not avatar:
            return {"episodes": []}
        rows = c.execute(
            "SELECT day, kind, title, body FROM events WHERE season_id=? AND kind IN "
            "('beat','season','intervention','scar') ORDER BY id", (season["id"],),
        ).fetchall()
        return {
            "goal": season["goal"],
            "status": season["status"],
            "milestones": season["milestones"],
            "milestone_idx": season["milestone_idx"],
            "episodes": [dict(r) for r in rows],
            "biography": season.get("biography") or (
                c.execute("SELECT biography FROM seasons WHERE id=?", (season["id"],)).fetchone()["biography"]
            ),
        }


@app.post("/api/intervene")
def intervene(body: SizeBody):
    with db.connect() as c:
        avatar, scenario, season = _loaded(c)
        if not avatar:
            return {"ok": False, "error": "아바타가 없어요"}
        return intervention.intervene(c, avatar, scenario, season, CARDS_BY_ID, body.size)


@app.post("/api/ad")
def ad():
    with db.connect() as c:
        return intervention.watch_ad(c)


@app.post("/api/buy")
def buy():
    with db.connect() as c:
        return intervention.buy_luck(c)


@app.post("/api/season/next")
def season_next(body: ContinueBody):
    with db.connect() as c:
        avatar, scenario, season = _loaded(c)
        if not avatar or season["status"] != "done":
            return {"ok": False, "error": "아직 시즌이 진행 중이에요"}
        if body.mode == "new":
            c.execute("DELETE FROM avatars")
            return {"ok": True, "reset": True}
        goal = body.goal.strip() or f"{scenario['goal']} — 그 다음 이야기"
        milestones = [f"{goal}을(를) 향한 걸음 {i+1}" for i in range(3)] + [goal]
        day = db.vtoday(c)
        sid = season_mod.start_season(c, avatar["id"], season["no"] + 1, goal, milestones, day)
        c.execute("DELETE FROM active_conflicts WHERE avatar_id=?", (avatar["id"],))
        c.execute(
            "INSERT INTO events (avatar_id, season_id, day, kind, title, body, created_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            (avatar["id"], sid, day, "season", f"시즌 {season['no']+1} — 새로운 목표",
             f"{avatar['name']}의 삶이 계속된다. 새 목표 — \"{goal}\""),
        )
        return {"ok": True}


@app.post("/api/debug/timewarp")
def timewarp(body: WarpBody):
    """시간 빨리감기 (테스트) — 가상 시계를 n일 앞으로."""
    with db.connect() as c:
        cur = int(db.kv_get(c, "time_offset_days", "0"))
        db.kv_set(c, "time_offset_days", str(cur + max(0, body.days)))
        avatar, scenario, season = _loaded(c)
    return {"ok": True, "offset_days": cur + body.days}


@app.delete("/api/avatar")
def reset():
    with db.connect() as c:
        for t in ("avatars", "seasons", "events", "schedules",
                  "active_conflicts", "interventions", "cast_members"):
            c.execute(f"DELETE FROM {t}")
        db.kv_set(c, "time_offset_days", "0")
    return {"ok": True}


app.mount("/static", StaticFiles(directory=WEB), name="static")
