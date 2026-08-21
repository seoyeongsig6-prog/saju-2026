"""개입 — 시즌당 3회, 행운 게이지를 실어 세계의 인과로 번역해 배달한다."""
import random
import sqlite3

from .. import db
from . import narrative

COST = {"소": 10, "중": 50, "대": 100}
BOOST = {"소": 0.15, "중": 0.30, "대": 0.42}
ADS_PER_DAY = 5
AD_LUCK = 10
BUY_LUCK = 100  # 결제 목업


def gauge(c: sqlite3.Connection, user: str = "solo") -> dict:
    row = c.execute("SELECT * FROM user_gauge WHERE user_id=?", (user,)).fetchone()
    if not row:
        c.execute("INSERT INTO user_gauge (user_id, luck) VALUES (?, 30) "
                  "ON CONFLICT (user_id) DO NOTHING", (user,))
        row = c.execute("SELECT * FROM user_gauge WHERE user_id=?", (user,)).fetchone()
    today = db.vtoday(c)
    g = dict(row)
    if g["ads_date"] != today:
        c.execute("UPDATE user_gauge SET ads_today=0, ads_date=? WHERE user_id=?", (today, user))
        g["ads_today"], g["ads_date"] = 0, today
    g["ads_left"] = ADS_PER_DAY - g["ads_today"]
    return g


def watch_ad(c: sqlite3.Connection, user: str = "solo") -> dict:
    g = gauge(c, user)
    if g["ads_left"] <= 0:
        return {"ok": False, "error": "오늘의 광고 시청 횟수를 다 썼어요. 내일 다시 볼 수 있어요."}
    c.execute("UPDATE user_gauge SET luck=luck+?, ads_today=ads_today+1 WHERE user_id=?",
              (AD_LUCK, user))
    return {"ok": True, "added": AD_LUCK}


def buy_luck(c: sqlite3.Connection, user: str = "solo") -> dict:
    gauge(c, user)  # 행 보장
    c.execute("UPDATE user_gauge SET luck=luck+? WHERE user_id=?", (BUY_LUCK, user))
    return {"ok": True, "added": BUY_LUCK}


def intervene(c: sqlite3.Connection, avatar: dict, scenario: dict, season: dict,
              cards_by_id: dict, size: str) -> dict:
    if size not in COST:
        return {"ok": False, "error": "크기는 소/중/대 중 하나여야 해요."}
    if season["status"] != "active":
        return {"ok": False, "error": "시즌이 끝났어요. 다음 시즌에서 개입할 수 있어요."}
    if season["interventions_left"] <= 0:
        return {"ok": False, "error": "이번 시즌의 개입 3번을 모두 썼어요. 이제 지켜보는 일만 남았어요."}
    user = avatar.get("user_id") or "solo"
    g = gauge(c, user)
    if g["luck"] < COST[size]:
        return {"ok": False, "error": f"행운이 부족해요. ({size}: {COST[size]} 필요, 보유 {g['luck']})"}

    # 번역할 행운의 형태를 고른다 — 행운 사전에서
    rng = random.Random()
    luck_lines = scenario.get("luck_dict", {}).get(size) or ["뜻밖의 좋은 일이 일어난다"]
    luck_line = rng.choice(luck_lines)

    # 얽힐 갈등 — 절정 > 고조 > 조짐 순으로 가장 급한 것
    target = c.execute(
        "SELECT * FROM active_conflicts WHERE avatar_id=? AND stage != 'done' "
        "ORDER BY CASE stage WHEN 'climax' THEN 0 WHEN 'rise' THEN 1 ELSE 2 END LIMIT 1",
        (avatar["id"],),
    ).fetchone()
    conflict_title = ""
    if target:
        from . import conflicts as conflicts_mod
        card = conflicts_mod.card_of(target, cards_by_id)
        conflict_title = card["title"] if card else ""
        c.execute(
            "UPDATE active_conflicts SET boost=boost+? WHERE id=?", (BOOST[size], target["id"])
        )

    hhmm = db.virtual_now(c).strftime("%H:%M")
    body = narrative.intervention_text(c, avatar, scenario, size, luck_line, conflict_title, hhmm)
    day = db.vtoday(c)
    slot_no = 4 - season["interventions_left"]
    title = f"행운이 닿다 ({size})"

    # 행운의 물질적 흔적 — 재산·기분에 반영
    from . import conflicts as conflicts_mod
    state = conflicts_mod._load_state(avatar, scenario)
    bump = {"소": 0.04, "중": 0.12, "대": 0.25}[size]
    state["money"] = int(state["money"] * (1 + bump))
    state["mood"] = "알 수 없는 든든함"
    conflicts_mod._save_state(c, avatar, state, day)

    c.execute("UPDATE user_gauge SET luck=luck-? WHERE user_id=?", (COST[size], user))
    c.execute("UPDATE seasons SET interventions_left=interventions_left-1 WHERE id=?", (season["id"],))
    season["interventions_left"] -= 1
    c.execute(
        "INSERT INTO interventions (avatar_id, season_id, slot_no, size, luck_spent, title, body, day) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (avatar["id"], season["id"], slot_no, size, COST[size], title, body, day),
    )
    c.execute(
        "INSERT INTO events (avatar_id, season_id, day, kind, title, body, created_at) "
        "VALUES (?,?,?,?,?,?,datetime('now'))",
        (avatar["id"], season["id"], day, "intervention", title, body),
    )
    return {"ok": True, "title": title, "body": body, "left": season["interventions_left"]}
