"""The Life — 관전형 AI 인생 게임 프로토타입 서버.

실행:  cd thelife && uvicorn server.main:app --reload --port 8000
GEMINI_API_KEY 환경변수가 있으면 실제 LLM으로, 없으면 목업 텍스트로 동작한다.
"""
import json

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from . import db
from .engine import conflicts, intervention, narrative, schedule, season as season_mod, world
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


def _loaded(c, user: str = "solo"):
    """아바타 + 시나리오 + 시즌 로드 후 따라잡기 시뮬레이션까지.
    반환: (avatar, scenario, season, cards_by_id) — 즉석 생성 카드 포함 색인."""
    avatar, scenario, season = season_mod.load_avatar(c, user)
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


@app.get("/api/avatars")
def list_avatars(user: str = Header(default="solo", alias="X-User-Id")):
    """지켜보는 중인 삶들 — 동시에 여러 스토리를 살 수 있다."""
    with db.connect() as c:
        active_id = db.kv_get(c, f"active_avatar:{user}", "")
        out = []
        for a in c.execute("SELECT id, name, category FROM avatars WHERE user_id=? ORDER BY id", (user,)).fetchall():
            s = c.execute("SELECT * FROM seasons WHERE avatar_id=? ORDER BY no DESC LIMIT 1",
                          (a["id"],)).fetchone()
            unread = c.execute("SELECT COUNT(*) AS n FROM events WHERE avatar_id=? AND read=0",
                               (a["id"],)).fetchone()["n"]
            import datetime as _dt
            day_count = 1
            if s:
                day_count = max(1, (_dt.date.fromisoformat(db.vtoday(c))
                                    - _dt.date.fromisoformat(s["started_day"])).days + 1)
            last = c.execute(
                "SELECT title, body, kind FROM events WHERE avatar_id=? "
                "AND kind IN ('beat','shadow','diary','intervention','season','briefing') "
                "ORDER BY id DESC LIMIT 1", (a["id"],),
            ).fetchone()
            av = c.execute("SELECT state_json, scenario_json FROM avatars WHERE id=?", (a["id"],)).fetchone()
            st = json.loads(av["state_json"] or "{}")
            sc = json.loads(av["scenario_json"])
            milestones = json.loads(s["milestones_json"]) if s else []
            out.append({"id": a["id"], "name": a["name"], "category": a["category"],
                        "goal": s["goal"] if s else "", "status": s["status"] if s else "",
                        "season_no": s["no"] if s else 1, "day_count": day_count,
                        "unread": unread, "active": str(a["id"]) == active_id,
                        "mood": st.get("mood", ""), "money": st.get("money", 0),
                        "money_unit": sc.get("money_unit", ""),
                        "milestone_idx": s["milestone_idx"] if s else 0,
                        "milestone_total": max(len(milestones), 1),
                        "last_kind": last["kind"] if last else "",
                        "last_line": ((last["title"] + " — " if last and last["kind"] != "diary" else "")
                                      + (last["body"] or "")[:70]) if last else "아직 조용하다"})
        return {"avatars": out, "max": MAX_AVATARS}


