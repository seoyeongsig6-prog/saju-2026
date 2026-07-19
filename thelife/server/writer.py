"""The Novelist — 작가용 웹소설 집필 도구 (The Life의 형제 앱).

검증된 서사 구조 위에서 쓴다:
- 플롯: Save the Cat 15비트 → 작가가 고정한 결말로 흘러가는 회차 지도
- 인물: 보글러의 원형(아키타입) + 외적 욕망(want)/내적 결핍(need)/비밀
- 관계도: 인물 쌍마다 관계 유형과 긴장도
작가가 지시하고, 고치고, 다시 쓴다 — 여기서는 조작이 전부다.
"""
import json

from fastapi import APIRouter, Header
from pydantic import BaseModel

from . import db
from .engine.world import parse_llm_json
from .llm import llm

router = APIRouter(prefix="/api/writer")

BEATS = [
    "오프닝 이미지", "주제 제시", "설정", "계기(촉발 사건)", "고민",
    "1막 전환(결단)", "B스토리", "재미와 게임", "중간점", "조여오는 악당",
    "모든 것을 잃다", "영혼의 어두운 밤", "3막 전환(해결의 실마리)",
    "피날레", "파이널 이미지",
]
# Save the Cat 표준 배치 비율 — 회차 진행률이 이 지점을 넘으면 다음 비트로
BEAT_EDGES = [0.02, 0.05, 0.10, 0.12, 0.20, 0.22, 0.26, 0.50, 0.55,
              0.75, 0.78, 0.81, 0.84, 0.99, 1.01]

ARCHETYPES = "영웅(주인공), 그림자(적대자), 멘토, 조력자, 애정상대, 전령, 관문수호자, 변신자재자"


def beat_for(no: int, total: int) -> int:
    frac = no / max(total, 1)
    for i, edge in enumerate(BEAT_EDGES):
        if frac <= edge:
            return i
    return len(BEATS) - 1


class WorkBody(BaseModel):
    genre: str = "현대 판타지"
    premise: str                       # 로그라인
    ending: str                        # 고정된 결말
    title: str = ""
    style: str = ""
    total_chapters: int = 25


class ChapterBody(BaseModel):
    directive: str = ""


class EditBody(BaseModel):
    title: str = ""
    body: str = ""


def _setup_prompt(b: WorkBody) -> str:
    schema = {
        "title": "작품 제목 (미정이면 창작)",
        "style": "문체 지침 한 줄",
        "characters": [{"name": "이름", "archetype": "원형", "role": "한 줄 소개",
                        "want": "외적 욕망 — 겉으로 쫓는 것",
                        "need": "내적 결핍 — 진짜 필요한 것", "secret": "비밀 하나"}],
        "relations": [{"a": "인물", "b": "인물", "type": "관계 (사제/연적/혈연/원수...)",
                       "tension": "둘 사이의 긴장 한 줄"}],
        "beats": [{"idx": 0, "name": BEATS[0], "summary": "이 비트에서 벌어질 일 2~3문장"}],
    }
    return f"""당신은 웹소설 스토리 설계자다. 아래 작품의 설계도를 JSON으로 만들어라.

[장르] {b.genre}
[로그라인] {b.premise}
[고정된 결말 — 이야기는 반드시 이곳에 도달한다] {b.ending}
[총 회차] {b.total_chapters}화
{f'[제목] {b.title}' if b.title else ''}
{f'[문체] {b.style}' if b.style else ''}

JSON 스키마 (다른 텍스트 없이 JSON만):
{json.dumps(schema, ensure_ascii=False, indent=1)}

요구사항:
- characters: 보글러 원형({ARCHETYPES}) 기반 5~7명.
  영웅과 그림자(적대자)는 필수. 각 인물의 want와 need는 서로 어긋나야 입체적이다.
- relations: 주요 인물 쌍 4~6개. 긴장 없는 관계는 넣지 마라.
- beats: Save the Cat 15비트 전부. name은 이 순서 그대로: {', '.join(BEATS)}.
  각 비트의 summary는 로그라인과 결말에 정확히 정렬되어야 한다 —
  특히 '피날레'와 '파이널 이미지'는 고정된 결말을 실현해야 한다.
- 웹소설 문법: 고구마(답답함)는 짧게, 사이다(해소)는 확실하게."""


