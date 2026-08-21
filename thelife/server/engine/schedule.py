"""일과표 — 매일의 시간대별 일과. 언제 들어가도 '지금'이 있도록."""
import json
import random
import sqlite3


def ensure_schedule(c: sqlite3.Connection, avatar_id: int, scenario: dict, day: str) -> list:
    row = c.execute(
        "SELECT slots_json FROM schedules WHERE avatar_id=? AND day=?", (avatar_id, day)
    ).fetchone()
    if row:
        return json.loads(row["slots_json"])

    rng = random.Random(f"{avatar_id}:{day}")
    slots = [dict(s) for s in scenario["schedule"]]
    # 날마다 약간의 변주 — 한 슬롯을 흔들어 살아있는 느낌을 준다
    if len(slots) > 3 and rng.random() < 0.7:
        i = rng.randrange(1, len(slots) - 1)
        variations = [
            "예정에 없던 손님이 찾아온다",
            "날씨가 바뀌어 일정을 조금 미룬다",
            "동료와 길게 이야기를 나눈다",
            "오래 미뤄둔 일을 손본다",
        ]
        slots[i] = {"t": slots[i]["t"], "what": slots[i]["what"] + " — " + rng.choice(variations)}

    c.execute(
        "INSERT INTO schedules (avatar_id, day, slots_json) VALUES (?,?,?)",
        (avatar_id, day, json.dumps(slots, ensure_ascii=False)),
    )
    return slots


def current_slot(slots: list, hhmm: str) -> dict:
    """현재 시각에 해당하는 일과. 첫 슬롯 이전/마지막 이후는 잠."""
    current = None
    for s in slots:
        if s["t"] <= hhmm:
            current = s
    if current is None or hhmm >= "23:00" or hhmm < slots[0]["t"]:
        return {"t": hhmm, "what": "깊이 잠들어 있다", "sleeping": True}
    if "잠자리" in current["what"] or "취침" in current["what"]:
        return {**current, "sleeping": True}
    return current
