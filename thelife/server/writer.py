"""The Novelist — 작가용 웹소설 집필 도구 (The Life의 형제 앱).

검증된 서사 구조 위에서 쓴다:
- 플롯: Save the Cat 15비트 → 작가가 고정한 결말로 흘러가는 회차 지도
- 인물: 보글러의 원형(아키타입) + 외적 욕망(want)/내적 결핍(need)/비밀
- 관계도: 인물 쌍마다 관계 유형과 긴장도
작가가 지시하고, 고치고, 다시 쓴다 — 여기서는 조작이 전부다.
"""
import datetime
import io
import json
import os
import re
import uuid

from fastapi import APIRouter, File, Form, Header, UploadFile
from pydantic import BaseModel

from . import db
from .engine.world import parse_llm_json
from .llm import llm

router = APIRouter(prefix="/api/writer")

# 판매용 런치 버전 — 소설 '본문 집필'과 거기 딸린 기능을 끈다.
# 기본은 '꺼짐'(전체 기능). 판매용 서버에서만 WRITER_LAUNCH_MODE=1 로 켠다.
# (기본값이 켜짐이면 개인 집필 서버가 코드 배포만으로 기능을 잃어 위험하다.)
LAUNCH_MODE = os.environ.get("WRITER_LAUNCH_MODE", "0") == "1"
_LAUNCH_OFF = {"ok": False, "error": "이 버전에서는 제공하지 않는 기능이에요."}


# 요금제 — 무료/라이트/프로. 질(회차 수·화당 줄거리 깊이·인물 수)로 차등한다.
TIERS = {
    "free":  {"label": "무료", "max_chapters": 3,  "syn_chars": 100,
              "max_characters": 3,  "max_works": 1,      "style_learning": False, "ads": True,
              "price": "무료", "period": "", "tagline": "가볍게 시작하기", "badge": ""},
    "light": {"label": "라이트", "max_chapters": 20, "syn_chars": 250,
              "max_characters": 7,  "max_works": 10,     "style_learning": False, "ads": False,
              "price": "₩4,900", "period": "/월", "tagline": "본격 연재 기획", "badge": "인기"},
    "pro":   {"label": "프로", "max_chapters": 70, "syn_chars": 450,
              "max_characters": 10, "max_works": 100000, "style_learning": True,  "ads": False,
              "price": "₩9,900", "period": "/월", "tagline": "프로 작가용", "badge": "추천"},
}


# 스토어 상품 ID → 등급. (앱 커넥트/플레이 콘솔에서 만든 구독 상품 ID와 맞춘다)
PRODUCT_TIER = {
    "novelist.light.monthly": "light", "novelist.light.yearly": "light",
    "novelist.pro.monthly": "pro", "novelist.pro.yearly": "pro",
}


def _entitlement(c, user: str):
    """유효한 '구매 등급' — 만료됐으면 무료로 떨어진다. 없으면 None."""
    raw = db.kv_get(c, f"ent:{user}", "")
    if not raw:
        return None
    try:
        e = json.loads(raw)
    except Exception:
        return None
    exp = e.get("expires_at")
    if exp:
        try:
            if datetime.datetime.fromisoformat(str(exp).replace("Z", "+00:00")) < \
               datetime.datetime.now(datetime.timezone.utc):
                return None  # 구독 만료 → 무료로
        except Exception:
            pass
    t = e.get("tier")
    return t if t in TIERS else None


def _tier_name(c, user: str) -> str:
    ent = _entitlement(c, user)                 # 실제 구매 등급이 최우선
    if ent:
        return ent
    t = db.kv_get(c, f"tier:{user}", "free")    # 개발용 오버라이드 (런치 빌드에선 안 쓰임)
    return t if t in TIERS else "free"


def _limits(name: str) -> dict:
    return TIERS.get(name, TIERS["free"])


# 하루 AI 호출 상한 — 비용 폭탄/남용 방지 안전망 (정상 사용엔 넉넉).
AI_DAILY_CAP = {"free": 40, "light": 250, "pro": 800}


def _ai_gate(c, user: str):
    """AI 생성 1회를 차감·검사한다. (남은 게 없으면 False)"""
    tier = _tier_name(c, user)
    cap = AI_DAILY_CAP.get(tier, 40)
    day = db.real_now().date().isoformat()   # 한국시간 자정에 리셋
    key = f"aiq:{user}:{day}"
    used = int(db.kv_get(c, key, "0") or "0")
    if used >= cap:
        return False, cap
    db.kv_set(c, key, str(used + 1))
    return True, cap


_AI_BUSY = {"ok": False, "error": "오늘 AI 생성 횟수를 다 썼어요. 내일 다시 시도하거나 요금제를 올려 주세요."}


def _clamp(s: str, n: int) -> str:
    return (s or "")[:n]


def _cap_build(b: "BuildBody") -> None:
    """과도한 입력으로 프롬프트가 비대해지는 걸 막는다 (비용·DoS 방지)."""
    b.characters = (b.characters or [])[:30]
    b.canon = (b.canon or [])[:60]
    b.outline = (b.outline or [])[:210]
    for f in ("logline", "intent", "world_setting", "world_rules", "taboos",
              "style", "style_sample", "ending", "genre", "title", "keywords"):
        setattr(b, f, _clamp(getattr(b, f, ""), 6000 if f in ("style_sample",) else 3000))


@router.get("/config")
def writer_config(user: str = Header(default="solo", alias="X-User-Id")):
    """앱이 시작할 때 기능·요금제 상태를 알려준다."""
    with db.connect() as c:
        t = _tier_name(c, user)
        ent = None
        raw = db.kv_get(c, f"ent:{user}", "")
        if raw and _entitlement(c, user):
            try:
                ent = json.loads(raw).get("expires_at")
            except Exception:
                ent = None
    return {"launch_mode": LAUNCH_MODE, "writing_enabled": not LAUNCH_MODE,
            "tier": t, "limits": TIERS[t], "tiers": TIERS, "expires_at": ent}


class TierBody(BaseModel):
    tier: str


@router.post("/tier")
def set_tier(body: TierBody, user: str = Header(default="solo", alias="X-User-Id")):
    """요금제 설정 — 개발/미리보기 전용. 판매(런치) 빌드에서는 막혀 있고,
    실제 요금제는 애플/구글 IAP 영수증 검증을 통해서만 부여된다."""
    if LAUNCH_MODE:
        return {"ok": False, "error": "요금제는 앱 내 구매로만 변경할 수 있어요."}
    t = body.tier if body.tier in TIERS else "free"
    with db.connect() as c:
        db.kv_set(c, f"tier:{user}", t)
    return {"ok": True, "tier": t, "limits": TIERS[t]}


def _verify_purchase(platform: str, product_id: str, transaction: str):
    """구매 검증 자리 — 반드시 '서버가' 스토어에 직접 확인해야 한다 (클라 주장은 못 믿음).
      · iOS: App Store Server API로 StoreKit2 JWS 서명 검증 → productId·expiresDate 추출
      · Android: Google Play Developer API purchases.subscriptions.get 로 확인
    검증이 연결되기 전에는 안전하게 '거부'(fail-closed)한다.
    반환 예: {"tier": "pro", "expires_at": "2026-09-01T00:00:00+00:00"} 또는 None."""
    # TODO: 실제 스토어 검증 연결. (지금은 미설정 → None 반환 = 부여 안 함)
    return None


class EntitlementBody(BaseModel):
    platform: str = "ios"      # ios | android
    product_id: str = ""
    transaction: str = ""      # StoreKit2 JWS 또는 영수증