def _mock_setup(b: WorkBody) -> dict:
    return {
        "title": b.title or f"{b.genre}의 밤",
        "style": b.style or "속도감 있는 문장. 대화 중심.",
        "characters": [
            {"name": "서진", "archetype": "영웅", "role": "밑바닥에서 시작하는 주인공",
             "want": "성공", "need": "자신을 용서하는 것", "secret": "과거의 사고"},
            {"name": "칸", "archetype": "그림자", "role": "모든 것을 가진 적대자",
             "want": "지배", "need": "인정", "secret": "몰락의 씨앗"},
            {"name": "노인", "archetype": "멘토", "role": "은둔한 스승",
             "want": "평온", "need": "속죄", "secret": "서진 과거와의 연결"},
        ],
        "relations": [
            {"a": "서진", "b": "칸", "type": "원수", "tension": "같은 것을 원한다"},
            {"a": "서진", "b": "노인", "type": "사제", "tension": "숨겨진 과거"},
        ],
        "beats": [{"idx": i, "name": n, "summary": f"{n} 단계의 사건이 전개된다."}
                  for i, n in enumerate(BEATS)],
    }


@router.post("/works")
def create_work(body: WorkBody, user: str = Header(default="solo", alias="X-User-Id")):
    if not body.premise.strip() or not body.ending.strip():
        return {"ok": False, "error": "로그라인과 결말은 작가만 정할 수 있어요. 두 칸을 채워주세요."}
    plan, last_raw = None, ""
    if not llm.is_mock:
        for _ in range(2):
            last_raw = llm.write(_setup_prompt(body), mock_text="", max_tokens=8000)
            plan = parse_llm_json(last_raw)
            if plan and plan.get("characters") and plan.get("beats"):
                break
            plan = None
    if plan is None:
        if llm.is_mock:
            plan = _mock_setup(body)
        else:
            hint = ("응답이 비어 있음 — API 키/모델 설정 확인 필요"
                    if not last_raw.strip() else f"형식 오류 (응답 앞부분: {last_raw[:120]})")
            return {"ok": False, "error": "설계도 생성에 실패했어요. 한 번 더 시도해 주세요.",
                    "detail": hint}

    beats = plan.get("beats") or []
    if len(beats) != len(BEATS):  # 비트 이름은 시스템이 보증한다
        by_idx = {int(x.get("idx", i)): x for i, x in enumerate(beats)}
        beats = [{"idx": i, "name": n, "summary": (by_idx.get(i) or {}).get("summary", "")}
                 for i, n in enumerate(BEATS)]
    else:
        for i, x in enumerate(beats):
            x["idx"], x["name"] = i, BEATS[i]

    with db.connect() as c:
        work_id = c.insert_id(
            "INSERT INTO works (user_id, title, genre, premise, ending, style, total_chapters, "
            "characters_json, relations_json, beats_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (user, plan.get("title") or body.title or "무제", body.genre, body.premise,
             body.ending, plan.get("style") or body.style, max(5, body.total_chapters),
             json.dumps(plan.get("characters", []), ensure_ascii=False),
             json.dumps(plan.get("relations", []), ensure_ascii=False),
             json.dumps(beats, ensure_ascii=False)),
        )
    return {"ok": True, "id": work_id}


def _load_work(c, work_id: int, user: str):
    row = c.execute("SELECT * FROM works WHERE id=? AND user_id=?", (work_id, user)).fetchone()
    if not row:
        return None
    w = dict(row)
    w["characters"] = json.loads(w.get("characters_json") or "[]")
    w["relations"] = json.loads(w.get("relations_json") or "[]")
    w["beats"] = json.loads(w.get("beats_json") or "[]")
    return w


