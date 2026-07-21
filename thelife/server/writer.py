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
    style_sample: str = ""             # 문체 표본 — 넣으면 그 결을 학습한다
    total_chapters: int = 25


class ChapterBody(BaseModel):
    directive: str = ""


class StyleBody(BaseModel):
    sample: str


def analyze_style(sample: str) -> str:
    """문체 표본에서 문체 프로파일을 학습한다 — 결을 배우되 문장은 배우지 않는다."""
    sample = sample.strip()[:6000]
    mock = ("- 시점: 3인칭 제한 시점\n- 문장: 짧고 리듬감 있게, 한 문단 3문장 이내\n"
            "- 묘사: 감각 중심, 감정은 행동으로\n- 대화: 짧은 주고받기, 군더더기 없는 어미")
    prompt = f"""아래 글의 문체를 분석해 '문체 프로파일'을 작성하라. 다른 작가가 이 프로파일만 보고
같은 결의 글을 쓸 수 있어야 한다.

[표본]
{sample}

다음 항목을 불릿으로, 각 1~2줄씩 구체적으로:
- 시점과 서술 거리
- 문장 길이와 리듬 (짧은 문장/긴 문장의 비율, 문단의 호흡)
- 어휘의 결 (한자어/고유어, 격식, 시대감)
- 묘사 방식 (감각의 사용, 밀도, 은유의 빈도)
- 대화 처리 (어미, 말줄임, 대화와 지문의 비율)
- 이 작가만의 특징적 기법 2~3가지 (예: 단문 연타로 긴장 조성, 문단 끝 명사 종결)
- 피해야 할 것 (이 문체와 어긋나는 습관)

주의: 표본의 문장이나 표현을 인용·복제하지 마라. 결(스타일)만 추출하라. 프로파일만 출력."""
    return llm.write(prompt, mock_text=mock, max_tokens=1500)


@router.post("/works/{work_id}/style")
def learn_style(work_id: int, body: StyleBody,
                user: str = Header(default="solo", alias="X-User-Id")):
    """문체 학습 — 표본을 넣으면 이 작품의 모든 회차가 그 결로 쓰인다."""
    sample = body.sample.strip()
    if len(sample) < 300:
        return {"ok": False, "error": "문체를 배우려면 표본이 300자는 넘어야 해요. 더 길게 붙여넣어 주세요."}
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        profile = analyze_style(sample)
        c.execute("UPDATE works SET style_sample=?, style_profile=? WHERE id=?",
                  (sample[:6000], profile, work_id))
    return {"ok": True, "profile": profile}


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
- **역사 고증 절대 규칙**: 실존 인물·역사 배경이 등장하면 인명(휘)·묘호·호칭·
  인물 관계를 실제 역사대로 정확히 써라. 서로 다른 인물의 이름을 혼동하는 것은
  중대한 오류다 (예: 단종의 휘는 '이홍위'이고, '이유'는 그의 숙부 세조의 휘다).
  휘가 불확실하면 지어내지 말고 잘 알려진 호칭(단종, 노산군 등)을 써라.
- 출력은 들여쓰기 없는 압축 JSON으로.
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
            last_raw = llm.write(_setup_prompt(body), mock_text="", max_tokens=16000)
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

    # 문체 표본이 함께 오면 생성 시점에 학습한다
    sample = body.style_sample.strip()
    profile = analyze_style(sample) if len(sample) >= 300 else ""

    with db.connect() as c:
        work_id = c.insert_id(
            "INSERT INTO works (user_id, title, genre, premise, ending, style, total_chapters, "
            "style_sample, style_profile, characters_json, relations_json, beats_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (user, plan.get("title") or body.title or "무제", body.genre, body.premise,
             body.ending, plan.get("style") or body.style, max(5, body.total_chapters),
             sample[:6000], profile,
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
                "work": {k: w.get(k) for k in ("id", "title", "genre", "premise", "ending",
                                               "style", "total_chapters", "characters",
                                               "relations", "beats",
                                               "style_profile", "style_sample")},
                "chapters": chapters}


class BibleBody(BaseModel):
    title: str = ""
    ending: str = ""
    characters: list = []
    relations: list = []
    beats: list = []