@router.post("/entitlement")
def set_entitlement(body: EntitlementBody, user: str = Header(default="solo", alias="X-User-Id")):
    """앱 내 구매 후 네이티브가 영수증을 보내면, 서버가 검증해 등급을 부여한다."""
    v = _verify_purchase(body.platform, body.product_id, body.transaction)
    if not v or v.get("tier") not in TIERS:
        return {"ok": False, "error": "결제 검증을 아직 사용할 수 없어요.",
                "detail": "서버에 애플/구글 결제 검증이 연결되면 자동으로 적용됩니다."}
    ent = {"tier": v["tier"], "product_id": body.product_id, "platform": body.platform,
           "expires_at": v.get("expires_at"),
           "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with db.connect() as c:
        db.kv_set(c, f"ent:{user}", json.dumps(ent, ensure_ascii=False))
    return {"ok": True, "tier": v["tier"], "limits": TIERS[v["tier"]], "expires_at": v.get("expires_at")}


ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")


class GrantBody(BaseModel):
    user_id: str
    tier: str
    days: int = 31


@router.post("/admin/grant")
def admin_grant(body: GrantBody, secret: str = Header(default="", alias="X-Admin-Secret")):
    """운영자 수동 등급 부여 (테스트·보상용). 서버의 ADMIN_SECRET 환경변수와 헤더가 일치해야 한다."""
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        return {"ok": False, "error": "권한이 없어요."}
    if body.tier not in TIERS:
        return {"ok": False, "error": "알 수 없는 등급이에요."}
    exp = (datetime.datetime.now(datetime.timezone.utc)
           + datetime.timedelta(days=max(1, body.days))).isoformat()
    ent = {"tier": body.tier, "product_id": "admin_grant", "platform": "admin",
           "expires_at": exp, "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with db.connect() as c:
        db.kv_set(c, f"ent:{body.user_id}", json.dumps(ent, ensure_ascii=False))
    return {"ok": True, "tier": body.tier, "expires_at": exp}


@router.get("/account/export")
def export_account(user: str = Header(default="solo", alias="X-User-Id")):
    """내 데이터 전부 내보내기 (데이터 이동권)."""
    with db.connect() as c:
        works = [dict(r) for r in c.execute(
            "SELECT * FROM works WHERE user_id=? ORDER BY id", (user,)).fetchall()]
        for w in works:
            w["chapters"] = [dict(x) for x in c.execute(
                "SELECT * FROM chapters WHERE work_id=? ORDER BY no", (w["id"],)).fetchall()]
    return {"ok": True, "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "works": works}


@router.delete("/account")
def delete_account(user: str = Header(default="solo", alias="X-User-Id")):
    """계정(이 사용자)의 모든 데이터 영구 삭제 — 애플/구글 정책상 앱 내 제공 필수."""
    with db.connect() as c:
        wids = [r["id"] for r in c.execute(
            "SELECT id FROM works WHERE user_id=?", (user,)).fetchall()]
        for wid in wids:
            c.execute("DELETE FROM chapters WHERE work_id=?", (wid,))
        c.execute("DELETE FROM works WHERE user_id=?", (user,))
        c.execute("DELETE FROM kv WHERE k=?", (f"tier:{user}",))
        c.execute("DELETE FROM kv WHERE k=?", (f"ent:{user}",))
        c.execute("DELETE FROM kv WHERE k LIKE ?", (f"aiq:{user}:%",))
        c.execute("DELETE FROM kv WHERE k=?", (f"active_avatar:{user}",))
        for r in c.execute("SELECT k, v FROM kv WHERE k LIKE 'trash:%'").fetchall():
            try:
                if json.loads(r["v"]).get("user") == user:
                    c.execute("DELETE FROM kv WHERE k=?", (r["k"],))
            except Exception:
                pass
    return {"ok": True, "deleted_works": len(wids)}


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
    forward: bool = False   # True면 '이후 화' 맥락을 빼고 앞만 보고 다시 쓴다(모든 회차 다시 쓰기용)


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
        if not _limits(_tier_name(c, user))["style_learning"]:
            return {"ok": False, "error": "문체 학습은 프로 요금제에서 쓸 수 있어요.", "limit": "style"}
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


BRIEF_MAX = 20000  # 작품설명서 보관 상한
BRIEF_PROMPT_MAX = 7000  # 매 회차 프롬프트에 재주입하는 분량


def extract_brief_text(filename: str, data: bytes) -> str:
    """작품설명서 파일에서 텍스트를 뽑는다 (.txt .md .docx .pdf)."""
    name = (filename or "").lower()
    try:
        if name.endswith((".txt", ".md")):
            for enc in ("utf-8", "cp949", "euc-kr"):
                try:
                    return data.decode(enc)[:BRIEF_MAX]
                except UnicodeDecodeError:
                    continue
            return data.decode("utf-8", errors="ignore")[:BRIEF_MAX]
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for t in doc.tables:
                for row in t.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            return "\n".join(x for x in parts if x.strip())[:BRIEF_MAX]
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)[:BRIEF_MAX]
    except Exception as e:
        print(f"[writer] 설명서 추출 실패 ({filename}): {e}", flush=True)
        return ""
    return ""


_CH_HEAD = re.compile(r"^\s*(\d{1,3})\s*화\s*[.．·:]?\s*(.*)$")


def extract_outline(brief: str) -> list:
    """계획서에서 'N화. 제목 + 내용' 형식의 회차별 지정 내용을 추출한다.
    작가가 이미 회차를 짜뒀으면, 우리는 그 회차를 그대로 따른다.

    진짜 회차 목록은 1→N으로 순서대로 이어진다. 문서 제목('50화 웹소설 설계서')이나
    하단의 참조('49화: …')는 그 흐름 밖에 있으므로, 연속 증가하는 본 흐름만 잡는다."""
    lines = brief.splitlines()
    heads = []  # (line_idx, no, title)
    for i, ln in enumerate(lines):
        m = _CH_HEAD.match(ln)
        if not m:
            continue
        no = int(m.group(1))
        title = m.group(2).strip()
        if not (1 <= no <= 999):
            continue
        if title.startswith(("~", "∼", "－", "-", "화")):  # '31화~40화' 같은 범위 헤더 제외
            continue
        heads.append((i, no, title))

    # 연속 증가하는 본 흐름만 채택 (expected: 1,2,3,...)
    main, expected = [], 1
    for idx, no, title in heads:
        if no == expected:
            main.append((idx, no, title))
            expected += 1
    if len(main) < 3:  # 연속 흐름이 약하면(회차 목록이 없는 계획서), 추출하지 않는다
        return []

    outline = []
    for j, (idx, no, title) in enumerate(main):
        end = main[j + 1][0] if j + 1 < len(main) else len(lines)
        body = "\n".join(x.strip() for x in lines[idx + 1:end] if x.strip())
        outline.append({"no": no, "title": title, "content": body[:1500]})
    return outline


def _outline_for(w: dict, no: int) -> dict:
    try:
        for o in json.loads(w.get("outline_json") or "[]"):
            if o.get("no") == no:
                return o
    except Exception:
        pass
    return {}


def _brief_block(w: dict, limit: int = BRIEF_PROMPT_MAX) -> str:
    """작품설명서 — 매 호출마다 다시 읽는 절대 기준. 잊는 것은 허용되지 않는다."""
    brief = (w.get("brief") or "").strip()
    if not brief:
        return ""
    return (f"[작품설명서 — 작가가 쓴 이 작품의 절대 기준. 설정집·요약과 어긋나면 설명서가 항상 우선한다. "
            f"여기 명시된 인물·설정·전개·금기를 절대 위반하지 마라]\n{brief[:limit]}\n")


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


def _brief_setup_prompt(brief: str, genre: str, total: int) -> str:
    schema = {
        "title": "작품 제목 (설명서에 있으면 그대로, 없으면 설명서에 맞게 창작)",
        "genre": "장르", "premise": "로그라인 한두 문장 (설명서에서 추출)",
        "ending": "결말 (설명서에 명시된 결말. 없으면 설명서의 방향에서 도출)",
        "style": "문체 지침 한 줄 (설명서의 요구 반영)",
        "characters": [{"name": "이름", "archetype": "원형", "role": "한 줄 소개",
                        "want": "외적 욕망", "need": "내적 결핍", "secret": "비밀"}],
        "relations": [{"a": "인물", "b": "인물", "type": "관계", "tension": "긴장 한 줄"}],
        "beats": [{"idx": 0, "name": BEATS[0], "summary": "이 비트에서 벌어질 일 2~3문장"}],
    }
    return f"""당신은 웹소설 스토리 설계자다. 아래 '작품설명서'가 이 작품의 유일한 원천이다.
설명서를 정밀하게 읽고, 거기 적힌 모든 것을 정확히 반영한 설계도를 JSON으로 만들어라.

[작품설명서 — 절대 기준]
{brief}

{f'[장르 힌트] {genre}' if genre else ''}
[총 회차] {total}화

JSON 스키마 (다른 텍스트 없이 압축 JSON만):
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}

절대 규칙 (위반 시 실패로 간주):
- **설명서에 적힌 것은 단 하나도 바꾸거나 빼거나 지어내지 마라.** 인물 이름·나이·성격·
  직업·관계·설정·세계관·전개·결말·금기 — 설명서의 표현을 그대로 존중하라.
  네 상상으로 각색하거나 '더 낫게' 바꾸는 것은 명백한 오류다.
- **설명서에 등장한 인물은 전원 characters에 넣어라.** 한 명도 빠뜨리지 마라.
  설명서에 인물이 8명이면 8명 다. 설명서에 없는 인물을 새로 만들어 넣지 마라
  (반드시 필요한 조연은 role에 '(보강)'을 표시).
- 각 인물의 want/need/secret/role은 설명서에 쓰인 내용을 우선 그대로 옮기고,
  설명서에 없는 항목만 설정에 맞게 채워라.
- premise/ending/style은 설명서에 적힌 것을 최대한 그대로 반영하라.
  설명서에 결말이 명시돼 있으면 그 문장을 결말로 삼아라.
- relations: 설명서에 나온 인물 관계를 모두 반영.
- beats: Save the Cat 15비트 전부, name은 이 순서 그대로: {', '.join(BEATS)}.
  각 비트 summary는 설명서의 실제 전개·설정을 반영해야 하며, '피날레'·'파이널
  이미지'는 설명서의 결말을 실현해야 한다.
- 역사물이면 실존 인물의 인명(휘)·호칭·관계를 실제 역사대로.
- 출력은 들여쓰기 없는 압축 JSON 하나. 설명·코드펜스 금지."""


@router.post("/works/from-brief")
async def create_from_brief(
    file: UploadFile = File(None),
    brief_text: str = Form(""),
    genre: str = Form(""),
    total_chapters: int = Form(25),
    style_sample: str = Form(""),
    user: str = Header(default="solo", alias="X-User-Id"),
):
    """작품설명서로 시작 — 파일(또는 붙여넣기)이 설계도의 유일한 원천이 된다."""
    brief = brief_text.strip()
    if file is not None and file.filename:
        data = await file.read()
        brief = extract_brief_text(file.filename, data).strip() or brief
    if len(brief) < 200:
        return {"ok": False,
                "error": "설명서에서 읽어낸 내용이 너무 짧아요 (200자 미만). "
                         "텍스트가 있는 .txt/.md/.docx/.pdf 파일인지 확인해 주세요."}

    # 설명서 기반 설계는 반드시 실제 AI가 해야 한다.
    # 목업(가짜 템플릿)으로 조용히 대체하면 설명서가 무시된 채 엉뚱한 작품이 나온다.
    if llm.is_mock:
        return {"ok": False,
                "error": "AI가 연결되어 있지 않아 설명서를 읽을 수 없어요.",
                "detail": "API 키가 설정되지 않았거나 사용량 한도/잔액이 소진됐을 수 있어요. "
                          "Anthropic 콘솔에서 크레딧을, 또는 Render 환경변수(ANTHROPIC_API_KEY / "
                          "GEMINI_API_KEY, LLM_PROVIDER)를 확인해 주세요."}
    plan, last_raw = None, ""
    for _ in range(2):
        last_raw = llm.write(_brief_setup_prompt(brief, genre, max(5, total_chapters)),
                             mock_text="", max_tokens=16000)
        plan = parse_llm_json(last_raw)
        if plan and plan.get("characters") and plan.get("beats"):
            break
        plan = None
    if plan is None:
        if llm.last_error:
            hint = (f"AI 호출 오류 — {llm.last_error}. "
                    "사용량 한도 초과나 크레딧 소진이면 콘솔에서 해결하거나 Gemini로 전환하세요.")
        else:
            hint = f"형식 오류 (응답 앞부분: {last_raw[:150] or '빈 응답'})"
        return {"ok": False, "error": "설계도 생성에 실패했어요. 설명서는 반영되지 않았어요.",
                "detail": hint}

    beats = plan.get("beats") or []
    by_idx = {int(x.get("idx", i)): x for i, x in enumerate(beats) if isinstance(x, dict)}
    beats = [{"idx": i, "name": n, "summary": (by_idx.get(i) or {}).get("summary", "")}
             for i, n in enumerate(BEATS)]

    sample = style_sample.strip()
    profile = analyze_style(sample) if len(sample) >= 300 else ""

    # 계획서에 회차별 내용이 있으면 추출해 그대로 따른다 (작가가 짠 회차 = 절대 기준)
    outline = extract_outline(brief)
    if len(outline) >= 3:
        total_chapters = max(outline[-1]["no"], total_chapters)

    with db.connect() as c:
        work_id = c.insert_id(
            "INSERT INTO works (user_id, title, genre, brief, premise, ending, style, "
            "total_chapters, style_sample, style_profile, characters_json, relations_json, "
            "beats_json, outline_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (user, plan.get("title") or "무제", plan.get("genre") or genre or "웹소설",
             brief[:BRIEF_MAX], plan.get("premise") or "", plan.get("ending") or "",
             plan.get("style") or "", max(5, total_chapters), sample[:6000], profile,
             json.dumps(plan.get("characters", []), ensure_ascii=False),
             json.dumps(plan.get("relations", []), ensure_ascii=False),
             json.dumps(beats, ensure_ascii=False),
             json.dumps(outline, ensure_ascii=False)),
        )
    return {"ok": True, "id": work_id, "outline_chapters": len(outline)}


# ── 앱 안에서 작품설명서를 직접 만든다 (상세 빌더) ──────────────────────────
# 파일 업로드 없이도, 구조화된 상세 폼을 정식 기획안 텍스트로 조립해
# 위의 from-brief 파이프라인에 그대로 투입한다. 설명서는 완결까지 절대 기준.

class ProtIn(BaseModel):
    name: str = ""
    age: str = ""
    job: str = ""
    personality: str = ""
    want: str = ""
    need: str = ""
    secret: str = ""
    arc: str = ""


class CharIn(BaseModel):
    name: str = ""
    role: str = ""
    relation: str = ""
    want: str = ""
    need: str = ""
    secret: str = ""


class CanonIn(BaseModel):
    name: str = ""
    desc: str = ""


class OutlineIn(BaseModel):
    no: int = 0
    title: str = ""
    content: str = ""


class BuildBody(BaseModel):
    title: str = ""
    genre: str = ""
    total_chapters: int = 25
    chars_per_chapter: int = 5000
    keywords: str = ""
    logline: str = ""            # 로그라인
    intent: str = ""             # 기획 의도
    world_setting: str = ""      # 배경 — 시대·공간
    world_rules: str = ""        # 핵심 규칙·시스템
    taboos: str = ""             # 금기·제약
    protagonist: ProtIn = ProtIn()
    characters: list[CharIn] = []
    canon: list[CanonIn] = []
    style: str = ""
    style_sample: str = ""
    ending: str = ""
    outline: list[OutlineIn] = []


def _sec(title: str, body: str) -> str:
    body = (body or "").strip()
    return f"## {title}\n{body}\n\n" if body else ""


def _assemble_brief(b: BuildBody) -> str:
    """구조화된 빌더 입력을 사람이 읽는 정식 기획안 텍스트로 조립한다.
    회차별 전개는 'N화. 제목' 형식으로 써서 extract_outline과도 호환된다."""
    out = [f"# {b.title.strip() or '무제'}\n"
           f"장르: {b.genre.strip() or '미정'} · 총 {max(5, b.total_chapters)}화 · "
           f"회당 목표 {b.chars_per_chapter or 5000}자\n"
           + (f"키워드: {b.keywords.strip()}\n" if b.keywords.strip() else "") + "\n"]
    out.append(_sec("로그라인", b.logline))
    out.append(_sec("기획 의도", b.intent))

    world = ""
    if b.world_setting.strip():
        world += f"배경: {b.world_setting.strip()}\n"
    if b.world_rules.strip():
        world += f"핵심 규칙·시스템:\n{b.world_rules.strip()}\n"
    if b.taboos.strip():
        world += f"금기·제약:\n{b.taboos.strip()}\n"
    out.append(_sec("세계관", world))

    p = b.protagonist
    if any(x.strip() for x in (p.name, p.personality, p.want, p.need, p.secret, p.arc, p.job, p.age)):
        tags = " · ".join(x.strip() for x in (p.age, p.job) if x.strip())
        pl = [f"{p.name.strip() or '주인공'}{' (' + tags + ')' if tags else ''}"]
        for label, val in (("성격", p.personality), ("욕망(want)", p.want),
                           ("결핍(need)", p.need), ("비밀", p.secret), ("성장 아크", p.arc)):
            if val.strip():
                pl.append(f"{label}: {val.strip()}")
        out.append(_sec("주인공", "\n".join(pl)))

    chars = [ch for ch in b.characters if ch.name.strip()]
    if chars:
        lines = []
        for ch in chars:
            parts = [f"- {ch.name.strip()}"]
            for label, val in (("역할", ch.role), ("관계", ch.relation), ("욕망", ch.want),
                               ("결핍", ch.need), ("비밀", ch.secret)):
                if val.strip():
                    parts.append(f"{label}: {val.strip()}")
            lines.append(" / ".join(parts))
        out.append(_sec("등장인물", "\n".join(lines)))

    canon = [cc for cc in b.canon if cc.name.strip()]
    if canon:
        lines = [f"- {cc.name.strip()}" + (f": {cc.desc.strip()}" if cc.desc.strip() else "")
                 for cc in canon]
        out.append(_sec("핵심 설정·고유명사 (표기 고정)", "\n".join(lines)))

    out.append(_sec("문체", b.style))
    out.append(_sec("결말 — 이야기는 반드시 이곳에 도달한다", b.ending))

    valid = sorted([o for o in b.outline if o.no and o.no >= 1 and (o.title.strip() or o.content.strip())],
                   key=lambda o: o.no)
    if valid:
        lines = []
        for o in valid:
            lines.append(f"{o.no}화. {o.title.strip()}".rstrip())
            if o.content.strip():
                lines.append(o.content.strip())
            lines.append("")
        out.append(_sec("회차별 전개", "\n".join(lines).strip()))
    return "".join(out).strip()


@router.post("/works/build")
def build_work(b: BuildBody, user: str = Header(default="solo", alias="X-User-Id")):
    """상세 빌더로 만든 작품설명서로 설계도를 만들고 작품을 생성한다."""
    _cap_build(b)
    brief = _assemble_brief(b)
    if not (b.logline.strip() or b.ending.strip()):
        return {"ok": False, "error": "최소한 로그라인이나 결말 중 하나는 있어야 이야기가 방향을 잡아요."}
    if len(brief) < 200:
        return {"ok": False, "error": "설명서 내용이 아직 짧아요. 세계관·주인공·결말 등을 더 채워주세요 (최소 200자)."}
    with db.connect() as c:  # 요금제 작품 수 상한 + 하루 AI 상한
        lim = _limits(_tier_name(c, user))
        made = c.execute("SELECT COUNT(*) AS n FROM works WHERE user_id=?", (user,)).fetchone()["n"]
        if made >= lim["max_works"]:
            return {"ok": False,
                    "error": f"{lim['label']} 요금제에서는 작품을 {lim['max_works']}개까지 만들 수 있어요.",
                    "detail": "기존 작품을 지우거나 상위 요금제로 올려 주세요.", "limit": "works"}
        ok, _cap = _ai_gate(c, user)
        if not ok:
            return _AI_BUSY
    if llm.is_mock:
        return {"ok": False, "error": "AI가 연결되어 있지 않아 설계도를 만들 수 없어요.",
                "detail": "API 키가 없거나 사용량 한도/잔액이 소진됐을 수 있어요 "
                          "(ANTHROPIC_API_KEY / GEMINI_API_KEY, LLM_PROVIDER 확인)."}

    total = max(5, b.total_chapters)
    plan, last_raw = None, ""
    for _ in range(2):
        last_raw = llm.write(_brief_setup_prompt(brief, b.genre, total), mock_text="", max_tokens=16000)
        plan = parse_llm_json(last_raw)
        if plan and plan.get("characters") and plan.get("beats"):
            break
        plan = None
    if plan is None:
        hint = (f"AI 호출 오류 — {llm.last_error}. 사용량 한도/크레딧을 확인하세요."
                if llm.last_error else f"형식 오류 (응답 앞부분: {last_raw[:150] or '빈 응답'})")
        return {"ok": False, "error": "설계도 생성에 실패했어요. 설명서는 반영되지 않았어요.", "detail": hint}

    beats = plan.get("beats") or []
    by_idx = {int(x.get("idx", i)): x for i, x in enumerate(beats) if isinstance(x, dict)}
    beats = [{"idx": i, "name": n, "summary": (by_idx.get(i) or {}).get("summary", "")}
             for i, n in enumerate(BEATS)]

    if isinstance(plan.get("characters"), list):  # 요금제 인물 수 상한
        plan["characters"] = plan["characters"][:lim["max_characters"]]

    # 회차별 전개 — 작가가 빌더에서 짠 것이 절대 기준. 없으면 조립 텍스트에서 추출.
    outline = [{"no": o.no, "title": o.title.strip(), "content": o.content.strip()}
               for o in sorted(b.outline, key=lambda o: o.no)
               if o.no and o.no >= 1 and (o.title.strip() or o.content.strip())]
    if not outline:
        outline = extract_outline(brief)
    if outline:
        total = max(outline[-1]["no"], total)

    canon = {cc.name.strip(): cc.desc.strip() for cc in b.canon if cc.name.strip()}
    sample = b.style_sample.strip()
    profile = analyze_style(sample) if len(sample) >= 300 else ""

    cpc = max(1000, min(int(b.chars_per_chapter or 5000), 8000))
    with db.connect() as c:
        work_id = c.insert_id(
            "INSERT INTO works (user_id, title, genre, brief, premise, ending, style, "
            "total_chapters, style_sample, style_profile, characters_json, relations_json, "
            "beats_json, outline_json, canon_json, chars_per_chapter, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (user, plan.get("title") or b.title or "무제", plan.get("genre") or b.genre or "웹소설",
             brief[:BRIEF_MAX], plan.get("premise") or b.logline, plan.get("ending") or b.ending,
             plan.get("style") or b.style, total, sample[:6000], profile,
             json.dumps(plan.get("characters", []), ensure_ascii=False),
             json.dumps(plan.get("relations", []), ensure_ascii=False),
             json.dumps(beats, ensure_ascii=False),
             json.dumps(outline, ensure_ascii=False),
             json.dumps(canon, ensure_ascii=False), cpc),
        )
    return {"ok": True, "id": work_id, "outline_chapters": len(outline)}


