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


@app.exception_handler(Exception)
async def debug_errors(request, exc):
    """프로토타입 디버그 — 500 대신 원인을 그대로 보여준다 (베타 전 제거)."""
    import traceback
    from fastapi.responses import JSONResponse
    tb = traceback.format_exc()
    print(tb, flush=True)
    return JSONResponse(status_code=500, content={
        "ok": False,
        "error": "서버 오류 (아래 내용을 캡처해서 알려주세요)",
        "detail": f"{type(exc).__name__}: {exc}",
        "trace": tb.splitlines()[-6:],
    })

db.init()
SCENARIOS = world.load_scenarios()
CARDS_BY_ID = world.load_conflict_cards()


def _day_no(start_day: str, day: str) -> int:
    """달력 날짜 대신 '삶의 N일차' — 시즌 시작 기준."""
    import datetime as _dt
    try:
        return max(1, (_dt.date.fromisoformat(day) - _dt.date.fromisoformat(start_day)).days + 1)
    except Exception:
        return 1


def _loaded(c):
    """아바타 + 시나리오 + 시즌 로드 후 따라잡기 시뮬레이션까지.
    반환: (avatar, scenario, season, cards_by_id) — 즉석 생성 카드 포함 색인."""
    avatar, scenario, season = season_mod.load_avatar(c)
    by_id = CARDS_BY_ID
    if avatar:
        cards, by_id = world.scenario_card_index(scenario, CARDS_BY_ID)
        season_mod.catch_up(c, avatar, scenario, season, cards, by_id)
    return avatar, scenario, season, by_id


class CreateBody(BaseModel):
    name: str
    age: str = ""
    occupation: str = ""
    era: str = ""
    persona: str = ""
    goal: str = ""


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


@app.post("/api/avatar/create")
def create_avatar(body: CreateBody):
    """자유 입력 아바타 생성 — 누구든, 어떤 목표든.
    이름이 예시 인물과 일치하고 목표를 따로 쓰지 않았으면 정성 제작 팩을 쓰고,
    그 외에는 LLM이 그 삶의 세계를 즉석에서 짓는다."""
    name = body.name.strip()
    if not name:
        return {"ok": False, "error": "이름을 알려주세요."}
    if world.is_living_famous(name):
        return {"ok": False, "blocked": True, "message": world.BLOCK_MESSAGE}

    goal = body.goal.strip()
    for s in SCENARIOS.values():
        if s["name"] == name and (not goal or goal == s["goal"]):
            with db.connect() as c:
                _create_avatar(c, s, s["type"])
            return {"ok": True}

    scenario = world.build_scenario(body.model_dump())
    if scenario is None:
        return {"ok": False,
                "error": "세계를 짓는 데 실패했어요. 잠시 후 한 번 더 시도해 주세요."}
    with db.connect() as c:
        _create_avatar(c, scenario, scenario.get("type", "현실"))
    return {"ok": True}


def _create_avatar(c, scenario: dict, category: str):
    c.execute("DELETE FROM avatars")  # 프로토타입: 아바타 1명
    for t in ("seasons", "events", "schedules", "active_conflicts", "interventions", "cast_members"):
        c.execute(f"DELETE FROM {t}")
    day = db.vtoday(c)
    state = {"money": scenario.get("money_start", 100), "health": 80, "mood": "담담함"}
    cur = c.execute(
        "INSERT INTO avatars (name, scenario_id, category, scenario_json, state_json, "
        "last_sim_day, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
        (scenario["name"], scenario["id"], category,
         json.dumps(scenario, ensure_ascii=False), json.dumps(state, ensure_ascii=False), day),
    )
    avatar_id = cur.lastrowid
    c.execute("INSERT OR REPLACE INTO state_history (avatar_id, day, money, health) VALUES (?,?,?,?)",
              (avatar_id, day, state["money"], state["health"]))
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


@app.get("/api/state")
def state():
    with db.connect() as c:
        avatar, scenario, season, _ = _loaded(c)
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
        avatar, scenario, season, by_id = _loaded(c)
        if not avatar:
            return {"error": "아바타가 없어요"}
        vnow = db.virtual_now(c)
        day, hhmm = vnow.date().isoformat(), vnow.strftime("%H:%M")
        slots = schedule.ensure_schedule(c, avatar["id"], scenario, day)
        slot = schedule.current_slot(slots, hhmm)
        note = conflicts.active_conflict_note(c, avatar["id"], by_id)
        day = f"{_day_no(season['started_day'], day)}일차"  # 프롬프트에도 달력 날짜 대신
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