def _normalize_beats(beats: list) -> list:
    """비트 이름과 순서는 시스템이 보증한다 — 요약만 작가/LLM의 것."""
    by_idx = {}
    for i, x in enumerate(beats or []):
        if isinstance(x, dict):
            by_idx[int(x.get("idx", i))] = x
    return [{"idx": i, "name": n, "summary": (by_idx.get(i) or {}).get("summary", "")}
            for i, n in enumerate(BEATS)]


@router.put("/works/{work_id}/bible")
def edit_bible(work_id: int, body: BibleBody,
               user: str = Header(default="solo", alias="X-User-Id")):
    """설정집 직접 편집 — 여기 고친 것이 이후 모든 회차의 진실이 된다."""
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        c.execute(
            "UPDATE works SET title=?, ending=?, characters_json=?, relations_json=?, "
            "beats_json=? WHERE id=?",
            (body.title.strip() or w["title"],
             body.ending.strip() or w["ending"],
             json.dumps(body.characters or w["characters"], ensure_ascii=False),
             json.dumps(body.relations or w["relations"], ensure_ascii=False),
             json.dumps(_normalize_beats(body.beats or w["beats"]), ensure_ascii=False),
             work_id),
        )
    return {"ok": True}


class ReviseBody(BaseModel):
    directive: str


@router.post("/works/{work_id}/bible/revise")
def revise_bible(work_id: int, body: ReviseBody,
                 user: str = Header(default="solo", alias="X-User-Id")):
    """명령으로 설정집 수정 — '주인공 이름을 이홍위로 바꿔' 한 줄이면 된다."""
    directive = body.directive.strip()
    if not directive:
        return {"ok": False, "error": "무엇을 고칠지 알려주세요."}
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
    if llm.is_mock:
        return {"ok": False, "error": "명령 수정에는 AI 연결이 필요해요. (API 키 설정 확인)"}

    current = {"title": w["title"], "ending": w["ending"],
               "characters": w["characters"], "relations": w["relations"],
               "beats": w["beats"]}
    prompt = f"""웹소설 설정집을 작가의 명령대로 수정하라.

[현재 설정집]
{json.dumps(current, ensure_ascii=False, separators=(",", ":"))}

[작가의 명령] {directive}

규칙:
- 명령이 요구한 것만 바꾸고 나머지는 그대로 보존하라.
- 인물 이름을 바꾸면 관계도(relations)와 비트 요약(beats) 속의 그 이름도 전부 갱신하라.
- 실존 인물·역사 배경이면 인명(휘)·호칭·관계를 실제 역사대로 정확히 고증하라.
- beats는 15개, name은 그대로 유지하고 summary만 수정 가능하다.
- 출력은 같은 구조의 JSON 하나만. **들여쓰기·불필요한 공백 없는 압축 JSON**으로,
  반드시 '{{'로 시작해 '}}'로 끝나라. 설명·코드펜스 금지."""
    plan, last_raw = None, ""
    for _ in range(2):
        last_raw = llm.write(prompt, mock_text="", max_tokens=16000)
        plan = parse_llm_json(last_raw)
        if plan and plan.get("characters"):
            break
        plan = None
    if plan is None:
        print(f"[writer] 설정 수정 실패. 응답 앞부분: {last_raw[:300]}", flush=True)
        hint = (f"AI 호출 오류 — {llm.last_error}" if llm.last_error
                else ("응답이 비어 있음 — API 키/사용량 한도 확인" if not last_raw.strip()
                      else f"형식 오류 (응답 앞부분: {last_raw[:120]})"))
        return {"ok": False, "error": "수정에 실패했어요. 명령을 조금 다르게 써서 다시 시도해 주세요.",
                "detail": hint}

    with db.connect() as c:
        c.execute(
            "UPDATE works SET title=?, ending=?, characters_json=?, relations_json=?, "
            "beats_json=? WHERE id=?",
            (plan.get("title") or w["title"], plan.get("ending") or w["ending"],
             json.dumps(plan.get("characters"), ensure_ascii=False),
             json.dumps(plan.get("relations") or w["relations"], ensure_ascii=False),
             json.dumps(_normalize_beats(plan.get("beats") or w["beats"]), ensure_ascii=False),
             work_id),
        )
    return {"ok": True}