@router.post("/brief/draft")
def draft_brief(b: BuildBody, user: str = Header(default="solo", alias="X-User-Id")):
    """지금까지 작가가 채운 내용을 존중하며, 빈 칸을 일관되게 채운 상세 기획을 짓는다.
    작가가 칸을 비우고 다시 누르면 그 칸만 새로 생성된다 (새로고침).
    요금제에 따라 자동 생성하는 인물 수가 달라진다."""
    if llm.is_mock:
        return {"ok": False, "error": "AI가 연결되어 있지 않아요.",
                "detail": "API 키/사용량 한도를 확인해 주세요."}
    if not (b.logline.strip() or b.genre.strip() or b.keywords.strip()):
        return {"ok": False, "error": "장르·로그라인·키워드 중 하나는 알려주세요. 거기서 상세 기획을 지어드릴게요."}
    _cap_build(b)
    with db.connect() as c:
        ok, _cap = _ai_gate(c, user)
        if not ok:
            return _AI_BUSY
        maxc = _limits(_tier_name(c, user))["max_characters"]
    filled = _assemble_brief(b)
    schema = {
        "title": "제목 (없으면 창작)",
        "logline": "로그라인 한두 문장",
        "intent": "기획 의도 2~3문장 (독자·재미 포인트)",
        "world_setting": "시대·공간 배경",
        "world_rules": "핵심 규칙·시스템 (여러 줄, 각 줄 하나의 규칙)",
        "taboos": "이 세계의 금기·제약",
        "protagonist": {"name": "", "age": "", "job": "", "personality": "성격",
                        "want": "외적 욕망", "need": "내적 결핍", "secret": "비밀", "arc": "성장 아크"},
        "characters": [{"name": "", "role": "역할", "relation": "주인공과의 관계",
                        "want": "욕망", "need": "결핍", "secret": "비밀"}],
        "canon": [{"name": "채널명·조직명·지명·별명 등", "desc": "설명"}],
        "style": "문체 지침 한 줄",
        "ending": "고정된 결말",
    }
    prompt = f"""당신은 프로 웹소설 기획자다. 아래는 작가가 지금까지 채운 기획이다.
이걸 바탕으로 '매우 상세한' 완성 기획을 JSON으로 지어라.

[작가가 지금까지 채운 내용 — 이미 적힌 것은 작가의 의도다]
{filled}

[장르] {b.genre or '자유'}
[총 회차] {max(5, b.total_chapters)}화

JSON 스키마 (다른 텍스트 없이 압축 JSON만):
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}

핵심 규칙:
- **작가가 이미 쓴 항목은 그 의도와 표현을 최대한 존중하라.** 로그라인·세계관·주인공·
  결말 등 작가가 채운 값은 그대로 옮기고(사소한 다듬기만 허용), 임의로 뒤집지 마라.
- **비어 있는 항목만 새로 지어라.** 채운 내용과 모순 없이, 구체적이고 일관되게.
- characters는 **정확히 {maxc}명**(작가가 넣은 인물을 우선 포함). 적대자·조력자·애정상대 등
  원형을 고루, 각 인물의 want와 need는 어긋나게(입체성), 관계(relation)를 분명히.
- world_rules는 이 작품만의 독창적 설정을 구체적으로.
- canon은 표기가 흔들리면 안 되는 고유명사 3~6개.
- ending은 하나의 도달점으로 고정(열린 결말 금지).
- 역사물이면 실존 인물의 인명·호칭·관계를 실제대로.
- 상투적이지 않게, 그러나 장르 독자가 좋아하는 코드는 지켜라. JSON만 출력."""
    raw = llm.write(prompt, mock_text="", max_tokens=8000)
    data = parse_llm_json(raw)
    if not isinstance(data, dict):
        return {"ok": False, "error": "기획 초안 생성에 실패했어요. 한 번 더 시도해 주세요.",
                "detail": (llm.last_error or (raw[:150] or "빈 응답"))}
    if isinstance(data.get("characters"), list):  # 요금제 상한까지만
        data["characters"] = data["characters"][:maxc]
    return {"ok": True, "draft": data, "max_characters": maxc}