@app.get("/api/dashboard")
def dashboard():
    """'상태' — 아바타 대시보드: 재산·체력·기분·관계·진행 중인 갈등·흉터."""
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c)
        if not avatar:
            return {"avatar": None}
        state = json.loads(avatar.get("state_json") or "{}")
        history = [dict(r) for r in c.execute(
            "SELECT day, money, health FROM state_history WHERE avatar_id=? "
            "ORDER BY day DESC LIMIT 14", (avatar["id"],),
        ).fetchall()][::-1]
        today = db.vtoday(c)
        cast = []
        for r in c.execute(
            "SELECT name, role, note, affinity, last_met FROM cast_members "
            "WHERE avatar_id=? ORDER BY affinity DESC", (avatar["id"],),
        ).fetchall():
            days_ago = None
            if r["last_met"]:
                import datetime as _dt
                days_ago = (_dt.date.fromisoformat(today) - _dt.date.fromisoformat(r["last_met"])).days
            cast.append({**dict(r), "days_ago": days_ago})
        actives = []
        for r in c.execute(
            "SELECT * FROM active_conflicts WHERE avatar_id=? AND season_id=? AND stage != 'done'",
            (avatar["id"], season["id"]),
        ).fetchall():
            card = conflicts.card_of(r, by_id)
            if card:
                actives.append({"title": card["title"], "stage": r["stage"],
                                "stage_label": conflicts.STAGE_LABEL[r["stage"]]})
        counts = c.execute(
            "SELECT SUM(CASE WHEN kind='scar' THEN 1 ELSE 0 END) AS scars FROM events WHERE season_id=?",
            (season["id"],),
        ).fetchone()
        overcome = c.execute(
            "SELECT COUNT(*) AS n FROM active_conflicts WHERE season_id=? AND outcome='good'",
            (season["id"],),
        ).fetchone()["n"]
        return {
            "name": avatar["name"],
            "money": state.get("money", 0),
            "money_unit": scenario.get("money_unit", ""),
            "health": state.get("health", 80),
            "mood": state.get("mood", "담담함"),
            "history": history,
            "cast": cast,
            "conflicts": actives,
            "scars": counts["scars"] or 0,
            "overcome": overcome,
            "goal": season["goal"],
            "milestone_idx": season["milestone_idx"],
            "milestones": season["milestones"],
            "interventions_left": season["interventions_left"],
        }


@app.get("/api/feed")
def feed():
    """'그동안' — 마지막 방문 이후의 소식들 (읽음 처리)."""
    with db.connect() as c:
        avatar, scenario, season, _ = _loaded(c)
        if not avatar:
            return {"events": []}
        rows = c.execute(
            "SELECT id, day, season_id, kind, title, body, read FROM events WHERE avatar_id=? "
            "ORDER BY id DESC LIMIT 60", (avatar["id"],),
        ).fetchall()
        c.execute("UPDATE events SET read=1 WHERE avatar_id=?", (avatar["id"],))
        starts = {r["id"]: r["started_day"] for r in c.execute(
            "SELECT id, started_day FROM seasons WHERE avatar_id=?", (avatar["id"],)).fetchall()}
        events = []
        for r in rows:
            e = dict(r)
            e["day_no"] = _day_no(starts.get(r["season_id"], r["day"]), r["day"])
            events.append(e)
        return {"events": events}


@app.get("/api/story")
def story():
    """'이야기' — 마일스톤 진행, 대사건 아카이브, 완결 전기."""
    with db.connect() as c:
        avatar, scenario, season, _ = _loaded(c)
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
            "episodes": [{**dict(r), "day_no": _day_no(season["started_day"], r["day"])}
                         for r in rows],
            "biography": season.get("biography") or (
                c.execute("SELECT biography FROM seasons WHERE id=?", (season["id"],)).fetchone()["biography"]
            ),
        }


@app.post("/api/intervene")
def intervene(body: SizeBody):
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c)
        if not avatar:
            return {"ok": False, "error": "아바타가 없어요"}
        return intervention.intervene(c, avatar, scenario, season, by_id, body.size)


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
        avatar, scenario, season, _ = _loaded(c)
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
        avatar, scenario, season, _ = _loaded(c)
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
