"""갈등 엔진 — 갈등 은행에서 카드를 꺼내 씨앗→고조→절정→해소로 전개한다.

극복의 주체는 언제나 아바타다. 개입(행운)은 해소 확률을 끌어올릴 뿐,
개입 없이도 서사는 완결된다 — 다만 더 험할 뿐.
"""
import random
import sqlite3

from . import narrative

STAGES = ["seed", "rise", "climax"]
STAGE_LABEL = {"seed": "조짐", "rise": "고조", "climax": "절정"}
SCALE_WEIGHT_BY_ACT = {  # 막(act)별로 어떤 규모의 갈등이 잘 나오는가
    1: {"소": 5, "중": 3, "대": 1},
    2: {"소": 2, "중": 5, "대": 3},
    3: {"소": 1, "중": 3, "대": 5},
}


def _act(season: dict) -> int:
    total = max(len(season["milestones"]), 1)
    ratio = season["milestone_idx"] / total
    return 1 if ratio < 0.34 else (2 if ratio < 0.67 else 3)


def _used_card_ids(c: sqlite3.Connection, avatar_id: int) -> set:
    rows = c.execute("SELECT card_id FROM active_conflicts WHERE avatar_id=?", (avatar_id,)).fetchall()
    return {r["card_id"] for r in rows}


def _pick_new_card(c, avatar, season, cards: list, rng: random.Random):
    act = _act(season)
    weights = SCALE_WEIGHT_BY_ACT[act]

    def build_pool(exclude: set):
        pool, w = [], []
        for card in cards:
            if card["id"] in exclude or card.get("min_act", 1) > act:
                continue
            pool.append(card)
            w.append(weights.get(card.get("scale", "중"), 1))
        return pool, w

    pool, w = build_pool(_used_card_ids(c, avatar["id"]))
    if not pool:
        # 은행이 바닥났다 — 해소된 카드를 변주해 재사용한다 (진행 중인 것만 제외).
        # 시즌이 막다른 길에 빠지지 않게 하는 안전장치.
        active_now = {
            r["card_id"] for r in c.execute(
                "SELECT card_id FROM active_conflicts WHERE avatar_id=? AND stage != 'done'",
                (avatar["id"],),
            ).fetchall()
        }
        pool, w = build_pool(active_now)
    if not pool:
        return None
    return rng.choices(pool, weights=w, k=1)[0]


def _emit(c, avatar, season, day: str, kind: str, title: str, body: str, slot: str = ""):
    c.execute(
        "INSERT INTO events (avatar_id, season_id, day, slot, kind, title, body, created_at) "
        "VALUES (?,?,?,?,?,?,?,datetime('now'))",
        (avatar["id"], season["id"], day, slot, kind, title, body),
    )


def active_conflict_note(c: sqlite3.Connection, avatar_id: int, cards_by_id: dict) -> str:
    rows = c.execute(
        "SELECT card_id, stage FROM active_conflicts WHERE avatar_id=? AND stage != 'done'",
        (avatar_id,),
    ).fetchall()
    notes = []
    for r in rows:
        card = cards_by_id.get(r["card_id"])
        if card:
            notes.append(f"{card['title']} ({STAGE_LABEL[r['stage']]}): {card.get(r['stage'], '')}")
    return " / ".join(notes)


def daily_tick(
    c: sqlite3.Connection, avatar: dict, season: dict, day: str,
    scenario: dict, cards: list, cards_by_id: dict, slots: list,
) -> dict:
    """하루치 갈등 전개. 반환: {'milestone_advanced': bool, 'had_event': bool}"""
    rng = random.Random(f"{avatar['id']}:{day}:tick")
    result = {"milestone_advanced": False, "had_event": False}

    active = c.execute(
        "SELECT * FROM active_conflicts WHERE avatar_id=? AND stage != 'done'", (avatar["id"],)
    ).fetchall()

    # 1) 진행 중인 갈등을 전진시킨다
    for cf in active:
        card = cards_by_id.get(cf["card_id"])
        if card is None:
            continue
        if rng.random() > 0.65:  # 오늘은 조용히 지나간다 → 달성 시점의 예측 불가성
            continue
        if cf["stage"] in ("seed", "rise"):
            nxt = STAGES[STAGES.index(cf["stage"]) + 1]
            c.execute("UPDATE active_conflicts SET stage=? WHERE id=?", (nxt, cf["id"]))
            body = narrative.beat_text(c, avatar, scenario, nxt, card)
            _emit(c, avatar, season, day, "beat", f"{card['title']} — {STAGE_LABEL[nxt]}", body)
            result["had_event"] = True
        elif cf["stage"] == "climax":
            # 해소 판정 — 아바타의 힘 + (있다면) 행운의 보정
            success = rng.random() < min(0.55 + cf["boost"], 0.97)
            outcome = "good" if success else "bad"
            c.execute(
                "UPDATE active_conflicts SET stage='done', outcome=? WHERE id=?", (outcome, cf["id"])
            )
            body = narrative.beat_text(c, avatar, scenario, "done", card, outcome=outcome)
            mark = "극복" if success else "패배"
            _emit(c, avatar, season, day, "beat", f"{card['title']} — {mark}", body)
            result["had_event"] = True
            if success and card.get("scale") in ("중", "대"):
                new_idx = season["milestone_idx"] + 1
                c.execute("UPDATE seasons SET milestone_idx=? WHERE id=?", (new_idx, season["id"]))
                season["milestone_idx"] = new_idx
                result["milestone_advanced"] = True
                if new_idx <= len(season["milestones"]):
                    label = season["milestones"][min(new_idx - 1, len(season["milestones"]) - 1)]
                    _emit(c, avatar, season, day, "season", f"한 걸음 — {label}",
                          f"{avatar['name']}의 삶이 목표를 향해 한 걸음 나아갔다.")
            if not success:
                _emit(c, avatar, season, day, "scar", "잃은 것",
                      card.get("resolve_bad", "이번에는 졌다.") + " 그러나 이야기는 끝나지 않았다.")

    # 2) 새 갈등의 씨앗 — 동시 진행 2개 제한
    still_active = c.execute(
        "SELECT COUNT(*) AS n FROM active_conflicts WHERE avatar_id=? AND stage != 'done'",
        (avatar["id"],),
    ).fetchone()["n"]
    if still_active < 2 and rng.random() < 0.55:
        card = _pick_new_card(c, avatar, season, cards, rng)
        if card:
            c.execute(
                "INSERT INTO active_conflicts (avatar_id, season_id, card_id, stage, day_started) "
                "VALUES (?,?,?,'seed',?)",
                (avatar["id"], season["id"], card["id"], day),
            )
            body = narrative.beat_text(c, avatar, scenario, "seed", card)
            _emit(c, avatar, season, day, "beat", f"{card['title']} — 조짐", body)
            result["had_event"] = True

    # 3) 갈등이 조용한 날엔 잔잔한 일상 한 줄
    if not result["had_event"]:
        _emit(c, avatar, season, day, "daily", "오늘",
              narrative.daily_text(avatar, scenario, slots, rng))

    return result