@router.post("/brief/outline")
def draft_outline(b: BuildBody, user: str = Header(default="solo", alias="X-User-Id")):
    """지금까지 채운 설정을 바탕으로 회차별 전개(1화~N화)를 통째로 생성한다.
    요금제에 따라 '몇 화까지'와 '화당 줄거리 깊이(글자수)'가 달라진다."""
    if llm.is_mock:
        return {"ok": False, "error": "AI가 연결되어 있지 않아요.",
                "detail": "API 키/사용량 한도를 확인해 주세요."}
    if not (b.logline.strip() or b.ending.strip() or b.world_setting.strip()):
        return {"ok": False, "error": "회차 전개를 짜려면 최소한 로그라인·세계관·결말 중 하나는 채워주세요."}
    _cap_build(b)
    with db.connect() as c:
        ok, _cap = _ai_gate(c, user)
        if not ok:
            return _AI_BUSY
        lim = _limits(_tier_name(c, user))
    requested = max(1, min(b.total_chapters, 200))
    total = min(requested, lim["max_chapters"])   # 요금제 상한까지만 생성
    syn = lim["syn_chars"]                          # 화당 줄거리 목표 글자수
    context = _assemble_brief(b)
    beats_guide = "\n".join(
        f"- {int(edge*100)}%까지: {name}" for name, edge in zip(BEATS, BEAT_EDGES))
    prompt = f"""당신은 웹소설 플롯 설계자다. 아래 기획을 바탕으로 {total}화 전체의 '회차별 전개'를 짜라.
Save the Cat 15비트를 회차 진행률에 맞춰 배치하고, 반드시 고정된 결말로 수렴시켜라.

[기획]
{context}

[비트 배치 가이드 (진행률 기준)]
{beats_guide}

출력: 아래 형식의 JSON 하나만 (1화부터 {total}화까지 '전부', 빠짐없이):
{{"outline":[{{"no":1,"title":"이 화 제목","content":"이 화의 핵심 사건"}}]}}

규칙:
- no는 1부터 {total}까지 연속. 한 화도 빠뜨리지 마라.
- **각 화 content는 약 {syn}자 분량으로.** ({'핵심 사건만 간결하게' if syn <= 120 else ('사건과 전개를 담아' if syn <= 300 else '사건·전개·감정선·복선까지 상세하게')})
- 각 화는 갈등이 전진하거나 반전이 있어야 한다. 사이다-고구마 리듬을 지켜라.
- 초반 3화 안에 후킹(주인공의 문제·목표·세계 규칙)을 확실히.
- 마지막 화들은 고정된 결말을 실현한다.
- content는 요약이 아니라 '이 화에 실제로 벌어지는 일'. 설정·인물을 구체적으로 사용.
- 압축 JSON만 출력. 설명·코드펜스 금지."""
    raw = llm.write(prompt, mock_text="", max_tokens=16000)
    data = parse_llm_json(raw)
    items = data.get("outline") if isinstance(data, dict) else (data if isinstance(data, list) else None)
    if not items:
        return {"ok": False, "error": "회차 전개 생성에 실패했어요. 한 번 더 시도해 주세요.",
                "detail": (llm.last_error or (raw[:150] or "빈 응답"))}
    outline = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            no = int(it.get("no"))
        except (TypeError, ValueError):
            continue
        if 1 <= no <= total:                       # 상한 넘는 회차는 버린다
            outline.append({"no": no, "title": str(it.get("title", "")).strip(),
                            "content": str(it.get("content", "")).strip()})
    outline.sort(key=lambda o: o["no"])
    return {"ok": True, "outline": outline,
            "capped": requested > total, "tier_max": lim["max_chapters"]}


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
            plan = _mock_setup(body)  # 데모/오프라인 체험용 (직접 입력 경로에 한함)
        else:
            hint = (f"AI 호출 오류 — {llm.last_error}. 크레딧/사용량 한도를 확인하세요."
                    if llm.last_error else
                    ("응답이 비어 있음 — API 키/모델 설정 확인 필요"
                     if not last_raw.strip() else f"형식 오류 (응답 앞부분: {last_raw[:120]})"))
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
    w["outline"] = json.loads(w.get("outline_json") or "[]")
    w["canon"] = json.loads(w.get("canon_json") or "{}")
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
            "SELECT id, no, title, summary, beat_idx, directive FROM chapters WHERE work_id=? ORDER BY no",
            (work_id,)).fetchall()]
        return {"ok": True,
                "work": {k: w.get(k) for k in ("id", "title", "genre", "premise", "ending",
                                               "style", "total_chapters", "characters",
                                               "relations", "beats", "brief", "outline", "canon",
                                               "style_profile", "style_sample", "chars_per_chapter")},
                "chapters": chapters}