@router.get("/works")
def list_works(user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        out = []
        for r in c.execute("SELECT id, title, genre, total_chapters FROM works "
                           "WHERE user_id=? ORDER BY id DESC", (user,)).fetchall():
            n = c.execute("SELECT COUNT(*) AS n FROM chapters WHERE work_id=?",
                          (r["id"],)).fetchone()["n"]
            out.append({**dict(r), "written": n})
        return {"works": out}


@router.get("/works/{work_id}")
def get_work(work_id: int, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        chapters = [dict(r) for r in c.execute(
            "SELECT id, no, title, beat_idx, directive FROM chapters WHERE work_id=? ORDER BY no",
            (work_id,)).fetchall()]
        return {"ok": True,
                "work": {k: w[k] for k in ("id", "title", "genre", "premise", "ending",
                                           "style", "total_chapters", "characters",
                                           "relations", "beats")},
                "chapters": chapters}


@router.get("/chapters/{chapter_id}")
def get_chapter(chapter_id: int, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        r = c.execute(
            "SELECT ch.* FROM chapters ch JOIN works w ON w.id = ch.work_id "
            "WHERE ch.id=? AND w.user_id=?", (chapter_id, user)).fetchone()
        return {"ok": bool(r), "chapter": dict(r) if r else None}


def _chapter_prompt(w: dict, no: int, beat: dict, prev: list, directive: str) -> str:
    chars = "\n".join(
        f"- {ch['name']} ({ch.get('archetype','')}): {ch.get('role','')} / "
        f"욕망: {ch.get('want','')} / 결핍: {ch.get('need','')} / 비밀: {ch.get('secret','')}"
        for ch in w["characters"])
    rels = "\n".join(f"- {r['a']} ↔ {r['b']}: {r.get('type','')} — {r.get('tension','')}"
                     for r in w["relations"])
    beats_map = "\n".join(f"{i+1}. {b['name']}: {b.get('summary','')}"
                          for i, b in enumerate(w["beats"]))
    prev_txt = "\n".join(f"[{p['no']}화 {p['title']}] {p['summary']}" for p in prev[-8:]) or "없음(1화)"
    last_tail = prev[-1]["body"][-600:] if prev else ""

    return f"""당신은 정상급 웹소설 작가다. 아래 작품의 {no}화를 써라.

[작품] {w['title']} ({w['genre']}) — 총 {w['total_chapters']}화 예정
[로그라인] {w['premise']}
[고정된 결말 — 전체 이야기는 반드시 여기 도달한다] {w['ending']}
[문체] {w.get('style','')}

[인물 설정 — 이름·성격·설정을 절대 어기지 마라]
{chars}
[관계도]
{rels}

[전체 플롯 지도 (Save the Cat 15비트)]
{beats_map}

[이번 화의 위치] {no}화 = 비트 "{beat['name']}" — {beat.get('summary','')}
[지금까지의 전개 (요약)]
{prev_txt}
{f'[직전 화의 마지막 대목] …{last_tail}' if last_tail else ''}
{f'[작가의 지시 — 최우선으로 따르라] {directive}' if directive else ''}

집필 규칙:
- 분량: 공백 포함 4,500~5,500자. 웹소설 연재 1회분이다. 반드시 채워라.
- 이번 화는 현재 비트의 역할을 수행하되, 전체 결말을 향해 한 걸음 전진해야 한다.
- 대화 비중 높게, 문단은 짧게, 속도감 있게. 고구마는 짧게, 사이다는 확실하게.
- 마지막 문장은 절단신공 — 다음 화를 누를 수밖에 없는 순간에서 끊어라.
- 이전 화 요약과 모순 금지 (인물의 위치·상태·알고 있는 정보).

출력 형식 (정확히 지켜라):
제목: (이번 화 제목)
(본문)
///요약///
(이번 화에서 벌어진 일과 인물 상태 변화를 4~6문장으로 — 다음 화 집필용 기억)"""


def _mock_chapter(w: dict, no: int, beat: dict) -> str:
    return (f"제목: {no}화 — {beat['name']}\n"
            f"{w['title']}의 {no}화. {beat.get('summary','이야기가 전개된다.')}\n"
            "서진은 주먹을 쥐었다.\n\"여기서 물러서면, 전부 끝이야.\"\n"
            "그 순간, 문이 열렸다. 들어선 사람의 얼굴을 본 서진의 눈이 크게 흔들렸다.\n"
            "///요약///\n"
            f"{no}화: {beat['name']} 단계가 진행됐고, 마지막에 뜻밖의 인물이 등장했다.")


@router.post("/works/{work_id}/chapters")
def write_chapter(work_id: int, body: ChapterBody,
                  user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        prev = [dict(r) for r in c.execute(
            "SELECT no, title, summary, body FROM chapters WHERE work_id=? ORDER BY no",
            (work_id,)).fetchall()]
        no = (prev[-1]["no"] + 1) if prev else 1
        if no > w["total_chapters"]:
            return {"ok": False, "error": "예정된 회차를 모두 썼어요. 총 회차 수를 늘리거나 완결하세요."}
        beat = w["beats"][beat_for(no, w["total_chapters"])]

        raw = llm.write(_chapter_prompt(w, no, beat, prev, body.directive.strip()),
                        mock_text=_mock_chapter(w, no, beat), max_tokens=8000)
        title, text, summary = _parse_chapter(raw, no)
        ch_id = c.insert_id(
            "INSERT INTO chapters (work_id, no, title, body, summary, directive, beat_idx, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
            (work_id, no, title, text, summary, body.directive.strip(),
             beat_for(no, w["total_chapters"])),
        )
        return {"ok": True, "id": ch_id, "no": no}


def _parse_chapter(raw: str, no: int):
    title, summary = f"{no}화", ""
    text = raw.strip()
    if "///요약///" in text:
        text, summary = text.rsplit("///요약///", 1)
        summary = summary.strip()
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("제목:"):
        title = lines[0].split(":", 1)[1].strip() or title
        lines = lines[1:]
    return title, "\n".join(lines).strip(), summary


@router.post("/chapters/{chapter_id}/regenerate")
def regen_chapter(chapter_id: int, body: ChapterBody,
                  user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        r = c.execute(
            "SELECT ch.no, ch.work_id FROM chapters ch JOIN works w ON w.id = ch.work_id "
            "WHERE ch.id=? AND w.user_id=?", (chapter_id, user)).fetchone()
        if not r:
            return {"ok": False, "error": "회차를 찾을 수 없어요."}
        w = _load_work(c, r["work_id"], user)
        prev = [dict(x) for x in c.execute(
            "SELECT no, title, summary, body FROM chapters WHERE work_id=? AND no<? ORDER BY no",
            (r["work_id"], r["no"])).fetchall()]
        beat = w["beats"][beat_for(r["no"], w["total_chapters"])]
        raw = llm.write(_chapter_prompt(w, r["no"], beat, prev, body.directive.strip()),
                        mock_text=_mock_chapter(w, r["no"], beat), max_tokens=8000)
        title, text, summary = _parse_chapter(raw, r["no"])
        c.execute("UPDATE chapters SET title=?, body=?, summary=?, directive=?, "
                  "updated_at=datetime('now') WHERE id=?",
                  (title, text, summary, body.directive.strip(), chapter_id))
    return {"ok": True}


@router.put("/chapters/{chapter_id}")
def edit_chapter(chapter_id: int, body: EditBody,
                 user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        r = c.execute(
            "SELECT ch.id FROM chapters ch JOIN works w ON w.id = ch.work_id "
            "WHERE ch.id=? AND w.user_id=?", (chapter_id, user)).fetchone()
        if not r:
            return {"ok": False, "error": "회차를 찾을 수 없어요."}
        c.execute("UPDATE chapters SET title=?, body=?, updated_at=datetime('now') WHERE id=?",
                  (body.title, body.body, chapter_id))
    return {"ok": True}


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: int, user: str = Header(default="solo", alias="X-User-Id")):
    """마지막 회차만 삭제 가능 — 중간을 비우면 기억이 끊긴다."""
    with db.connect() as c:
        r = c.execute(
            "SELECT ch.no, ch.work_id FROM chapters ch JOIN works w ON w.id = ch.work_id "
            "WHERE ch.id=? AND w.user_id=?", (chapter_id, user)).fetchone()
        if not r:
            return {"ok": False, "error": "회차를 찾을 수 없어요."}
        last = c.execute("SELECT MAX(no) AS m FROM chapters WHERE work_id=?",
                         (r["work_id"],)).fetchone()["m"]
        if r["no"] != last:
            return {"ok": False, "error": "마지막 회차만 지울 수 있어요."}
        c.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
    return {"ok": True}


@router.delete("/works/{work_id}")
def delete_work(work_id: int, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        if not c.execute("SELECT id FROM works WHERE id=? AND user_id=?",
                         (work_id, user)).fetchone():
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        c.execute("DELETE FROM chapters WHERE work_id=?", (work_id,))
        c.execute("DELETE FROM works WHERE id=?", (work_id,))
    return {"ok": True}