@router.get("/chapters/{chapter_id}")
def get_chapter(chapter_id: int, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        r = c.execute(
            "SELECT ch.* FROM chapters ch JOIN works w ON w.id = ch.work_id "
            "WHERE ch.id=? AND w.user_id=?", (chapter_id, user)).fetchone()
        return {"ok": bool(r), "chapter": dict(r) if r else None}


def _style_block(w: dict) -> str:
    """작품의 문체 지침 — 학습된 프로파일과 표본 발췌가 있으면 최우선."""
    parts = []
    if w.get("style_profile"):
        parts.append(f"[학습된 문체 프로파일 — 이 결로 써라]\n{w['style_profile']}")
    if w.get("style_sample"):
        excerpt = w["style_sample"][:700]
        parts.append(f"[문체 표본 발췌 — 이 호흡과 결을 모사하되, 문장·표현을 그대로 베끼는 것은 절대 금지]\n{excerpt}")
    if w.get("style"):
        parts.append(f"[문체 메모] {w['style']}")
    return "\n".join(parts) if parts else "[문체] 속도감 있는 웹소설 문체"


DESCRIPTION_RULES = """- **묘사는 집요하게 디테일하라 (필수)**:
  · 장면마다 오감 중 최소 세 가지를 구체적으로 (빛의 각도, 소리의 질감, 냄새, 온도, 살갗의 감각)
  · 뭉뚱그리지 마라 — '방'이 아니라 '창호지가 반쯤 뜯긴 북쪽 들창', '칼'이 아니라 '날이 한 뼘쯤 이가 나간 환도'
  · 감정은 명사로 말하지 말고 몸으로 보여줘라 — '두려웠다' 대신 떨리는 손끝, 마른침, 좁아지는 시야
  · 단, 묘사가 속도를 죽이면 안 된다 — 긴 묘사 덩어리 대신 행동 사이사이에 짧고 선명하게 박아라"""


def _prev_state(prev: list) -> dict:
    """직전 화의 상태 원장 — 인물 심경·이야기 내 시간·최근 사용 표현."""
    state = {}
    if prev and prev[-1].get("state_json"):
        try:
            state = json.loads(prev[-1]["state_json"]) or {}
        except Exception:
            state = {}
    phrases = []
    for p in prev[-3:]:
        try:
            st = json.loads(p.get("state_json") or "{}") or {}
            phrases += [x for x in (st.get("phrases") or []) if isinstance(x, str)]
        except Exception:
            pass
    state["banned_phrases"] = phrases[-15:]
    return state


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

    st = _prev_state(prev)
    time_line = st.get("time_end", "")
    char_states = "\n".join(
        f"- {c.get('name','')}: 심경 {c.get('mood','')} / 위치 {c.get('loc','')} / {c.get('change','')}"
        for c in (st.get("chars") or []) if isinstance(c, dict)) or "1화 — 설정집의 초기 상태에서 시작"
    banned = " / ".join(st.get("banned_phrases") or [])

    return f"""당신은 정상급 웹소설 작가다. 아래 작품의 {no}화를 써라.

[작품] {w['title']} ({w['genre']}) — 총 {w['total_chapters']}화 예정
[로그라인] {w['premise']}
[고정된 결말 — 전체 이야기는 반드시 여기 도달한다] {w['ending']}
{_style_block(w)}

[인물 설정 — 이름·성격·설정을 절대 어기지 마라]
{chars}
[관계도]
{rels}

[전체 플롯 지도 (Save the Cat 15비트)]
{beats_map}

[이번 화의 위치] {no}화 = 비트 "{beat['name']}" — {beat.get('summary','')}
[지금까지의 전개 (요약)]
{prev_txt}
[인물의 현재 상태 — 이 심경과 위치에서 '이어서' 출발하라]
{char_states}
{f'[이야기 속 시간] 직전 화는 「{time_line}」에 끝났다. 이번 화는 반드시 그 이후이며, 경과 시간이 사건과 아귀가 맞아야 한다.' if time_line else '[이야기 속 시간] 1화 — 이야기의 시간 기점을 이번 화에서 명확히 세워라.'}
{f'[직전 화의 마지막 대목] …{last_tail}' if last_tail else ''}
{f'[금지 표현 — 최근 화에서 이미 사용했다. 같은 표현·비유·대사 반복 금지] {banned}' if banned else ''}
{f'[작가의 지시 — 최우선으로 따르라] {directive}' if directive else ''}

집필 규칙:
- **분량: 공백 포함 5,000자 이상 (5,000~6,000자). 웹소설 연재 1회분의 국룰이다.
  장면 3~4개로 구성하면 자연히 채워진다 — 장면마다 장소·시간·긴장이 달라야 한다.**
{DESCRIPTION_RULES}
- **인물 일관성 절대 규칙**: 인물의 말투·가치관·습관은 설정집과 [인물의 현재 상태]를
  따르라. 심경이 변한다면 반드시 이번 화의 사건이 그 원인이어야 하고, 변화의 과정을
  몸짓과 대사로 단계적으로 보여줘라. 원인 없는 급변은 중대한 오류다.
- **시간 일관성 절대 규칙**: 낮과 밤, 이동에 걸리는 시간, 계절이 앞뒤가 맞아야 한다.
  한나절 거리를 순간이동하거나, 밤에 시작한 장면이 설명 없이 낮이 되면 안 된다.
- 역사물이라면 인명·연호·관직·물건의 고증을 지켜라. 그 시대에 없는 것은 등장 금지.
- 이번 화는 현재 비트의 역할을 수행하되, 전체 결말을 향해 한 걸음 전진해야 한다.
- 대화 비중 높게, 문단은 짧게, 속도감 있게. 고구마는 짧게, 사이다는 확실하게.
- 같은 단어·문형을 한 화 안에서도 반복하지 마라. 특히 상투적 감탄·추임새 반복 금지.
- 마지막 문장은 절단신공 — 다음 화를 누를 수밖에 없는 순간에서 끊어라.

출력 형식 (정확히 지켜라):
제목: (이번 화 제목)
(본문)
///요약///
(이번 화에서 벌어진 일과 인물 상태 변화를 4~6문장으로 — 다음 화 집필용 기억)
///상태///
{{"time_start":"이번 화가 시작된 이야기 속 시점","time_end":"끝난 시점","chars":[{{"name":"인물명","mood":"현재 심경","loc":"현재 위치","change":"이번 화에서 달라진 것"}}],"phrases":["이번 화에서 쓴 인상적 표현·비유 5개 — 다음 화 반복 방지용"]}}"""


def _mock_chapter(w: dict, no: int, beat: dict) -> str:
    return (f"제목: {no}화 — {beat['name']}\n"
            f"{w['title']}의 {no}화. {beat.get('summary','이야기가 전개된다.')}\n"
            "서진은 주먹을 쥐었다.\n\"여기서 물러서면, 전부 끝이야.\"\n"
            "그 순간, 문이 열렸다. 들어선 사람의 얼굴을 본 서진의 눈이 크게 흔들렸다.\n"
            "///요약///\n"
            f"{no}화: {beat['name']} 단계가 진행됐고, 마지막에 뜻밖의 인물이 등장했다.\n"
            "///상태///\n"
            + json.dumps({"time_start": f"{no}일째 아침", "time_end": f"{no}일째 밤",
                          "chars": [{"name": "서진", "mood": "결연함", "loc": "본가",
                                     "change": "물러서지 않기로 결심"}],
                          "phrases": ["주먹을 쥐었다", "눈이 크게 흔들렸다"]},
                         ensure_ascii=False))


def _generate_full_chapter(w: dict, no: int, beat: dict, prev: list, directive: str):
    """회차 생성 + 분량 보증 루프 — 5,000자에 못 미치면 프로그램이 이어쓰기를 시킨다."""
    raw = llm.write(_chapter_prompt(w, no, beat, prev, directive),
                    mock_text=_mock_chapter(w, no, beat), max_tokens=16000)
    title, text, summary, state = _parse_chapter(raw, no)
    tries = 0
    while not llm.is_mock and len(text) < MIN_CHAPTER_CHARS and tries < 2:
        cont = llm.write(_continue_prompt(w, no, beat, text, directive),
                         mock_text="", max_tokens=16000)
        if not cont.strip():
            break
        _, more, s2, st2 = _parse_chapter(cont, no)
        if not more.strip():
            break
        text = text.rstrip() + "\n\n" + more.strip()
        if s2:
            summary = s2
        if st2:
            state = st2
        tries += 1
    return title, text, summary, state


@router.post("/works/{work_id}/chapters")
def write_chapter(work_id: int, body: ChapterBody,
                  user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        prev = [dict(r) for r in c.execute(
            "SELECT no, title, summary, body, state_json FROM chapters WHERE work_id=? ORDER BY no",
            (work_id,)).fetchall()]
        no = (prev[-1]["no"] + 1) if prev else 1
        if no > w["total_chapters"]:
            return {"ok": False, "error": "예정된 회차를 모두 썼어요. 총 회차 수를 늘리거나 완결하세요."}
        beat = w["beats"][beat_for(no, w["total_chapters"])]

        title, text, summary, state = _generate_full_chapter(
            w, no, beat, prev, body.directive.strip())
        ch_id = c.insert_id(
            "INSERT INTO chapters (work_id, no, title, body, summary, state_json, directive, "
            "beat_idx, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
            (work_id, no, title, text, summary, state, body.directive.strip(),
             beat_for(no, w["total_chapters"])),
        )
        return {"ok": True, "id": ch_id, "no": no, "chars": len(text)}


def _parse_chapter(raw: str, no: int):
    """제목 / 본문 / 요약 / 상태(JSON 문자열)로 분해한다."""
    title, summary, state = f"{no}화", "", ""
    text = raw.strip()
    if "///상태///" in text:
        text, state_raw = text.rsplit("///상태///", 1)
        st = parse_llm_json(state_raw.strip())
        state = json.dumps(st, ensure_ascii=False) if st else ""
    if "///요약///" in text:
        text, summary = text.rsplit("///요약///", 1)
        summary = summary.strip()
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("제목:"):
        title = lines[0].split(":", 1)[1].strip() or title
        lines = lines[1:]
    return title, "\n".join(lines).strip(), summary, state


MIN_CHAPTER_CHARS = 4300  # 이 밑이면 프로그램이 이어쓰기를 시킨다 (목표 5,000+)


def _continue_prompt(w: dict, no: int, beat: dict, body_so_far: str, directive: str) -> str:
    return f"""당신은 정상급 웹소설 작가다. 아래는 {w['title']} {no}화의 앞부분이다.
현재 {len(body_so_far)}자인데 연재 1회분(공백 포함 5,000자 이상)이 되려면 부족하다.
같은 화의 연속으로, 끊긴 지점에서 자연스럽게 이어서 써라.

{_style_block(w)}
[이번 화의 비트] {beat['name']} — {beat.get('summary','')}
{f'[작가의 지시] {directive}' if directive else ''}
[지금까지의 본문 마지막 대목]
…{body_so_far[-1200:]}

규칙:
- 이어지는 본문만 써라. 제목·앞부분 반복 금지. 이미 쓴 표현·대사 반복 금지.
{DESCRIPTION_RULES}
- 새 장면 1~2개를 더해 긴장을 키우고, 마지막 문장은 절단신공으로 끝내라.

출력 형식:
(이어지는 본문)
///요약///
(화 '전체' 기준 요약 4~6문장)
///상태///
{{"time_start":"...","time_end":"...","chars":[{{"name":"...","mood":"...","loc":"...","change":"..."}}],"phrases":["..."]}}"""


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
            "SELECT no, title, summary, body, state_json FROM chapters WHERE work_id=? AND no<? ORDER BY no",
            (r["work_id"], r["no"])).fetchall()]
        beat = w["beats"][beat_for(r["no"], w["total_chapters"])]
        title, text, summary, state = _generate_full_chapter(
            w, r["no"], beat, prev, body.directive.strip())
        c.execute("UPDATE chapters SET title=?, body=?, summary=?, state_json=?, directive=?, "
                  "updated_at=datetime('now') WHERE id=?",
                  (title, text, summary, state, body.directive.strip(), chapter_id))
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