class BibleBody(BaseModel):
    title: str = ""
    ending: str = ""
    characters: list = []
    relations: list = []
    beats: list = []
    total_chapters: int = 0       # 0이면 그대로 둔다
    chars_per_chapter: int = 0    # 0이면 그대로 둔다


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
        total = body.total_chapters if body.total_chapters and body.total_chapters >= 5 \
            else w["total_chapters"]
        cpc = max(1000, min(body.chars_per_chapter, 8000)) if body.chars_per_chapter \
            else (w.get("chars_per_chapter") or 5000)
        c.execute(
            "UPDATE works SET title=?, ending=?, characters_json=?, relations_json=?, "
            "beats_json=?, total_chapters=?, chars_per_chapter=? WHERE id=?",
            (body.title.strip() or w["title"],
             body.ending.strip() or w["ending"],
             json.dumps(body.characters or w["characters"], ensure_ascii=False),
             json.dumps(body.relations or w["relations"], ensure_ascii=False),
             json.dumps(_normalize_beats(body.beats or w["beats"]), ensure_ascii=False),
             total, cpc, work_id),
        )
    return {"ok": True}


class BriefBody(BaseModel):
    brief: str = ""


@router.put("/works/{work_id}/brief")
def edit_brief(work_id: int, body: BriefBody,
               user: str = Header(default="solo", alias="X-User-Id")):
    """작품설명서 직접 편집 — 절대 기준이므로 작가가 언제든 고칠 수 있어야 한다."""
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        c.execute("UPDATE works SET brief=? WHERE id=?", (body.brief[:BRIEF_MAX], work_id))
    return {"ok": True}