@app.get("/api/gauge")
def get_gauge(user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        g = intervention.gauge(c, user)
        return {"luck": g["luck"], "ads_left": g["ads_left"]}


class SelectBody(BaseModel):
    id: int


@app.post("/api/avatar/select")
def select_avatar(body: SelectBody, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        row = c.execute("SELECT id FROM avatars WHERE id=? AND user_id=?", (body.id, user)).fetchone()
        if not row:
            return {"ok": False, "error": "그 삶을 찾을 수 없어요."}
        db.kv_set(c, f"active_avatar:{user}", str(body.id))
    return {"ok": True}


@app.post("/api/avatar/create")
def create_avatar(body: CreateBody, user: str = Header(default="solo", alias="X-User-Id")):
    """자유 입력 아바타 생성 — 누구든, 어떤 목표든.
    이름이 예시 인물과 일치하고 목표를 따로 쓰지 않았으면 정성 제작 팩을 쓰고,
    그 외에는 LLM이 그 삶의 세계를 즉석에서 짓는다."""
    name = body.name.strip()
    if not name:
        return {"ok": False, "error": "이름을 알려주세요."}
    with db.connect() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM avatars WHERE user_id=?", (user,)).fetchone()["n"]
        if n >= MAX_AVATARS:
            return {"ok": False,
                    "error": f"동시에 지켜볼 수 있는 삶은 {MAX_AVATARS}개까지예요. 먼저 한 삶을 떠나보내 주세요."}
    if world.is_living_famous(name):
        return {"ok": False, "blocked": True, "message": world.BLOCK_MESSAGE}

    goal = body.goal.strip()
    for s in SCENARIOS.values():
        if s["name"] == name and (not goal or goal == s["goal"]):
            with db.connect() as c:
                _create_avatar(c, s, s["type"], user)
            return {"ok": True}

    scenario = world.build_scenario(body.model_dump())
    if scenario is None:
        return {"ok": False,
                "error": "세계를 짓는 데 실패했어요. 잠시 후 한 번 더 시도해 주세요."}
    with db.connect() as c:
        _create_avatar(c, scenario, scenario.get("type", "현실"), user)
    return {"ok": True}


MAX_AVATARS = 3  # 동시에 지켜볼 수 있는 삶 (기획: 최소 2)


def _create_avatar(c, scenario: dict, category: str, user: str = "solo"):
    day = db.vtoday(c)
    state = {"money": scenario.get("money_start", 100), "health": 80, "mood": "담담함"}
    avatar_id = c.insert_id(
        "INSERT INTO avatars (user_id, name, scenario_id, category, scenario_json, state_json, "
        "last_sim_day, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
        (user, scenario["name"], scenario["id"], category,
         json.dumps(scenario, ensure_ascii=False), json.dumps(state, ensure_ascii=False), day),
    )
    db.kv_set(c, f"active_avatar:{user}", str(avatar_id))
    c.execute("INSERT INTO state_history (avatar_id, day, money, health) VALUES (?,?,?,?) "
              "ON CONFLICT(avatar_id, day) DO UPDATE SET money=excluded.money, health=excluded.health",
              (avatar_id, day, state["money"], state["health"]))
    for m in scenario.get("cast", []):
        c.execute(
            "INSERT INTO cast_members (avatar_id, name, role, note, affinity) VALUES (?,?,?,?,?)",
            (avatar_id, m["name"], m.get("role", ""), m.get("note", ""), m.get("affinity", 50)),
        )
    sid = season_mod.start_season(c, avatar_id, 1, scenario["goal"], scenario["milestones"], day)
    # 오프닝 브리핑 — 세계의 날짜·시각·날씨·분위기로 카메라가 내려온다
    hhmm = db.virtual_now(c).strftime("%H:%M")
    briefing = narrative.briefing_text(scenario, hhmm)
    c.execute(
        "INSERT INTO events (avatar_id, season_id, day, kind, title, body, created_at) "
        "VALUES (?,?,?,?,?,?,datetime('now'))",
        (avatar_id, sid, day, "briefing", "이야기가 시작되는 곳", briefing),
    )
    return avatar_id


@app.get("/api/state")
def state(user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        avatar, scenario, season, _ = _loaded(c, user)
        if not avatar:
            return {"avatar": None}
        g = intervention.gauge(c, user)
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


@app.get("/api/now/last")
def now_last(user: str = Header(default="solo", alias="X-User-Id")):
    """방금 지켜본 장면 — 다시 열면 재생성 없이 그대로 보여준다."""
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c, user)
        if not avatar:
            return {"scene": None}
        today = db.vtoday(c)
        row = c.execute(
            "SELECT title, body, created_at FROM events WHERE avatar_id=? AND kind='scene' AND day=? "
            "ORDER BY id DESC LIMIT 1",
            (avatar["id"], today),
        ).fetchone()
        if not row:
            return {"scene": None}
        # 신선도 판정은 파이썬에서 — SQLite/Postgres의 시간 표현 차이를 흡수
        import datetime as _dt
        try:
            raw = str(row["created_at"])
            ts = _dt.datetime.fromisoformat(raw.replace(" ", "T"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_dt.timezone.utc)
            fresh = (_dt.datetime.now(_dt.timezone.utc) - ts) < _dt.timedelta(minutes=30)
        except Exception:
            fresh = True
        return {"scene": {"title": row["title"], "body": row["body"]} if fresh else None}


@app.get("/api/now")
def now_scene(user: str = Header(default="solo", alias="X-User-Id")):
    """'지금' — 현재 진행형 라이브 장면 (스트리밍 + 기록 보존)."""
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c, user)
        if not avatar:
            return {"error": "아바타가 없어요"}
        vnow = db.virtual_now(c)
        day_iso, hhmm = vnow.date().isoformat(), vnow.strftime("%H:%M")
        slots = schedule.ensure_schedule(c, avatar["id"], scenario, day_iso)
        slot = schedule.current_slot(slots, hhmm)
        note = conflicts.active_conflict_note(c, avatar["id"], by_id)
        day_label = f"{_day_no(season['started_day'], day_iso)}일차"
        c.execute("UPDATE avatars SET last_seen_at=datetime('now') WHERE id=?", (avatar["id"],))
        c.commit()
        ctx = [avatar, scenario, slot, note, hhmm, day_label]
        meta = {"avatar_id": avatar["id"], "season_id": season["id"],
                "day": day_iso, "hhmm": hhmm}
    from .engine import narrative

    def streamer():
        chunks = []
        with db.connect() as c2:
            for chunk in narrative.scene_stream(c2, ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[5]):
                chunks.append(chunk)
                yield chunk
            text = "".join(chunks).strip()
            if text:  # 지켜본 장면은 기록으로 남는다 — 언제든 다시 읽을 수 있게
                c2.execute(
                    "INSERT INTO events (avatar_id, season_id, day, slot, kind, title, body, read, created_at) "
                    "VALUES (?,?,?,?,?,?,?,1,datetime('now'))",
                    (meta["avatar_id"], meta["season_id"], meta["day"], meta["hhmm"],
                     "scene", f"{meta['hhmm']} — 지켜본 장면", text),
                )

    return StreamingResponse(streamer(), media_type="text/plain; charset=utf-8")


@app.get("/api/dashboard")
def dashboard(user: str = Header(default="solo", alias="X-User-Id")):
    """'상태' — 아바타 대시보드: 재산·체력·기분·관계·진행 중인 갈등·흉터."""
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c, user)
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
        # 살아 움직이는 티커 + 그가 모르는 움직임 (읽음 처리 없이 살짝 엿본다)
        ticker_rows = c.execute(
            "SELECT day, kind, title, body FROM events WHERE avatar_id=? "
            "AND kind IN ('beat','shadow','daily','intervention','hunch','season','diary') "
            "ORDER BY id DESC LIMIT 14", (avatar["id"],),
        ).fetchall()
        ticker = [{"kind": r["kind"],
                   "text": (r["title"] + " — " if r["kind"] != "daily" else "") + (r["body"] or "")[:90],
                   "day_no": _day_no(season["started_day"], r["day"])} for r in ticker_rows]
        shadow_row = c.execute(
            "SELECT body FROM events WHERE avatar_id=? AND kind='shadow' ORDER BY id DESC LIMIT 1",
            (avatar["id"],),
        ).fetchone()
        return {
            "name": avatar["name"],
            "ticker": ticker,
            "shadow_last": shadow_row["body"] if shadow_row else None,
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
def feed(user: str = Header(default="solo", alias="X-User-Id")):
    """'그동안' — 마지막 방문 이후의 소식들 (읽음 처리)."""
    with db.connect() as c:
        avatar, scenario, season, _ = _loaded(c, user)
        if not avatar:
            return {"events": []}
        rows = c.execute(
            "SELECT id, day, season_id, kind, title, body, detail, read FROM events WHERE avatar_id=? "
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
def story(user: str = Header(default="solo", alias="X-User-Id")):
    """'이야기' — 마일스톤 진행, 대사건 아카이브, 완결 전기."""
    with db.connect() as c:
        avatar, scenario, season, _ = _loaded(c, user)
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


class HunchBody(BaseModel):
    conflict_id: int
    direction: str  # good | bad
    luck: int = 10


@app.get("/api/hunches")
def hunches(user: str = Header(default="solo", alias="X-User-Id")):
    """예감 — 절정으로 향하는 갈등 중 아직 예감을 맡기지 않은 것들."""
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c, user)
        if not avatar:
            return {"offerable": [], "open": []}
        taken = {r["conflict_id"] for r in c.execute(
            "SELECT conflict_id FROM hunches WHERE season_id=?", (season["id"],)).fetchall()}
        offerable = []
        for r in c.execute(
            "SELECT * FROM active_conflicts WHERE avatar_id=? AND stage IN ('rise','climax')",
            (avatar["id"],),
        ).fetchall():
            if r["id"] in taken:
                continue
            card = conflicts.card_of(r, by_id)
            if card:
                offerable.append({"conflict_id": r["id"], "title": card["title"],
                                  "stage_label": conflicts.STAGE_LABEL[r["stage"]],
                                  "hint": card.get(r["stage"], "")})
        open_h = []
        for h in c.execute(
            "SELECT h.*, ac.card_id, ac.card_json FROM hunches h "
            "JOIN active_conflicts ac ON ac.id = h.conflict_id "
            "WHERE h.season_id=? AND h.status='open'", (season["id"],),
        ).fetchall():
            card = conflicts.card_of(h, by_id)
            open_h.append({"title": card["title"] if card else "",
                           "direction": h["direction"], "luck": h["luck_staked"]})
        g = intervention.gauge(c, user)
        return {"offerable": offerable, "open": open_h, "luck": g["luck"]}


@app.post("/api/hunch")
def place_hunch(body: HunchBody, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c, user)
        if not avatar:
            return {"ok": False, "error": "아바타가 없어요"}
        if body.direction not in ("good", "bad"):
            return {"ok": False, "error": "예감은 '이겨낸다'거나 '어렵겠다' 둘 중 하나예요."}
        luck = max(5, min(100, int(body.luck)))
        g = intervention.gauge(c, user)
        if g["luck"] < luck:
            return {"ok": False, "error": f"행운이 부족해요. (보유 {g['luck']})"}
        cf = c.execute(
            "SELECT * FROM active_conflicts WHERE id=? AND avatar_id=? AND stage IN ('rise','climax')",
            (body.conflict_id, avatar["id"]),
        ).fetchone()
        if not cf:
            return {"ok": False, "error": "이미 지나갔거나 아직 오지 않은 일이에요."}
        dup = c.execute("SELECT 1 FROM hunches WHERE conflict_id=? ", (cf["id"],)).fetchone()
        if dup:
            return {"ok": False, "error": "이 일에는 이미 예감을 맡겨뒀어요."}
        c.execute("UPDATE user_gauge SET luck=luck-? WHERE user_id=?", (luck, user))
        c.execute(
            "INSERT INTO hunches (avatar_id, season_id, conflict_id, direction, luck_staked, created_day) "
            "VALUES (?,?,?,?,?,?)",
            (avatar["id"], season["id"], cf["id"], body.direction, luck, db.vtoday(c)),
        )
        return {"ok": True, "luck_left": g["luck"] - luck}


@app.post("/api/intervene")
def intervene(body: SizeBody, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        avatar, scenario, season, by_id = _loaded(c, user)
        if not avatar:
            return {"ok": False, "error": "아바타가 없어요"}
        return intervention.intervene(c, avatar, scenario, season, by_id, body.size)


@app.post("/api/ad")
def ad(user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        return intervention.watch_ad(c, user)


@app.post("/api/buy")
def buy(user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        return intervention.buy_luck(c, user)


@app.post("/api/season/next")
def season_next(body: ContinueBody, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        avatar, scenario, season, _ = _loaded(c, user)
        if not avatar or season["status"] != "done":
            return {"ok": False, "error": "아직 시즌이 진행 중이에요"}
        if body.mode == "new":
            # 완결된 삶은 전기와 함께 슬롯에 남는다 — 새 삶은 새 슬롯에서
            return {"ok": True, "go_create": True}
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
        avatar, scenario, season, _ = _loaded(c, user)
    return {"ok": True, "offset_days": cur + body.days}


@app.delete("/api/avatar")
def leave_avatar(user: str = Header(default="solo", alias="X-User-Id")):
    """활성 아바타의 삶을 떠나보낸다 — 다른 삶들은 그대로 이어진다."""
    with db.connect() as c:
        avatar, _, _, _ = _loaded(c, user)
        if not avatar:
            return {"ok": True}
        for t in ("seasons", "events", "schedules", "active_conflicts",
                  "interventions", "cast_members", "hunches", "state_history"):
            c.execute(f"DELETE FROM {t} WHERE avatar_id=?", (avatar["id"],))
        c.execute("DELETE FROM avatars WHERE id=?", (avatar["id"],))
        nxt = c.execute("SELECT id FROM avatars WHERE user_id=? ORDER BY id DESC LIMIT 1", (user,)).fetchone()
        db.kv_set(c, f"active_avatar:{user}", str(nxt["id"]) if nxt else "")
    return {"ok": True}


app.mount("/static", StaticFiles(directory=WEB), name="static")