class OutlineBody(BaseModel):
    outline: list[OutlineIn] = []


@router.put("/works/{work_id}/outline")
def edit_outline(work_id: int, body: OutlineBody,
                 user: str = Header(default="solo", alias="X-User-Id")):
    """회차별 전개(계획) 편집 — 지정된 회차는 그 내용대로 집필된다."""
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        outline = [{"no": o.no, "title": o.title.strip(), "content": o.content.strip()}
                   for o in sorted(body.outline, key=lambda o: o.no)
                   if o.no and o.no >= 1 and (o.title.strip() or o.content.strip())]
        total = w["total_chapters"]
        if outline:
            total = max(total, outline[-1]["no"])
        c.execute("UPDATE works SET outline_json=?, total_chapters=? WHERE id=?",
                  (json.dumps(outline, ensure_ascii=False), total, work_id))
    return {"ok": True, "outline_count": len(outline)}


class RenameBody(BaseModel):
    old: str
    new: str


@router.post("/works/{work_id}/rename")
def rename_term(work_id: int, body: RenameBody,
                user: str = Header(default="solo", alias="X-User-Id")):
    """이름·고유명사 일괄 변경 — 설정집은 물론 '이미 쓴 모든 회차 본문'까지 그대로 반영한다.
    이야기를 흔드는 고유명사(인명·지명·조직명 등)는 앞 내용까지 함께 바뀌어야 하므로 전역 치환한다."""
    if LAUNCH_MODE:
        return _LAUNCH_OFF
    old, new = body.old.strip(), body.new.strip()
    if not old or not new:
        return {"ok": False, "error": "바꿀 이름과 새 이름을 모두 입력해 주세요."}
    if old == new:
        return {"ok": True, "chapters": 0}
    if any(ch in (old + new) for ch in ('"', "\\")):
        return {"ok": False, "error": "이름에 따옴표(\")나 역슬래시(\\)는 쓸 수 없어요."}
    rep = lambda s: (s or "").replace(old, new)
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        # 작품 설정 전반 (JSON 문자열째로 치환 — 값 안의 이름까지 모두 바뀐다)
        c.execute(
            "UPDATE works SET title=?, premise=?, ending=?, brief=?, style=?, "
            "characters_json=?, relations_json=?, beats_json=?, outline_json=?, canon_json=? "
            "WHERE id=?",
            (rep(w["title"]), rep(w.get("premise")), rep(w.get("ending")), rep(w.get("brief")),
             rep(w.get("style")), rep(w.get("characters_json")), rep(w.get("relations_json")),
             rep(w.get("beats_json")), rep(w.get("outline_json")), rep(w.get("canon_json")),
             work_id),
        )
        # 이미 쓴 모든 회차 본문·제목·요약
        rows = c.execute("SELECT id, title, body, summary FROM chapters WHERE work_id=?",
                         (work_id,)).fetchall()
        n = 0
        for r in rows:
            if old in (r["title"] or "") or old in (r["body"] or "") or old in (r["summary"] or ""):
                c.execute("UPDATE chapters SET title=?, body=?, summary=?, updated_at=datetime('now') "
                          "WHERE id=?", (rep(r["title"]), rep(r["body"]), rep(r["summary"]), r["id"]))
                n += 1
    return {"ok": True, "chapters": n}


class CanonBody(BaseModel):
    name: str          # 고유명사 (채널명·조직명·지명·별명·설정용어)
    value: str = ""    # 짧은 설명 (선택)


@router.post("/works/{work_id}/canon")
def set_canon(work_id: int, body: CanonBody,
              user: str = Header(default="solo", alias="X-User-Id")):
    """고유명사 고정 — AI 없이 즉시 정전에 등록한다. 이후 모든 회차가 이 표기를 지킨다."""
    name = body.name.strip()
    if not name:
        return {"ok": False, "error": "고정할 이름을 입력해 주세요."}
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        canon = w.get("canon") or {}
        canon[name] = body.value.strip()
        c.execute("UPDATE works SET canon_json=? WHERE id=?",
                  (json.dumps(canon, ensure_ascii=False), work_id))
    return {"ok": True, "canon": canon}


@router.delete("/works/{work_id}/canon/{name}")
def del_canon(work_id: int, name: str,
              user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        canon = w.get("canon") or {}
        canon.pop(name, None)
        c.execute("UPDATE works SET canon_json=? WHERE id=?",
                  (json.dumps(canon, ensure_ascii=False), work_id))
    return {"ok": True, "canon": canon}


class ReviseBody(BaseModel):
    directive: str


@router.post("/works/{work_id}/bible/revise")
def revise_bible(work_id: int, body: ReviseBody,
                 user: str = Header(default="solo", alias="X-User-Id")):
    """명령으로 설정집 수정 — '주인공 이름을 이홍위로 바꿔' 한 줄이면 된다."""
    if LAUNCH_MODE:
        return _LAUNCH_OFF
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

{_brief_block(w, 4000)}
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


def _work_canon(w: dict) -> dict:
    """작가가 설정집/명령으로 고정한 고유명사 — 작품 전체의 최우선 정전."""
    try:
        return json.loads(w.get("canon_json") or "{}") or {}
    except Exception:
        return {}


def _this_chapter_block(w: dict, no: int, beat: dict) -> str:
    """이번 화의 지침 — 계획서에 이 화 내용이 지정돼 있으면 그것이 절대 우선한다."""
    o = _outline_for(w, no)
    if o and (o.get("content") or o.get("title")):
        return (f"[이번 화 = {no}화 「{o.get('title','')}」 — 계획서가 지정한 이 화의 내용이다.\n"
                f" 반드시 이 사건·전개를 이번 화로 집필하라. 앞당기거나 미루거나 바꾸지 마라]\n"
                f"{o.get('content','')}")
    return f"[이번 화의 위치] {no}화 = 비트 \"{beat['name']}\" — {beat.get('summary','')}"


def _prior_chapters_block(prev: list, budget: int = 240000) -> str:
    """지금까지 쓴 모든 화의 '본문 전체'를 넣는다.
    요약이 아니라 원본을 읽어야 앞뒤가 맞는다. 예산을 넘으면 앞쪽 화부터 요약으로 접는다."""
    if not prev:
        return "아직 없음. 이번이 1화다."
    # 뒤쪽(최근)부터 전문으로 채우고, 예산이 다하면 앞쪽은 요약으로
    full, folded, used = [], [], 0
    for p in reversed(prev):
        body = (p.get("body") or "").strip()
        piece = f"═══ {p['no']}화 「{p.get('title','')}」 ═══\n{body}\n"
        if used + len(piece) <= budget:
            full.append(piece)
            used += len(piece)
        else:
            folded.append(f"[{p['no']}화 「{p.get('title','')}」 요약] {p.get('summary','') or body[:200]}")
    full.reverse()
    folded.reverse()
    out = ""
    if folded:
        out += "── 앞부분 회차 (요약) ──\n" + "\n".join(folded) + "\n\n"
    out += "── 지금까지의 본문 (전문 — 반드시 이 내용과 앞뒤가 맞아야 한다) ──\n" + "\n".join(full)
    return out


def _later_chapters_block(later: list, budget: int = 120000) -> str:
    """이 화 '다음'에 이미 연재된 화들의 본문 — 다시 쓸 때 뒤와도 안 어긋나게."""
    if not later:
        return ""
    out, used = [], 0
    for p in later:  # 바로 다음 화부터 순서대로
        body = (p.get("body") or "").strip()
        piece = f"═══ {p['no']}화 「{p.get('title','')}」 ═══\n{body}\n"
        if used + len(piece) <= budget:
            out.append(piece)
            used += len(piece)
        else:
            out.append(f"[{p['no']}화 「{p.get('title','')}」 요약] {p.get('summary','') or body[:200]}")
    return "\n".join(out)


def _target_chars(w: dict) -> int:
    """이 작품의 회당 목표 글자수 (작가가 빌더에서 고른 값). 기본 5,000."""
    try:
        t = int(w.get("chars_per_chapter") or 5000)
    except (TypeError, ValueError):
        t = 5000
    return max(800, min(t, 12000))


def _chapter_prompt(w: dict, no: int, beat: dict, prev: list, directive: str,
                    later: list = None) -> str:
    target = _target_chars(w)
    chars = "\n".join(
        f"- {ch['name']} ({ch.get('archetype','')}): {ch.get('role','')} / "
        f"욕망: {ch.get('want','')} / 결핍: {ch.get('need','')} / 비밀: {ch.get('secret','')}"
        for ch in w["characters"])
    rels = "\n".join(f"- {r['a']} ↔ {r['b']}: {r.get('type','')} — {r.get('tension','')}"
                     for r in w["relations"])
    beats_map = "\n".join(f"{i+1}. {b['name']}: {b.get('summary','')}"
                          for i, b in enumerate(w["beats"]))

    canon = dict(_work_canon(w))  # 작가 고정 고유명사
    canon_lines = "\n".join(f"- {k}: {v}" if v else f"- {k}" for k, v in canon.items())
    prior = _prior_chapters_block(prev)
    later_block = _later_chapters_block(later) if later else ""
    rewriting = bool(later_block)

    return f"""당신은 정상급 웹소설 작가다. 아래 작품의 {no}화를 {'다시 ' if rewriting else ''}써라.
당신은 앞의 모든 화를 이미 다 읽었다. 앞에서 벌어진 사건·설정·수치·인물의 말투를
완벽히 기억한 상태로, 그와 모순 없이 이어서 써야 한다.
{'''지금은 이 화를 '다시 쓰는' 중이다. 아래에 이 화 앞의 내용과 뒤의 내용이 모두 주어진다.
새로 쓰는 이 화는 앞 화의 끝과 자연스럽게 이어지고, 뒤 화의 시작과도 매끄럽게 맞물려야 하며,
뒤 화에서 이미 벌어진 사건·밝혀진 정보·인물의 상태와 절대 모순되면 안 된다.''' if rewriting else ''}

{_brief_block(w)}
[작품] {w['title']} ({w['genre']}) — 총 {w['total_chapters']}화 예정
[로그라인] {w['premise']}
[고정된 결말 — 전체 이야기는 반드시 여기 도달한다] {w['ending']}
{_style_block(w)}

[인물 설정 — 이름·성격·말투·설정을 절대 어기지 마라]
{chars}
[관계도]
{rels}
{f'''[고유명사 사전 — 작가가 고정한 표기다. 이 표기 그대로만 써라]
{canon_lines}''' if canon_lines else ''}

[전체 플롯 지도 (Save the Cat 15비트)]
{beats_map}

{_this_chapter_block(w, no, beat)}

━━━━━━━━━━ 지금까지 연재된 내용 (이 화 앞) ━━━━━━━━━━
{prior}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{f'''
━━━━━━ 이 화 '다음'에 이미 연재된 내용 (여기와도 모순되면 안 된다) ━━━━━━
{later_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━''' if rewriting else ''}

{f'[작가의 지시 — 최우선으로 따르라] {directive}' if directive else ''}

집필 규칙:
- **앞 회차 절대 준수**: 위에 이미 쓰인 내용과 모순되면 안 된다.
  · 이미 일어난 사건을 다시 처음 일어난 것처럼 쓰지 마라 (예: 이미 치른 재회·고백·죽음·각성·승부의 결말).
  · 능력치·수치(포인트, 금액, 시청자 수, 날짜 등)는 앞 회차의 마지막 값에서 이어가라.
  · 인물의 말투·성격·호칭은 앞 회차에서 확립된 그대로 유지하라.
  · 앞에서 밝혀진 비밀·정보를 인물이 다시 모르는 상태로 되돌리지 마라.
- **분량: 공백 포함 {target:,}자 이상 ({target:,}~{int(target * 1.2):,}자).** 여러 장면으로 구성하라.
{DESCRIPTION_RULES}
- **심경 변화**는 반드시 이번 화의 사건이 원인이어야 하고, 몸짓과 대사로 단계적으로 보여라.
- **시간 일관성**: 앞 화가 끝난 시점 이후에서 시작하고, 낮/밤·이동시간·계절이 맞아야 한다.
- 역사물이면 인명·연호·관직·물건의 고증을 지켜라.
- 이번 화는 지정된 전개를 수행하되, 결말을 향해 한 걸음 전진해야 한다.
- 대화 비중 높게, 문단은 짧게. 앞 회차에서 이미 쓴 인상적 표현·비유·대사를 반복하지 마라.
- 마지막 문장은 절단신공으로 끝내라.

출력 형식 (정확히 지켜라):
제목: (이번 화 제목)
(본문)
///요약///
(이번 화에서 벌어진 핵심 사건과 인물·수치의 변화를 4~6문장으로)"""


def _mock_chapter(w: dict, no: int, beat: dict) -> str:
    return (f"제목: {no}화 — {beat['name']}\n"
            f"{w['title']}의 {no}화. {beat.get('summary','이야기가 전개된다.')}\n"
            "서진은 주먹을 쥐었다.\n\"여기서 물러서면, 전부 끝이야.\"\n"
            "그 순간, 문이 열렸다. 들어선 사람의 얼굴을 본 서진의 눈이 크게 흔들렸다.\n"
            "///요약///\n"
            f"{no}화: {beat['name']} 단계가 진행됐고, 마지막에 뜻밖의 인물이 등장했다.")


def _generate_full_chapter(w: dict, no: int, beat: dict, prev: list, directive: str,
                           later: list = None):
    """회차 생성 + 분량 보증 루프 — 5,000자에 못 미치면 프로그램이 이어쓰기를 시킨다.
    later가 있으면 '다시 쓰기'로 보고 이후 화들과도 모순 없게 한다.
    반환: (title, text, summary, error) — error가 있으면 저장하지 않는다."""
    raw = llm.write(_chapter_prompt(w, no, beat, prev, directive, later),
                    mock_text=_mock_chapter(w, no, beat), max_tokens=16000)
    if not llm.is_mock and llm.last_error:
        return None, None, None, llm.last_error
    title, text, summary = _parse_chapter(raw, no)
    min_chars = int(_target_chars(w) * 0.86)  # 목표의 86% 미만이면 이어쓰기
    tries = 0
    while not llm.is_mock and len(text) < min_chars and tries < 2:
        cont = llm.write(_continue_prompt(w, no, beat, text, directive),
                         mock_text="", max_tokens=16000)
        if not cont.strip():
            break
        _, more, s2 = _parse_chapter(cont, no)
        if not more.strip():
            break
        text = text.rstrip() + "\n\n" + more.strip()
        if s2:
            summary = s2
        tries += 1
    return title, text, summary, None


@router.post("/works/{work_id}/chapters")
def write_chapter(work_id: int, body: ChapterBody,
                  user: str = Header(default="solo", alias="X-User-Id")):
    if LAUNCH_MODE:
        return _LAUNCH_OFF
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

        title, text, summary, err = _generate_full_chapter(
            w, no, beat, prev, body.directive.strip())
        if err:
            return {"ok": False, "error": "회차 생성에 실패했어요. 저장하지 않았어요.",
                    "detail": f"AI 호출 오류 — {err}. 크레딧/사용량 한도를 확인하거나 Gemini로 전환하세요."}
        ch_id = c.insert_id(
            "INSERT INTO chapters (work_id, no, title, body, summary, state_json, directive, "
            "beat_idx, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
            (work_id, no, title, text, summary, "", body.directive.strip(),
             beat_for(no, w["total_chapters"])),
        )
        return {"ok": True, "id": ch_id, "no": no, "chars": len(text)}


def _parse_chapter(raw: str, no: int):
    """제목 / 본문 / 요약으로 분해한다."""
    title, summary = f"{no}화", ""
    text = raw.strip()
    # 옛 형식 호환: 혹시 모델이 ///상태/// 블록을 붙여도 본문에서 떼어낸다
    if "///상태///" in text:
        text = text.rsplit("///상태///", 1)[0]
    if "///요약///" in text:
        text, summary = text.rsplit("///요약///", 1)
        summary = summary.strip()
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("제목:"):
        title = lines[0].split(":", 1)[1].strip() or title
        lines = lines[1:]
    return title, "\n".join(lines).strip(), summary


MIN_CHAPTER_CHARS = 4300  # 이 밑이면 프로그램이 이어쓰기를 시킨다 (목표 5,000+)


def _continue_prompt(w: dict, no: int, beat: dict, body_so_far: str, directive: str) -> str:
    target = _target_chars(w)
    return f"""당신은 정상급 웹소설 작가다. 아래는 {w['title']} {no}화의 앞부분이다.
현재 {len(body_so_far)}자인데 연재 1회분(공백 포함 {target:,}자 이상)이 되려면 부족하다.
같은 화의 연속으로, 끊긴 지점에서 자연스럽게 이어서 써라.

{_brief_block(w, 3000)}
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
(화 '전체' 기준 요약 4~6문장)"""


@router.post("/chapters/{chapter_id}/regenerate")
def regen_chapter(chapter_id: int, body: ChapterBody,
                  user: str = Header(default="solo", alias="X-User-Id")):
    if LAUNCH_MODE:
        return _LAUNCH_OFF
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
        # 단일 '다시 쓰기'는 뒤 화들과도 맞춰야 한다. '모든 회차 다시 쓰기'(forward)는 앞만 본다.
        later = None
        if not body.forward:
            later = [dict(x) for x in c.execute(
                "SELECT no, title, summary, body FROM chapters WHERE work_id=? AND no>? ORDER BY no",
                (r["work_id"], r["no"])).fetchall()]
        beat = w["beats"][beat_for(r["no"], w["total_chapters"])]
        title, text, summary, err = _generate_full_chapter(
            w, r["no"], beat, prev, body.directive.strip(), later)
        if err:
            return {"ok": False, "error": "다시 쓰기에 실패했어요. 기존 회차는 그대로 유지됩니다.",
                    "detail": f"AI 호출 오류 — {err}. 크레딧/사용량 한도를 확인하세요."}
        c.execute("UPDATE chapters SET title=?, body=?, summary=?, state_json=?, directive=?, "
                  "updated_at=datetime('now') WHERE id=?",
                  (title, text, summary, "", body.directive.strip(), chapter_id))
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


def _stash(c, kind: str, user: str, data: dict) -> str:
    """삭제한 데이터를 휴지통(kv)에 보관하고 되돌리기 토큰을 돌려준다."""
    token = uuid.uuid4().hex[:12]
    db.kv_set(c, f"trash:{token}",
              json.dumps({"kind": kind, "user": user, **data}, ensure_ascii=False))
    return token


def _insert_row(c, table: str, row: dict, override: dict = None) -> int:
    """dict 한 줄을 그대로 되살린다 (id는 새로 발급)."""
    d = {k: v for k, v in row.items() if k != "id"}
    if override:
        d.update(override)
    cols = list(d.keys())
    ph = ",".join("?" * len(cols))
    return c.insert_id(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})",
                       tuple(d[k] for k in cols))


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: int, user: str = Header(default="solo", alias="X-User-Id")):
    """마지막 회차만 삭제 가능 — 중간을 비우면 기억이 끊긴다. 되돌리기 토큰을 준다."""
    with db.connect() as c:
        own = c.execute(
            "SELECT ch.no, ch.work_id FROM chapters ch JOIN works w ON w.id = ch.work_id "
            "WHERE ch.id=? AND w.user_id=?", (chapter_id, user)).fetchone()
        if not own:
            return {"ok": False, "error": "회차를 찾을 수 없어요."}
        last = c.execute("SELECT MAX(no) AS m FROM chapters WHERE work_id=?",
                         (own["work_id"],)).fetchone()["m"]
        if own["no"] != last:
            return {"ok": False, "error": "마지막 회차만 지울 수 있어요."}
        row = dict(c.execute("SELECT * FROM chapters WHERE id=?", (chapter_id,)).fetchone())
        token = _stash(c, "chapter", user, {"chapter": row})
        c.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
    return {"ok": True, "undo": token}


@router.delete("/works/{work_id}")
def delete_work(work_id: int, user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        w = c.execute("SELECT * FROM works WHERE id=? AND user_id=?", (work_id, user)).fetchone()
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        chapters = [dict(x) for x in c.execute(
            "SELECT * FROM chapters WHERE work_id=? ORDER BY no", (work_id,)).fetchall()]
        token = _stash(c, "work", user, {"work": dict(w), "chapters": chapters})
        c.execute("DELETE FROM chapters WHERE work_id=?", (work_id,))
        c.execute("DELETE FROM works WHERE id=?", (work_id,))
    return {"ok": True, "undo": token}


@router.post("/trash/{token}/restore")
def restore_trash(token: str, user: str = Header(default="solo", alias="X-User-Id")):
    """방금 삭제한 회차/작품을 되살린다."""
    with db.connect() as c:
        raw = db.kv_get(c, f"trash:{token}", "")
        if not raw:
            return {"ok": False, "error": "되돌릴 항목이 없어요 (이미 되돌렸거나 만료됐어요)."}
        data = json.loads(raw)
        if data.get("user") != user:
            return {"ok": False, "error": "권한이 없어요."}
        if data["kind"] == "chapter":
            ch = data["chapter"]
            if not c.execute("SELECT id FROM works WHERE id=? AND user_id=?",
                             (ch.get("work_id"), user)).fetchone():
                return {"ok": False, "error": "이 회차가 속한 작품이 사라졌어요."}
            _insert_row(c, "chapters", ch)
            out = {"ok": True, "kind": "chapter", "work_id": ch.get("work_id")}
        else:
            new_wid = _insert_row(c, "works", data["work"], override={"user_id": user})
            for ch in data.get("chapters", []):
                _insert_row(c, "chapters", ch, override={"work_id": new_wid})
            out = {"ok": True, "kind": "work", "id": new_wid}
        db.kv_set(c, f"trash:{token}", "")  # 되돌린 뒤엔 소비
    return out
