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
import urllib.error
import urllib.parse
import urllib.request
import uuid

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from pydantic import BaseModel

from . import db
from .engine.world import parse_llm_json
from .llm import llm

router = APIRouter(prefix="/api/writer")

# 판매용 런치 버전 — 소설 '본문 집필'과 거기 딸린 기능을 끈다.
# 기본은 '꺼짐'(전체 기능). 판매용 서버에서만 WRITER_LAUNCH_MODE=1 로 켠다.
# (기본값이 켜짐이면 개인 집필 서버가 코드 배포만으로 기능을 잃어 위험하다.)
LAUNCH_MODE = os.environ.get("WRITER_LAUNCH_MODE", "0") == "1"
DEMO_MODE = os.environ.get("NOVELIST_DEMO_MODE", "0") == "1"
_LAUNCH_OFF = {"ok": False, "error": "이 버전에서는 제공하지 않는 기능이에요."}


# 요금제 — 무료/라이트/프로. 질(회차 수·화당 줄거리 깊이·인물 수)로 차등한다.
TIERS = {
    "free":  {"label": "무료", "max_chapters": 3,  "syn_chars": 100,
              "max_characters": 3,  "max_works": 1,      "style_learning": False, "ads": True,
              "price": "무료", "period": "", "tagline": "가볍게 시작하기", "badge": "",
              "best_for": "웹소설 입문",
              "pitch": "아이디어 한 줄이면 인물·플롯·회차 줄거리까지 AI가 잡아줘요. 부담 없이 먼저 맛보세요.",
              "highlight": "무료로 전 과정 체험"},
    "light": {"label": "라이트", "max_chapters": 20, "syn_chars": 250,
              "max_characters": 7,  "max_works": 10,     "style_learning": False, "ads": False,
              "price": "₩4,900", "period": "/월", "tagline": "본격 연재 기획", "badge": "인기",
              "best_for": "연재 준비 작가",
              "pitch": "20화까지 상세 줄거리를 한 번에. 광고 없이, 작품 10개를 나란히 굴리며 연재를 준비하세요.",
              "highlight": "무료 대비 회차 6배 · 광고 없음"},
    "pro":   {"label": "프로", "max_chapters": 70, "syn_chars": 450,
              "max_characters": 10, "max_works": 100000, "style_learning": True,  "ads": False,
              "monthly_pens": 5, "body_writing": True,
              "price": "₩9,900", "period": "/월", "tagline": "프로 작가용", "badge": "추천",
              "best_for": "전업·다작 작가",
              "pitch": "70화 대작을 통째로 설계하고, 내 문체까지 학습시켜 나만의 결로. 매달 펜 5개로 본문까지 직접 씁니다.",
              "highlight": "문체 학습 · 본문 쓰기 · 매달 펜 5개"},
}
# 기본값 채우기 — 아래 등급은 본문 쓰기/월 펜 없음.
for _t in TIERS.values():
    _t.setdefault("monthly_pens", 0)
    _t.setdefault("body_writing", False)


# 스토어 상품 ID → 등급. (앱 커넥트/플레이 콘솔에서 만든 구독 상품 ID와 맞춘다)
PRODUCT_TIER = {
    "novelist.light.monthly": "light", "novelist.light.yearly": "light",
    "novelist.pro.monthly": "pro", "novelist.pro.yearly": "pro",
}

# 소모성 '펜' 상품 ID → 지급 개수. 펜 1개 = 본문 1편.
PEN_PRODUCTS = {
    "novelist.pen.1": 1,
    "novelist.pens.10": 10,
    "novelist.pens.50": 50,
    "novelist.pens.100": 100,
}
# 스토어 표시 정보 (플랜 화면 '펜 충전'에 쓰인다). count·price·per(개당).
PEN_PACKS = [
    {"product": "novelist.pen.1",   "count": 1,   "price": "₩990",    "per": "₩990"},
    {"product": "novelist.pens.10", "count": 10,  "price": "₩8,000",  "per": "개당 ₩800"},
    {"product": "novelist.pens.50", "count": 50,  "price": "₩35,000", "per": "개당 ₩700", "badge": "인기"},
    {"product": "novelist.pens.100","count": 100, "price": "₩60,000", "per": "개당 ₩600", "badge": "최저가"},
]


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


# ─────────────────────────── 펜(소모성 재화) ───────────────────────────
# 펜 1개 = 본문 1편. 서버가 잔액의 유일한 소스 오브 트루스다.
#  · 프로 구독자는 매달 monthly_pens 개를 자동 지급받는다.
#  · 스토어에서 펜을 사면 RevenueCat 웹훅(NON_RENEWING_PURCHASE)이 잔액을 올린다.
def _pen_balance(c, user: str) -> int:
    try:
        return max(0, int(db.kv_get(c, f"pens:{user}", "0") or "0"))
    except (TypeError, ValueError):
        return 0


def _pen_add(c, user: str, n: int) -> int:
    bal = _pen_balance(c, user) + max(0, int(n))
    db.kv_set(c, f"pens:{user}", str(bal))
    return bal


def _pen_spend(c, user: str, n: int = 1) -> bool:
    bal = _pen_balance(c, user)
    if bal < n:
        return False
    db.kv_set(c, f"pens:{user}", str(bal - n))
    return True


def _maybe_grant_monthly_pens(c, user: str) -> None:
    """프로 구독자에게 이번 달 펜을 아직 안 줬으면 지급한다 (한국시간 기준 월 1회)."""
    tier = _tier_name(c, user)
    give = _limits(tier).get("monthly_pens", 0)
    if give <= 0:
        return
    month = db.real_now().strftime("%Y-%m")   # 한국시간 월
    if db.kv_get(c, f"penmonth:{user}", "") == month:
        return
    db.kv_set(c, f"penmonth:{user}", month)
    _pen_add(c, user, give)


def _credit_pen_tx(c, user: str, product_id: str, tx_id: str) -> bool:
    """스토어 결제 1건으로 펜을 지급한다 — 거래 ID로 중복 지급을 막는다(멱등)."""
    n = PEN_PRODUCTS.get(product_id, 0)
    if n <= 0 or not user:
        return False
    mark = f"pentx:{tx_id}" if tx_id else ""
    if mark and db.kv_get(c, mark, ""):
        return False                          # 이미 지급된 거래
    _pen_add(c, user, n)
    if mark:
        db.kv_set(c, mark, "1")
    return True


def _body_gate(c, user: str):
    """'AI가 본문을 대신 써주는' 기능의 권한을 확인한다. (작가가 직접 쓰는 건 여기 안 걸린다)
      · 개인 집필 서버(WRITER_LAUNCH_MODE=0): 항상 허용, 펜 소모 없음.
      · 판매 빌드(=1): 아예 없는 기능이다 — 본문은 작가가 직접 쓴다.
    반환: (ok, consume, error_dict|None)"""
    if not LAUNCH_MODE:
        return True, False, None
    return False, False, {
        "ok": False, "need": "manual",
        "error": "이 앱은 본문을 작가가 직접 씁니다. 회차를 열어 바로 집필해 주세요."}


# ── 본문 예시(약 1,000자) — 하루 몇 건까지 ────────────────────────────────
# 등급별 기본 건수. 여기에 '광고를 본 횟수'만큼 1건씩 더해진다.
# 한국시간 자정에 리셋된다. 광고로 늘어나는 총량은 아래 AI_DAILY_CAP이 막아준다.
SAMPLE_BASE = {"free": 0, "light": 3, "pro": 10}
SAMPLE_CHARS = 1000
for _k, _v in SAMPLE_BASE.items():
    if _k in TIERS:
        TIERS[_k]["sample_daily"] = _v

# 하루 AI 호출 상한 — 비용 폭탄/남용 방지 안전망 (정상 사용엔 넉넉).
AI_DAILY_CAP = {"free": 40, "light": 250, "pro": 800}
for _k, _v in AI_DAILY_CAP.items():
    if _k in TIERS:
        TIERS[_k]["ai_daily"] = _v

# ── 판매(런치) 빌드의 플랜 = 판매 앱이 '실제로 하는 것'만 적는다 ──────────────
# 판매 앱의 정체성: AI가 세계관·인물·플롯·회차별 줄거리를 짜주고,
# 본문은 작가가 앱 안에서 직접 쓴다.
#   → AI 본문 대행 / 펜 / 문체 학습은 판매 빌드에 '없다'. 그러니 플랜 문구에서도 뺀다.
#     (없는 걸 팔면 스토어 심사에서도 걸리고, 산 사람이 못 찾는다.)
#   → 직접 쓰기는 핵심 기능이라 모든 등급에 열려 있다. 등급은 'AI가 짜주는 양'을 나눈다.
LAUNCH_TIER_COPY = {
    "free": {
        "pitch": "아이디어 한 줄이면 인물·플롯·회차 줄거리까지 AI가 잡아줘요. "
                 "본문은 앱 안에서 직접 씁니다.",
        "highlight": "AI 작품 설계 · 직접 집필",
    },
    "light": {
        "pitch": "20화까지 상세 줄거리를 한 번에. 광고 없이, 하루 3번의 1,000자 본문 예시로 문을 열어 보세요.",
        "highlight": "20화 설계 · 본문 예시 하루 3회 · 광고 없음",
    },
    "pro": {
        "pitch": "70화 대작을 통째로 설계하고, 화당 450자 상세 줄거리로 흐름을 놓치지 않아요. "
                 "작품 수 무제한, 하루 10번의 1,000자 본문 예시를 제공합니다.",
        "highlight": "70화 설계 · 본문 예시 하루 10회 · 작품 무제한",
    },
}
if LAUNCH_MODE:
    for _k, _over in LAUNCH_TIER_COPY.items():
        TIERS[_k].update(_over)
        TIERS[_k]["style_learning"] = False   # 문체 학습은 AI 본문용 — 판매 빌드엔 없다
        TIERS[_k]["body_writing"] = False     # AI 본문 대행 없음
        TIERS[_k]["monthly_pens"] = 0         # 펜도 없음


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


def _sample_quota(c, user: str) -> dict:
    """오늘 본문 예시를 몇 건 썼고 몇 건 남았는지. (광고 1회 = 1건 추가)"""
    day = db.real_now().date().isoformat()          # 한국시간 자정에 리셋
    base = SAMPLE_BASE.get(_tier_name(c, user), 1)
    used = int(db.kv_get(c, f"smpl:{user}:{day}", "0") or "0")
    extra = int(db.kv_get(c, f"smplad:{user}:{day}", "0") or "0")
    return {"used": used, "base": base, "extra": extra,
            "left": max(0, base + extra - used), "day": day}


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
        _maybe_grant_monthly_pens(c, user)     # 프로면 이번 달 펜 지급
        pens = _pen_balance(c, user)
        ent = None
        raw = db.kv_get(c, f"ent:{user}", "")
        if raw and _entitlement(c, user):
            try:
                ent = json.loads(raw).get("expires_at")
            except Exception:
                ent = None
    # 두 가지를 구분한다.
    #  · writing_enabled — 작가가 '직접' 쓰는 에디터. 핵심 기능이라 모든 등급에 열려 있다.
    #  · ai_body        — AI가 본문을 '대신' 써주는 기능. 판매 빌드에는 없다.
    ai_body = not LAUNCH_MODE           # 개인 서버는 등급과 무관하게 허용(_body_gate와 동일 규칙)
    with db.connect() as c:
        quota = _sample_quota(c, user)
    return {"launch_mode": LAUNCH_MODE, "demo_mode": DEMO_MODE,
            "ai_connected": not llm.is_mock,
            "writing_enabled": True, "ai_body": ai_body,
            "pens_enabled": not LAUNCH_MODE, "sample": quota, "sample_chars": SAMPLE_CHARS,
            "tier": t, "limits": TIERS[t], "tiers": TIERS, "expires_at": ent,
            "pens": pens, "pen_needed": False, "pen_packs": ([] if LAUNCH_MODE else PEN_PACKS)}


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


# ─────────────────────────── 인앱 결제(구독) 검증 ───────────────────────────
# 결제는 RevenueCat을 소스 오브 트루스로 쓴다. 앱(네이티브)의 RevenueCat SDK가
# App Store·Google Play 결제를 처리하고, 서버는 RevenueCat REST API로 '서버가 직접'
# 구독 상태를 확인한다(클라이언트 주장은 절대 신뢰하지 않음 = fail-closed).
#
#   · RevenueCat 대시보드에 Entitlement를 tier 이름 그대로 만든다: "light", "pro"
#   · 앱은 RevenueCat appUserID = 우리의 X-User-Id(기기 UUID)로 로그인시킨다
#   · 구매 성공 후 앱이 POST /entitlement 를 부르면, 서버가 아래로 재확인해 등급 부여
#   · 갱신·해지·환불은 RevenueCat 웹훅(POST /rc-webhook)이 서버 상태를 자동 갱신
#
# 환경변수(둘 다 Render 대시보드에서 설정):
#   REVENUECAT_SECRET        RevenueCat v1 시크릿 API 키 (Bearer)
#   REVENUECAT_WEBHOOK_AUTH  웹훅 Authorization 헤더로 받을 공유 비밀(임의 문자열)
REVENUECAT_SECRET = os.environ.get("REVENUECAT_SECRET", "")
REVENUECAT_WEBHOOK_AUTH = os.environ.get("REVENUECAT_WEBHOOK_AUTH", "")
# 높은 등급이 우선. RevenueCat entitlement 식별자 → 우리 tier 이름(동일하게 맞춘다).
_RC_TIER_PRIORITY = ["pro", "light"]


def _rc_subscriber(app_user_id: str):
    """RevenueCat에서 이 사용자의 subscriber 객체를 가져온다 (없으면 None)."""
    if not REVENUECAT_SECRET or not app_user_id:
        return None
    url = "https://api.revenuecat.com/v1/subscribers/" + urllib.parse.quote(app_user_id, safe="")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + REVENUECAT_SECRET,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None
    return (data or {}).get("subscriber") or None


def _rc_has_nonsub(app_user_id: str, product_id: str, tx_id: str = "") -> str:
    """이 사용자가 해당 소모성 상품을 실제로 샀는지 RevenueCat로 확인한다.
    반환: 스토어 거래 ID(멱등 키)로 쓸 문자열, 없으면 ""."""
    sub = _rc_subscriber(app_user_id)
    if not sub:
        return ""
    txs = (sub.get("non_subscriptions") or {}).get(product_id) or []
    if not txs:
        return ""
    if tx_id:                                   # 특정 거래를 지정했으면 그것만 인정
        for t in txs:
            if tx_id in (t.get("store_transaction_id"), t.get("id")):
                return t.get("store_transaction_id") or t.get("id") or tx_id
        return ""
    last = txs[-1]                              # 지정 안 했으면 가장 최근 거래
    return last.get("store_transaction_id") or last.get("id") or ""


def _rc_lookup(app_user_id: str):
    """RevenueCat에 '이 사용자'의 활성 구독을 서버가 직접 물어본다.
    반환: {"tier": "...", "expires_at": "...|None"} 또는 None(활성 구독 없음/미설정)."""
    sub = _rc_subscriber(app_user_id)
    if not sub:
        return None
    ents = sub.get("entitlements") or {}
    now = datetime.datetime.now(datetime.timezone.utc)
    for tier in _RC_TIER_PRIORITY:            # 높은 등급부터
        e = ents.get(tier)
        if not e:
            continue
        exp = e.get("expires_date")           # ISO8601 또는 None(영구)
        if exp:
            try:
                if datetime.datetime.fromisoformat(str(exp).replace("Z", "+00:00")) < now:
                    continue                  # 이미 만료
            except ValueError:
                continue
        if tier in TIERS:
            return {"tier": tier, "expires_at": exp}
    return None


def _grant_from_rc(user: str) -> dict:
    """RevenueCat 확인 결과로 ent를 갱신(활성 없으면 무료로 내림). 결과 dict 반환."""
    v = _rc_lookup(user)
    with db.connect() as c:
        if v:
            ent = {"tier": v["tier"], "platform": "revenuecat",
                   "expires_at": v.get("expires_at"),
                   "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
            db.kv_set(c, f"ent:{user}", json.dumps(ent, ensure_ascii=False))
            return {"ok": True, "tier": v["tier"], "limits": TIERS[v["tier"]],
                    "expires_at": v.get("expires_at")}
        db.kv_set(c, f"ent:{user}", "")        # 활성 구독 없음 → 무료
        return {"ok": True, "tier": "free", "limits": TIERS["free"], "expires_at": None}


class EntitlementBody(BaseModel):
    platform: str = "ios"      # ios | android (참고용 — 검증은 RevenueCat이 한다)
    product_id: str = ""


@router.post("/entitlement")
def set_entitlement(body: EntitlementBody, user: str = Header(default="solo", alias="X-User-Id")):
    """앱에서 구매·복원 직후 호출. 서버가 RevenueCat로 재확인해 등급을 부여한다."""
    if not REVENUECAT_SECRET:
        return {"ok": False, "error": "결제 검증을 아직 사용할 수 없어요.",
                "detail": "서버에 RevenueCat(REVENUECAT_SECRET)이 연결되면 자동으로 적용됩니다."}
    return _grant_from_rc(user)


@router.post("/rc-webhook")
async def rc_webhook(request: Request):
    """RevenueCat 웹훅 — 갱신/해지/환불/만료 시 해당 사용자 등급을 자동 재동기화.
    RevenueCat 대시보드의 Webhook Authorization 헤더 값과 대조해 인증한다."""
    if not REVENUECAT_WEBHOOK_AUTH or \
       request.headers.get("authorization", "") != REVENUECAT_WEBHOOK_AUTH:
        return {"ok": False}                   # 인증 실패 — 조용히 무시
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False}
    ev = (payload or {}).get("event") or {}
    uid = ev.get("app_user_id") or ev.get("original_app_user_id")
    if not uid:
        return {"ok": True}
    product = ev.get("product_id") or ""
    if product in PEN_PRODUCTS:                 # 소모성 '펜' 구매 → 잔액 적립(멱등)
        tx = str(ev.get("transaction_id") or ev.get("id") or "")
        with db.connect() as c:
            _credit_pen_tx(c, uid, product, tx)
    else:                                       # 구독 이벤트 → 등급 재동기화
        _grant_from_rc(uid)
    return {"ok": True}


@router.get("/pens")
def get_pens(user: str = Header(default="solo", alias="X-User-Id")):
    """현재 펜 잔액 (프로면 이번 달 지급분 포함)."""
    with db.connect() as c:
        _maybe_grant_monthly_pens(c, user)
        return {"ok": True, "pens": _pen_balance(c, user), "packs": PEN_PACKS}


class PenPurchaseBody(BaseModel):
    product_id: str = ""
    transaction_id: str = ""


@router.post("/pens/purchase")
def pens_purchase(body: PenPurchaseBody, user: str = Header(default="solo", alias="X-User-Id")):
    """앱이 소모성 결제 직후 호출 — 서버가 RevenueCat로 확인해 펜을 적립한다(멱등).
    웹훅이 먼저 처리했다면 여기선 중복 없이 현재 잔액만 돌려준다."""
    if not LAUNCH_MODE:                         # 개인 서버는 결제가 필요 없다
        return {"ok": False, "error": "이 서버에서는 펜 구매가 필요 없어요."}
    if body.product_id not in PEN_PRODUCTS:
        return {"ok": False, "error": "알 수 없는 상품이에요."}
    if not REVENUECAT_SECRET:
        return {"ok": False, "error": "결제 검증을 아직 사용할 수 없어요."}
    # RevenueCat에 이 사용자의 비구독(소모성) 거래가 실제로 있는지 확인한 뒤 적립.
    # 반환된 스토어 거래 ID를 멱등 키로 써서 웹훅과 중복 지급을 막는다.
    verified_tx = _rc_has_nonsub(user, body.product_id, body.transaction_id)
    with db.connect() as c:
        if verified_tx:
            _credit_pen_tx(c, user, body.product_id, verified_tx)
        return {"ok": True, "pens": _pen_balance(c, user)}


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


class PenGrantBody(BaseModel):
    user_id: str
    pens: int = 5


@router.post("/admin/pens")
def admin_pens(body: PenGrantBody, secret: str = Header(default="", alias="X-Admin-Secret")):
    """운영자 수동 펜 지급 (테스트·보상용)."""
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        return {"ok": False, "error": "권한이 없어요."}
    with db.connect() as c:
        bal = _pen_add(c, body.user_id, max(0, body.pens))
    return {"ok": True, "pens": bal}


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
        c.execute("DELETE FROM kv WHERE k=?", (f"pens:{user}",))
        c.execute("DELETE FROM kv WHERE k=?", (f"penmonth:{user}",))
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
    description: str = ""


class CharIn(BaseModel):
    name: str = ""
    role: str = ""
    relation: str = ""
    want: str = ""
    need: str = ""
    secret: str = ""
    # 단계별 설계에서 받는 항목들
    age: str = ""
    personality: str = ""       # 성격 (여러 개)
    fear: str = ""              # 가장 두려워하는 것
    facade: str = ""            # 사람들에게 보이는 모습
    truth: str = ""             # 자신의 실제 모습
    description: str = ""       # 작품 속에서 맡는 기능과 갈등을 설명하는 인물 소개


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
    structure: str = ""          # 이야기 구성 방식 (시간 흐름·정보 전달·반전·플롯 유형)
    outline: list[OutlineIn] = []


def _sec(title: str, body: str) -> str:
    body = (body or "").strip()
    return f"## {title}\n{body}\n\n" if body else ""


def _assemble_brief(b: BuildBody) -> str:
    """구조화된 빌더 입력을 사람이 읽는 정식 기획안 텍스트로 조립한다.
    회차별 전개는 'N화. 제목' 형식으로 써서 extract_outline과도 호환된다."""
    out = [f"# {b.title.strip() or '무제'}\n"
           f"장르: {b.genre.strip() or '미정'} · 총 {max(5, b.total_chapters)}화\n"
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
    if any(x.strip() for x in (p.name, p.personality, p.want, p.need, p.secret,
                               p.arc, p.job, p.age, p.description)):
        tags = " · ".join(x.strip() for x in (p.age, p.job) if x.strip())
        pl = [f"{p.name.strip() or '주인공'}{' (' + tags + ')' if tags else ''}"]
        for label, val in (("성격", p.personality), ("욕망(want)", p.want),
                           ("결핍(need)", p.need), ("비밀", p.secret), ("성장 아크", p.arc),
                           ("작품 속 인물 설명", p.description)):
            if val.strip():
                pl.append(f"{label}: {val.strip()}")
        out.append(_sec("주인공", "\n".join(pl)))

    chars = [ch for ch in b.characters if ch.name.strip()]
    if chars:
        lines = []
        for ch in chars:
            head = ch.name.strip() + (f" ({ch.age.strip()})" if ch.age.strip() else "")
            parts = [f"- {head}"]
            for label, val in (("역할", ch.role), ("관계", ch.relation), ("성격", ch.personality),
                               ("원하는 것", ch.want), ("두려워하는 것", ch.fear),
                               ("결핍", ch.need), ("숨기는 것", ch.secret),
                               ("남에게 보이는 모습", ch.facade), ("실제 모습", ch.truth),
                               ("작품 속 인물 설명", ch.description)):
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
    out.append(_sec("이야기 구성 방식 (시간 흐름·정보 전달·반전·플롯)", b.structure))
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
    """앞 단계에서 확정한 기획을 그대로 저장해 작품을 생성한다.

    초안과 회차 설계에서 이미 AI를 사용했으므로 마지막 저장 단계에서는 AI를
    다시 호출하지 않는다. 이렇게 해야 응답 형식 오류나 일시적인 API 장애 때문에
    완성한 기획 전체를 잃는 일이 없다.
    """
    _cap_build(b)
    brief = _assemble_brief(b)
    if not (b.logline.strip() or b.ending.strip()):
        return {"ok": False, "error": "최소한 로그라인이나 결말 중 하나는 있어야 이야기가 방향을 잡아요."}
    if len(brief) < 200:
        return {"ok": False, "error": "설명서 내용이 아직 짧아요. 세계관·주인공·결말 등을 더 채워주세요 (최소 200자)."}
    with db.connect() as c:  # 요금제 작품 수 상한
        lim = _limits(_tier_name(c, user))
        made = c.execute("SELECT COUNT(*) AS n FROM works WHERE user_id=?", (user,)).fetchone()["n"]
        if made >= lim["max_works"]:
            return {"ok": False,
                    "error": f"{lim['label']} 요금제에서는 작품을 {lim['max_works']}개까지 만들 수 있어요.",
                    "detail": "기존 작품을 지우거나 상위 요금제로 올려 주세요.", "limit": "works"}
    total = max(5, b.total_chapters)

    # 회차별 전개 — 작가가 빌더에서 짠 것이 절대 기준. 없으면 조립 텍스트에서 추출.
    outline = [{"no": o.no, "title": o.title.strip(), "content": o.content.strip()}
               for o in sorted(b.outline, key=lambda o: o.no)
               if o.no and o.no >= 1 and (o.title.strip() or o.content.strip())]
    if not outline:
        outline = extract_outline(brief)
    if outline:
        total = max(outline[-1]["no"], total)

    # 인물과 관계도 사용자가 확정한 값을 그대로 옮긴다.
    characters = []
    seen_names = set()
    p = b.protagonist
    if p.name.strip():
        pname = p.name.strip()
        seen_names.add(pname)
        characters.append({
            "name": pname, "archetype": "주인공", "role": p.job.strip() or "주인공",
            "want": p.want.strip(), "need": p.need.strip(), "secret": p.secret.strip(),
            "personality": p.personality.strip(), "arc": p.arc.strip(), "age": p.age.strip(),
            "description": p.description.strip(),
        })
    relations = []
    for ch in b.characters:
        name = ch.name.strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        characters.append({
            "name": name, "archetype": "", "role": ch.role.strip(),
            "want": ch.want.strip(), "need": ch.need.strip(), "secret": ch.secret.strip(),
            "personality": ch.personality.strip(), "fear": ch.fear.strip(),
            "facade": ch.facade.strip(), "truth": ch.truth.strip(), "age": ch.age.strip(),
            "description": ch.description.strip(),
        })
        if ch.relation.strip():
            relations.append({"a": p.name.strip() or "주인공", "b": name,
                              "type": ch.relation.strip(), "tension": ""})
    characters = characters[:lim["max_characters"]]
    allowed_names = {ch["name"] for ch in characters}
    relations = [r for r in relations if r["b"] in allowed_names]

    # 15비트는 회차 설계를 위치에 따라 묶어 보여 주는 목차다. 새 내용을 만들지 않는다.
    beat_lines = [[] for _ in BEATS]
    for item in outline:
        idx = beat_for(int(item["no"]), total)
        text = f"{item['no']}화 {item['title']}".strip()
        if item["content"]:
            text += f": {item['content']}"
        beat_lines[idx].append(text)
    beats = [{"idx": i, "name": name, "summary": "\n".join(beat_lines[i])}
             for i, name in enumerate(BEATS)]

    canon = {cc.name.strip(): cc.desc.strip() for cc in b.canon if cc.name.strip()}
    sample = b.style_sample.strip()
    profile = analyze_style(sample) if len(sample) >= 300 else ""

    with db.connect() as c:
        work_id = c.insert_id(
            "INSERT INTO works (user_id, title, genre, brief, premise, ending, style, "
            "total_chapters, style_sample, style_profile, characters_json, relations_json, "
            "beats_json, outline_json, canon_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (user, b.title.strip() or "무제", b.genre.strip() or "웹소설",
             brief[:BRIEF_MAX], b.logline.strip(), b.ending.strip(),
             b.style.strip(), total, sample[:6000], profile,
             json.dumps(characters, ensure_ascii=False),
             json.dumps(relations, ensure_ascii=False),
             json.dumps(beats, ensure_ascii=False),
             json.dumps(outline, ensure_ascii=False),
             json.dumps(canon, ensure_ascii=False)),
        )
    return {"ok": True, "id": work_id, "outline_chapters": len(outline)}


def _demo_brief(b: BuildBody, max_characters: int) -> dict:
    """로컬 화면 점검용 기획안. 실제 배포에서는 명시적으로 켜지 않는다."""
    premise = b.logline.strip() or "주인공이 익숙한 일상을 뒤흔드는 사건과 마주한다."
    genre = b.genre.strip() or "장편소설"
    lead = b.protagonist
    named = [c for c in b.characters if c.name.strip()]
    if not lead.name.strip():
        chosen = next((c for c in named if "주인공" in c.role), named[0] if named else None)
        if chosen:
            lead = ProtIn(name=chosen.name, age=chosen.age, job=chosen.role,
                          personality=chosen.personality, want=chosen.want,
                          need=chosen.need or chosen.fear, secret=chosen.secret,
                          arc=chosen.truth)

    lead_name = lead.name.strip() or "주인공"
    protagonist = {
        "name": lead_name, "age": lead.age.strip(), "job": lead.job.strip() or "주인공",
        "personality": lead.personality.strip() or "쉽게 물러서지 않지만 속마음을 감춘다",
        "want": lead.want.strip() or "사건의 진실을 밝혀 자신의 삶을 되찾는 것",
        "need": lead.need.strip() or "혼자 해결하려는 태도에서 벗어나 타인을 믿는 것",
        "secret": lead.secret.strip() or "사건의 시작과 자신이 관련되어 있다는 사실",
        "arc": lead.arc.strip() or "회피하던 진실을 받아들이고 스스로 선택한다",
    }
    characters = []
    for c in named:
        if c.name.strip() == lead_name:
            continue
        characters.append({
            "name": c.name.strip(), "age": c.age.strip(), "role": c.role.strip() or "조력자",
            "relation": c.relation.strip() or f"{lead_name}의 선택에 영향을 주는 인물",
            "personality": c.personality.strip(), "want": c.want.strip(),
            "need": c.need.strip(), "secret": c.secret.strip(), "fear": c.fear.strip(),
            "facade": c.facade.strip(), "truth": c.truth.strip(),
        })
    characters = characters[:max(0, max_characters - 1)]
    canon = [{"name": x.name.strip(), "desc": x.desc.strip()}
             for x in b.canon if x.name.strip()]
    return {
        "title": b.title.strip() or f"{lead_name}의 선택", "genre": genre,
        "logline": premise,
        "intent": b.intent.strip() or "한 번의 선택이 관계와 삶을 어떻게 바꾸는지 따라간다.",
        "world_setting": b.world_setting.strip() or f"{premise} 이 사건이 현실처럼 작동하는 {genre}의 무대.",
        "world_rules": b.world_rules.strip() or "모든 선택에는 되돌릴 수 없는 대가가 따르며, 얻은 정보는 다음 사건의 조건이 된다.",
        "taboos": b.taboos.strip() or "인물은 확인하지 않은 진실을 함부로 공개할 수 없다.",
        "protagonist": protagonist, "characters": characters, "canon": canon,
        "style": b.style.strip() or "간결한 문장과 장면 중심의 전개",
        "ending": b.ending.strip() or f"{lead_name}은 진실을 받아들이고 처음과 다른 선택을 내린다.",
    }


@router.post("/brief/draft")
def draft_brief(b: BuildBody, user: str = Header(default="solo", alias="X-User-Id")):
    """지금까지 작가가 채운 내용을 존중하며, 빈 칸을 일관되게 채운 상세 기획을 짓는다.
    작가가 칸을 비우고 다시 누르면 그 칸만 새로 생성된다 (새로고침).
    요금제에 따라 자동 생성하는 인물 수가 달라진다."""
    if not (b.logline.strip() or b.genre.strip() or b.keywords.strip()):
        return {"ok": False, "error": "장르·로그라인·키워드 중 하나는 알려주세요. 거기서 상세 기획을 지어드릴게요."}
    _cap_build(b)
    with db.connect() as c:
        ok, _cap = _ai_gate(c, user)
        if not ok:
            return _AI_BUSY
        maxc = _limits(_tier_name(c, user))["max_characters"]
    if llm.is_mock:
        if not DEMO_MODE:
            return {"ok": False, "error": "AI 연결이 필요해요.",
                    "detail": "배포 환경의 AI 연결 상태를 확인해 주세요."}
        return {"ok": True, "draft": _demo_brief(b, maxc),
                "max_characters": maxc, "demo": True}
    filled = _assemble_brief(b)
    # 작가가 앞 단계에서 인물을 이미 만들었으면 새 인물을 지어내지 않는다 (설계상 인물은 작가의 몫)
    has_cast = bool((b.protagonist and (b.protagonist.name or "").strip())
                    or [c2 for c2 in (b.characters or []) if (getattr(c2, "name", "") or "").strip()])
    cast_rule = ("- characters·protagonist는 **작가가 적은 인물을 그대로** 옮겨라. "
                 "새 인물을 만들지 마라. 빈 칸(욕망·결핍·비밀 등)만 채워라."
                 if has_cast else
                 "- characters는 **정확히 {n}명**. 적대자·조력자·애정상대 등 원형을 고루, "
                 "각 인물의 want와 need는 어긋나게(입체성), 관계(relation)를 분명히.".format(n=maxc))
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
{cast_rule}
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


class SuggestBody(BaseModel):
    question: str = ""            # 무엇을 고르는 항목인지 (예: "작품 분위기")
    options: list[str] = []       # 고를 수 있는 보기
    pick: int = 1                 # 몇 개까지 고를지
    context: str = ""             # 지금까지의 선택(제목·로그라인·장르 등)


class CastFillBody(BaseModel):
    context: str = ""
    characters: list[dict] = []
    create_all: bool = False
    specs: list[dict] = []


@router.post("/brief/cast-fill")
def fill_cast(b: CastFillBody, user: str = Header(default="solo", alias="X-User-Id")):
    """기존 인물의 빈 칸을 채우거나, 주인공부터 전체 인물을 한 번에 만든다."""
    def clean_fields(raw_fields):
        fields = []
        for raw_f in (raw_fields or [])[:12]:
            if not isinstance(raw_f, dict):
                continue
            opts = [str(o).strip() for o in (raw_f.get("options") or []) if str(o).strip()][:60]
            if not opts:
                continue
            fields.append({"id": str(raw_f.get("id", ""))[:60],
                           "question": str(raw_f.get("question", ""))[:120],
                           "options": opts,
                           "pick": max(1, min(int(raw_f.get("pick") or 1), 5))})
        return fields

    with db.connect() as c:
        max_characters = _limits(_tier_name(c, user))["max_characters"]

    clean = []
    if b.create_all:
        fields = clean_fields(b.specs)
        clean = [{"index": i, "name": "", "fields": fields} for i in range(max_characters)]
    else:
        for raw_ch in (b.characters or [])[:12]:
            if not isinstance(raw_ch, dict):
                continue
            fields = clean_fields(raw_ch.get("fields"))
            if fields:
                clean.append({"index": int(raw_ch.get("index", len(clean))),
                              "name": str(raw_ch.get("name", ""))[:80], "fields": fields})
    if not clean:
        return {"ok": False, "error": "채울 인물 항목이 없어요."}

    if llm.is_mock:
        if not DEMO_MODE:
            return {"ok": False, "error": "AI 연결이 필요해요.",
                    "detail": "배포 환경의 AI 연결 상태를 확인해 주세요."}
        is_wind_story = "바람" in (b.context or "")
        names = (["하늬", "샛바람", "마파람", "높새", "갈바람", "된바람", "실바람", "돌개", "솔바람", "눈바람"]
                 if is_wind_story else
                 ["서윤", "민재", "하린", "도현", "수아", "지후", "예린", "태오", "나연", "현우"])
        role_targets = ["주인공", "조력자", "라이벌", "적대자", "동료", "친구", "가족", "연인", "스승", "사건의 열쇠를 가진 인물"]
        context_lines = [line.strip() for line in (b.context or "").splitlines() if line.strip()]
        title_line = next((line.split(":", 1)[1].strip() for line in context_lines
                           if line.startswith("제목:") and ":" in line), "이 작품")
        synopsis = next((line.split(":", 1)[1].strip() for line in context_lines
                         if line.startswith("로그라인:") and ":" in line), "작품의 중심 사건")
        result = []
        for i, ch in enumerate(clean):
            chosen = {}
            for f in ch["fields"]:
                opts = f["options"]
                if f["id"] == "role":
                    target = role_targets[min(i, len(role_targets) - 1)]
                    chosen[f["id"]] = [target if target in opts else opts[min(i, len(opts) - 1)]]
                else:
                    chosen[f["id"]] = [opts[(i + j) % len(opts)] for j in range(min(f["pick"], len(opts)))]
            row = {"index": ch["index"], "fields": chosen}
            if b.create_all:
                name = names[i % len(names)]
                role = (chosen.get("role") or ["등장인물"])[0]
                personality = ", ".join(chosen.get("personality") or [])
                want = (chosen.get("want") or ["자신의 목표"])[0]
                fear = (chosen.get("fear") or ["실패"])[0]
                secret = (chosen.get("secret") or ["감춰 둔 사정"])[0]
                facade = (chosen.get("facade") or ["겉으로 보이는 모습"])[0]
                truth = (chosen.get("truth") or ["내면의 실제 모습"])[0]
                description = (
                    f"{name}, 『{title_line}』에서 {role} 역할로 움직이는 {'의지를 지닌 바람' if is_wind_story else '인물'}이다. "
                    f"‘{synopsis}’라는 중심 사건 속에서 가장 원하는 것은 {want}이고, 가장 두려운 것은 {fear}이라 중요한 선택 앞에서 흔들린다. "
                    f"{personality} 성향 때문에 다른 인물들과 쉽게 충돌하거나 뜻밖의 결정을 내린다. "
                    f"겉으로는 {facade}처럼 보이지만 실제로는 {truth}에 가깝다. 숨긴 비밀은 {secret}이며, 이것이 사건의 방향을 바꾼다."
                )
                age = (f"{120 + i * 70}년" if is_wind_story else str(24 + i * 3))
                row.update({"name": name, "age": age, "description": description})
            result.append(row)
        return {"ok": True, "characters": result, "demo": True}

    with db.connect() as c:
        ok, _cap = _ai_gate(c, user)
        if not ok:
            return _AI_BUSY
    compact = [{"index": ch["index"], "name": ch["name"],
                "fields": [{"id": f["id"], "question": f["question"],
                            "options": f["options"], "pick": f["pick"]}
                           for f in ch["fields"]]} for ch in clean]
    create_rule = (f"- 서로 구분되는 인물 {len(clean)}명을 새로 만들어라. index 0은 반드시 주인공이다.\n"
                   "- 각 인물에 자연스러운 한국어 이름과 숫자로 된 나이를 반드시 넣어라."
                   if b.create_all else "- 전달된 인물의 이름은 바꾸지 말고 빈 설정만 채워라.")
    prompt = f"""당신은 프로 웹소설 인물 기획자다. 작품 맥락과 인물별 보기를 보고 인물진을 완성하라.

[작품 맥락]
{(b.context or '아직 없음')[:3000]}

[인물과 선택 가능한 보기]
{json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}

규칙:
{create_rule}
- 작품 속 인물이 인간이라고 가정하지 마라. 로그라인의 주체가 바람·동물·사물·정령이라면 이름, 나이,
  정체성, 행동 방식도 반드시 그 존재에 맞춰 만들어라. 특히 작품 고유의 소재를 평범한 인간 캐릭터로 바꾸지 마라.
- 반드시 각 field의 options 안에 있는 문구만 정확히 골라라.
- pick 수만큼 고르되, 같은 인물의 선택이 서로 모순되지 않게 하라.
- 각 인물의 description은 3~5문장으로 충분히 써라. 작품의 제목·로그라인·장르·세계관을 직접 반영하고,
  선택한 역할·성격·욕망·두려움·비밀·겉모습·실제 모습을 모두 연결해 이 인물이 작품에서 무엇을 하고
  어떤 갈등을 만드는지 구체적으로 설명하라. 어느 작품에나 붙일 수 있는 일반적인 소개는 금지한다.
- 모든 index와 field id를 빠짐없이 반환하라.
- 아래 형식의 JSON만 출력하라.
{{"characters":[{{"index":0,"name":"서윤","age":"29","description":"작품과 설정을 반영한 인물 설명","fields":{{"role":["주인공"],"personality":["침착하다"]}}}}]}}"""
    raw = llm.write(prompt, mock_text="", max_tokens=5000)
    data = parse_llm_json(raw)
    rows = data.get("characters") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {"ok": False, "error": "인물 설정을 채우지 못했어요.",
                "detail": llm.last_error or "AI 응답 형식을 확인해 주세요."}

    specs = {ch["index"]: {f["id"]: f for f in ch["fields"]} for ch in clean}
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        chosen = {}
        for fid, values in (row.get("fields") or {}).items():
            spec = specs.get(idx, {}).get(str(fid))
            if not spec:
                continue
            if not isinstance(values, list):
                values = [values]
            valid = [str(v) for v in values if str(v) in spec["options"]][:spec["pick"]]
            if valid:
                chosen[str(fid)] = valid
        if chosen:
            item = {"index": idx, "fields": chosen}
            if b.create_all:
                name = str(row.get("name", "")).strip()[:80]
                if not name:
                    continue
                description = str(row.get("description", "")).strip()[:1600]
                if not description:
                    continue
                item.update({"name": name, "age": str(row.get("age", "")).strip()[:20],
                             "description": description})
            result.append(item)
    if not result:
        return {"ok": False, "error": "인물 설정을 채우지 못했어요. 다시 시도해 주세요."}
    return {"ok": True, "characters": result}


@router.post("/brief/suggest")
def suggest_choice(b: SuggestBody, user: str = Header(default="solo", alias="X-User-Id")):
    """단계별 설계에서 'AI에게 추천받기' — 지금까지의 설정에 가장 어울리는 보기를 고른다.
    보기 중에서만 고르므로 응답이 짧고 값이 싸다."""
    opts = [o.strip() for o in (b.options or []) if o.strip()][:60]
    if not opts:
        return {"ok": False, "error": "고를 보기가 없어요."}
    n = max(1, min(int(b.pick or 1), 5))
    if llm.is_mock:
        if not DEMO_MODE:
            return {"ok": False, "error": "AI 연결이 필요해요.",
                    "detail": "배포 환경의 AI 연결 상태를 확인해 주세요."}
        return {"ok": True, "picked": opts[:n],
                "reason": "미리보기용 예시 추천입니다.", "demo": True}
    with db.connect() as c:
        ok, _cap = _ai_gate(c, user)
        if not ok:
            return _AI_BUSY
    prompt = f"""당신은 프로 웹소설 기획자다. 아래 작품에 가장 어울리는 '{b.question}'을 고르라.

[지금까지 정해진 것]
{(b.context or '아직 없음')[:2000]}

[보기 — 반드시 이 중에서만 고른다]
{chr(10).join('- ' + o for o in opts)}

정확히 {n}개를 고르고, 아래 JSON만 출력하라 (설명·코드펜스 금지).
{{"picked": ["보기 그대로 정확히"], "reason": "왜 이게 어울리는지 한 문장"}}"""
    raw = llm.write(prompt, mock_text="", max_tokens=600)
    if llm.last_error:
        return {"ok": False, "error": "추천을 받지 못했어요.", "detail": llm.last_error}
    data = parse_llm_json(raw) or {}
    picked = [p for p in (data.get("picked") or []) if p in opts][:n]
    if not picked:                                   # 형식이 틀리면 비슷한 것 찾아보기
        for p in (data.get("picked") or []):
            for o in opts:
                if p and (p in o or o in p) and o not in picked:
                    picked.append(o)
                    break
        picked = picked[:n]
    if not picked:
        return {"ok": False, "error": "추천을 받지 못했어요. 다시 시도해 주세요."}
    return {"ok": True, "picked": picked, "reason": str(data.get("reason", ""))[:200]}


class SampleBody(BuildBody):
    work_id: int = 0        # 이미 만든 작품에서 부를 때
    no: int = 0             # 몇 화의 예시인지 (0이면 도입부)


SAMPLE_NOTE = ("이 예시는 작품을 쓰는데 도움이 되도록 설정된 내용을 반영한 본문 예시입니다. "
               "전체적인 흐름과는 다소 차이가 날 수 있으며, 본문 작성에 참고용으로 이용 바랍니다.")


@router.get("/sample/quota")
def sample_quota(user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        return {"ok": True, "sample": _sample_quota(c, user), "chars": SAMPLE_CHARS}


@router.post("/sample/ad")
def sample_ad_reward(user: str = Header(default="solo", alias="X-User-Id")):
    """광고를 끝까지 본 대가로 예시 1건을 더 준다."""
    with db.connect() as c:
        q = _sample_quota(c, user)
        db.kv_set(c, f"smplad:{user}:{q['day']}", str(q["extra"] + 1))
        return {"ok": True, "sample": _sample_quota(c, user)}


@router.post("/brief/sample")
def write_sample(b: SampleBody, user: str = Header(default="solo", alias="X-User-Id")):
    """설정한 내용을 그대로 반영한 '본문 예시' 한 토막(약 1,000자)을 쓴다.
    회차 본문이 아니다 — 작가가 문체·분위기를 가늠하고 참고하라고 만드는 것이다."""
    if llm.is_mock:
        return {"ok": False, "error": "AI가 연결되어 있지 않아요.",
                "detail": "API 키/사용량 한도를 확인해 주세요."}
    _cap_build(b)
    with db.connect() as c:
        q = _sample_quota(c, user)
        if q["base"] <= 0:
            return {"ok": False, "need": "tier", "sample": q,
                    "error": "라이트 버전 이상에서만 제공됩니다."}
        if q["left"] <= 0:
            return {"ok": False, "need": "ad", "sample": q,
                    "error": "오늘 쓸 수 있는 예시를 다 썼어요. 광고를 보면 1건 더 만들 수 있어요."}
        ok, _cap = _ai_gate(c, user)
        if not ok:
            return _AI_BUSY
        db.kv_set(c, f"smpl:{user}:{q['day']}", str(q["used"] + 1))   # 먼저 차감(중복 요청 방지)
        # 작품에서 부른 경우엔 그 화의 줄거리를 함께 넣어 준다
        plan_line = ""
        if b.work_id:
            w = _load_work(c, b.work_id, user)
            if w:
                o = next((x for x in (w.get("outline") or []) if int(x.get("no", 0)) == b.no), None)
                if o:
                    plan_line = f"\n[이 화의 줄거리]\n{o.get('title', '')} — {o.get('content', '')}"
    where = f"{b.no}화의 한 장면" if b.no else "1화 도입부"
    prompt = f"""당신은 프로 웹소설 작가다. 아래 기획을 그대로 반영해 {where}를 약 {SAMPLE_CHARS}자로 써라.
작가가 '내 설정이 글로 나오면 어떤 느낌인지' 확인하려고 보는 예시다.

[기획]
{_assemble_brief(b)}{plan_line}

규칙:
- 정해진 인물 이름·세계관·금기를 그대로 쓴다. 새로 지어내지 마라.
- 정한 문체·분위기가 드러나게 쓴다. 이게 이 예시의 목적이다.
- 장면 하나에 집중한다. 요약·설명이 아니라 실제 본문처럼 대사와 묘사로.
- 같은 표현을 반복하지 마라.
- 약 {SAMPLE_CHARS}자. 제목·머리말·설명 없이 본문만 출력하라."""
    raw = llm.write(prompt, mock_text="", max_tokens=2600)
    text = (raw or "").strip()
    if not text:
        with db.connect() as c:                       # 실패했으면 차감을 되돌린다
            q2 = _sample_quota(c, user)
            db.kv_set(c, f"smpl:{user}:{q2['day']}", str(max(0, q2["used"] - 1)))
            back = _sample_quota(c, user)
        return {"ok": False, "sample": back, "error": "예시를 만들지 못했어요. 다시 시도해 주세요.",
                "detail": llm.last_error or "빈 응답"}
    with db.connect() as c:
        left = _sample_quota(c, user)
    return {"ok": True, "text": text, "chars": len(text), "note": SAMPLE_NOTE, "sample": left}


@router.post("/brief/outline")
def draft_outline(b: BuildBody, user: str = Header(default="solo", alias="X-User-Id")):
    """지금까지 채운 설정을 바탕으로 회차별 전개(1화~N화)를 통째로 생성한다.
    요금제에 따라 '몇 화까지'와 '화당 줄거리 깊이(글자수)'가 달라진다."""
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
    if llm.is_mock:
        if not DEMO_MODE:
            return {"ok": False, "error": "AI 연결이 필요해요.",
                    "detail": "배포 환경의 AI 연결 상태를 확인해 주세요."}
        titles = ["사건의 시작", "첫 번째 선택", "되돌릴 수 없는 변화",
                  "숨겨진 진실", "결말을 향한 선택"]
        premise = b.logline.strip() or b.world_setting.strip()
        ending = b.ending.strip() or "주인공이 진실을 받아들이고 자신의 선택을 내린다."
        outline = []
        for no in range(1, total + 1):
            title = titles[min(len(titles) - 1, (no - 1) * len(titles) // max(1, total))]
            if no == 1:
                content = f"{premise} 일상을 깨뜨리는 구체적인 사건이 벌어지고, 주인공은 외면할 수 없는 단서를 얻는다."
            elif no == total:
                content = f"쌓인 갈등과 비밀이 한자리에서 충돌한다. {ending}"
            else:
                content = "이전 선택의 대가가 드러나며 갈등이 커진다. 주인공은 새로운 정보를 얻고 더 위험한 다음 선택을 한다."
            outline.append({"no": no, "title": title, "content": content})
        return {"ok": True, "outline": outline, "capped": requested > total,
                "tier_max": lim["max_chapters"], "syn_chars": syn,
                "tier_label": lim["label"], "requested": requested,
                "missing": [], "demo": True}
    context = _assemble_brief(b)
    beats_guide = "\n".join(
        f"- {int(edge*100)}%까지: {name}" for name, edge in zip(BEATS, BEAT_EDGES))
    # 초기 설정에서 고른 '이야기 구성 방식'(플롯 유형·시간 흐름·정보 전달·반전)을 반드시 지킨다
    shape = (b.structure or "").strip()
    shape_rule = (f"\n[반드시 지킬 구성 방식 — 작가가 고른 것]\n{shape}\n"
                  "이 구성 방식대로 회차를 배열하라. 예를 들어 시간 흐름이 역순·교차라면 "
                  "회차 순서도 그렇게 짜고, 반전 방식이 정해져 있으면 그 자리에 배치하라. "
                  "아래 비트 가이드보다 이 구성 방식이 우선이다.\n" if shape else "")
    prompt = f"""당신은 웹소설 플롯 설계자다. 아래 기획을 바탕으로 {total}화 전체의 '회차별 전개'를 짜라.
Save the Cat 15비트를 회차 진행률에 맞춰 배치하고, 반드시 고정된 결말로 수렴시켜라.

[기획]
{context}

{shape_rule}
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
    raw = llm.write(prompt, mock_text="", max_tokens=32000)
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
    # 모델이 중간에 끊어 빠진 화가 있으면 한 번만 보충한다 (25화 골랐는데 몇 개만 나오던 문제)
    have = {o["no"] for o in outline}
    missing = [n for n in range(1, total + 1) if n not in have]
    if missing:
        done = "\n".join(f"{o['no']}화: {o['title']} — {o['content'][:80]}" for o in outline[-6:])
        fix = llm.write(
            f"""아래 웹소설의 회차 전개에서 {missing[0]}화~{missing[-1]}화가 빠졌다. 그 화들만 채워라.

[기획]
{context[:4000]}

[직전까지의 전개]
{done}

출력: {{"outline":[{{"no":{missing[0]},"title":"제목","content":"약 {syn}자"}}]}}
- no는 {', '.join(str(n) for n in missing[:60])} 만. 빠짐없이.
- 각 화 content는 약 {syn}자. 압축 JSON만 출력.""",
            mock_text="", max_tokens=32000)
        more = parse_llm_json(fix)
        more = more.get("outline") if isinstance(more, dict) else (more if isinstance(more, list) else [])
        for it in (more or []):
            if not isinstance(it, dict):
                continue
            try:
                no = int(it.get("no"))
            except (TypeError, ValueError):
                continue
            if no in have or not (1 <= no <= total):
                continue
            have.add(no)
            outline.append({"no": no, "title": str(it.get("title", "")).strip(),
                            "content": str(it.get("content", "")).strip()})
    outline.sort(key=lambda o: o["no"])
    return {"ok": True, "outline": outline, "capped": requested > total,
            "tier_max": lim["max_chapters"], "syn_chars": syn, "tier_label": lim["label"],
            "requested": requested, "missing": [n for n in range(1, total + 1) if n not in have]}


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
    # 예전에 만든 작품의 기획안에도 남아 있는 회당 글자 수 목표를 노출하거나
    # 이후 AI 기획 작업의 참고 정보로 사용하지 않는다.
    w["brief"] = re.sub(
        r"\s*(?:·\s*)?회당 목표\s*[\d,]+\s*자", "", w.get("brief") or ""
    )
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
            n = c.execute("SELECT COUNT(*) AS n FROM chapters "
                          "WHERE work_id=? AND LENGTH(TRIM(COALESCE(body,'')))>0",
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
            "SELECT id, no, title, summary, beat_idx, directive, "
            "LENGTH(COALESCE(body,'')) AS chars FROM chapters WHERE work_id=? ORDER BY no",
            (work_id,)).fetchall()]
        return {"ok": True,
                "work": {k: w.get(k) for k in ("id", "title", "genre", "premise", "ending",
                                               "style", "total_chapters", "characters",
                                               "relations", "beats", "brief", "outline", "canon",
                                               "style_profile", "style_sample")},
                "chapters": chapters}


class BibleBody(BaseModel):
    title: str = ""
    ending: str = ""
    characters: list = []
    relations: list = []
    beats: list = []
    total_chapters: int = 0       # 0이면 그대로 둔다


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
        c.execute(
            "UPDATE works SET title=?, ending=?, characters_json=?, relations_json=?, "
            "beats_json=?, total_chapters=? WHERE id=?",
            (body.title.strip() or w["title"],
             body.ending.strip() or w["ending"],
             json.dumps(body.characters or w["characters"], ensure_ascii=False),
             json.dumps(body.relations or w["relations"], ensure_ascii=False),
             json.dumps(_normalize_beats(body.beats or w["beats"]), ensure_ascii=False),
             total, work_id),
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
        old = {o.get("no"): o for o in (w.get("outline") or [])}
        outline = []
        for o in sorted(body.outline, key=lambda o: o.no):
            if not o.no or o.no < 1 or not (o.title.strip() or o.content.strip()):
                continue
            item = {"no": o.no, "title": o.title.strip(), "content": o.content.strip()}
            outline.append(item)
        total = w["total_chapters"]
        if outline:
            total = max(total, outline[-1]["no"])
        c.execute("UPDATE works SET outline_json=?, total_chapters=? WHERE id=?",
                  (json.dumps(outline, ensure_ascii=False), total, work_id))
    return {"ok": True, "outline_count": len(outline)}


# NOTE: 예전의 '이름 일괄 변경(/rename)' 기능은 제거되었다.
# 그 기능은 이미 쓴 모든 회차 본문을 전역 문자열 치환해서, 짧은 이름 하나만 바꿔도
# 본문이 통째로 훼손되는 데이터 손실 사고를 냈다. 표기를 바꾸고 싶으면 아래
# '고유명사 사전(canon)'에 등록하라 — 이미 쓴 글은 절대 건드리지 않고, 다음 회차부터만
# 반영된다. (원칙: 어떤 수정도 기존 본문을 자동으로 다시 쓰지 않는다.)


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


def _overused_expressions(prev: list, top: int = 18) -> list:
    """앞 회차들에서 '이미 두 번 이상 쓴' 문장·구절을 뽑아낸다.
    이걸 프롬프트에 '재사용 금지 목록'으로 넣어 같은 묘사·표현 반복을 막는다."""
    if not prev:
        return []
    text = "\n".join((p.get("body") or "") for p in prev)
    counts = {}
    for u in re.split(r"[\n.!?…]+|[,]\s", text):
        u = u.strip(" \t\"'“”‘’—-·…")
        if 6 <= len(u) <= 40:               # 너무 짧은 상투구/너무 긴 문장은 제외
            counts[u] = counts.get(u, 0) + 1
    reps = sorted((u for u, n in counts.items() if n >= 2),
                  key=lambda u: (-counts[u], -len(u)))
    out = []
    for u in reps:                          # 다른 항목에 포함되는 조각은 버린다
        if any(u != v and u in v for v in out):
            continue
        out.append(u)
        if len(out) >= top:
            break
    return out


# 자주 나오는 조사/접속어 — 장면 검출에서 잡음이 되므로 이음말 계산에서 뺀다.
_MOTIF_STOP = set("그리고 그러나 하지만 그래서 그때 그러자 그런데 이내 결국 마침내 순간 "
                  "다시 이제 여기 저기 이것 그것 무엇 자신 서로 모든 함께 정도 때문 "
                  "것이다 것을 수는 수가 채로".split())


def _content_words(text: str) -> list:
    """본문을 '내용어' 토큰으로 쪼갠다 (2글자 이상, 흔한 접속어 제외)."""
    ws = re.findall(r"[가-힣A-Za-z0-9]+", text or "")
    return [w for w in ws if len(w) >= 2 and w not in _MOTIF_STOP]


def _chapter_bigrams(body: str) -> set:
    """한 회차 안에서 붙어 나오는 내용어 쌍(이음말)의 집합."""
    ws = _content_words(body)
    return set(zip(ws, ws[1:]))


def _story_names(w: dict) -> set:
    """인물명·고유명사 — 매 회차 반복돼도 정상이므로 장면 검출에서 제외한다."""
    ns = set()
    for ch in (w.get("characters") or []):
        n = (ch.get("name") or "").strip()
        if n:
            ns.add(n)
    for k in (_work_canon(w) or {}):
        ns.add(k)
    return ns


def _recurring_motifs(prev: list, w: dict, top: int = 16) -> list:
    """여러 '회차에 걸쳐' 반복되는 이음말을 뽑는다 = 반복되는 장면·행동의 신호.
    (한 회차 안 반복이 아니라, 서로 다른 회차에서 같은 상황이 되풀이되는 것을 잡는다.)
    반환: [(a, b), ...] 반복 강한 순."""
    if not prev or len(prev) < 2:
        return []
    names = _story_names(w)
    df = {}
    for p in prev:                              # 회차별로 '있다/없다'만 센다(문서빈도)
        for bg in _chapter_bigrams(p.get("body") or ""):
            df[bg] = df.get(bg, 0) + 1
    need = max(2, round(len(prev) * 0.34))      # 전체 회차의 1/3 이상에서 반복될 때
    cands = [(bg, n) for bg, n in df.items()
             if n >= need and not (bg[0] in names and bg[1] in names)]
    cands.sort(key=lambda x: (-x[1], -(len(x[0][0]) + len(x[0][1]))))
    return [bg for bg, _ in cands[:top]]


# 소설에서 자연스럽게 자주 나오는 흔한 단어 — 반복이라 볼 수 없으니 '과다 단어'에서 제외한다.
# (여기 없는 '고유한 단어'가 자꾸 나오는 게 진짜 문제 — 예: 삼나무·피맛·보랏빛)
_COMMON_WORDS = set((
    "나 너 그 저 이 우리 당신 그녀 그들 자신 서로 스스로 누구 무엇 무언가 어디 언제 "
    "이것 그것 저것 여기 저기 거기 이곳 그곳 것 수 때 곳 점 뿐 채 만큼 정도 무렵 "
    "사람 남자 여자 사이 동안 하나 둘 셋 모두 전부 세상 세계 자리 모습 상황 경우 "
    "순간 시간 하루 오늘 내일 어제 지금 이제 방금 아침 저녁 밤 낮 새벽 하늘 바닥 벽 "
    "눈 손 말 얼굴 목소리 마음 생각 시선 표정 공기 소리 숨 가슴 머리 몸 눈빛 목 입 "
    "발 등 어깨 고개 손끝 눈앞 입술 팔 다리 피부 심장 이마 뺨 턱 코 귀 뒤통수 "
    "안 앞 뒤 위 아래 옆 속 밖 방 문 창 빛 어둠 그림자 공간 주변 사방 "
    "그리고 그러나 하지만 그래서 그런데 그러자 그러니 이내 결국 마침내 다시 이제 "
    "아주 조금 정말 그저 마치 문득 이미 아직 여전히 천천히 그때 곧 잠시 어느 "
    "무슨 어떤 이런 그런 저런 모든 그만 더욱 훨씬 가장 매우 계속 함께 그대로 "
    "이렇게 그렇게 저렇게 왜 어떻게 얼마나 대답 질문 대화 웃음 눈물 걸음 발걸음 "
    "동시 순식간 한동안 방향 소년 소녀 목적 이유 방법 사실 진실 존재 자체 부분 전체 "
).split())


# 흔한 조사·어미 — 단어 뒤에 붙는 걸 떼어내 '삼나무/삼나무의/삼나무가'를 한 단어로 본다.
_JOSA = ("으로써 으로서 으로부터 에게서 에서도 에게도 이라도 이라는 이라고 이나마 "
         "으로 에게 한테 에서 부터 까지 보다 처럼 마저 조차 이라 이며 이나 라도 라고 라는 "
         "은 는 이 가 을 를 에 의 도 로 와 과 만 께 나 며 고 라 야 서").split()


def _norm_word(wd: str) -> str:
    """단어 뒤에 붙은 조사 하나를 떼어 표제어에 가깝게 만든다 (한글만, 최소 2자 유지)."""
    if not wd or not ("가" <= wd[0] <= "힣"):
        return wd
    for j in _JOSA:                              # 긴 조사부터 시도
        if wd.endswith(j) and len(wd) - len(j) >= 2:
            return wd[:-len(j)]
    return wd


def _word_counts(text: str):
    """본문 속 '내용어'의 등장 횟수 (조사 정규화 후, 한 회차 안에서)."""
    d = {}
    for wd in _content_words(text):
        n = _norm_word(wd)
        d[n] = d.get(n, 0) + 1
    return d


def _overused_words(prev: list, w: dict, top: int = 14) -> list:
    """여러 회차에 '단어 하나'가 너무 자주 나오는 것을 뽑는다 (길이 제한 없음).
    인물명·고유명사(조사 붙은 형태 포함)·흔한 서술어는 빼고, 고유한데 반복되는 단어만 남긴다.
    반환: 반복 많은 순 단어 리스트 (삼나무·피맛·보랏빛 같은 것)."""
    if not prev:
        return []
    names = [n for n in _story_names(w) if len(n) >= 2]
    total, docf = {}, {}
    for p in prev:
        seen = set()
        for wd in _content_words(p.get("body") or ""):
            n = _norm_word(wd)
            if len(n) < 2 or n in _COMMON_WORDS or any(n.startswith(nm) for nm in names):
                continue                          # 인물명+조사(민우는 등)도 함께 제외
            total[n] = total.get(n, 0) + 1
            seen.add(n)
        for n in seen:
            docf[n] = docf.get(n, 0) + 1
    need = max(4, len(prev))                     # 총 4회 이상 & 평균 회당 1회 이상
    cands = [(n, c) for n, c in total.items()
             if c >= need and docf.get(n, 0) >= 2]   # 여러 회차에 걸쳐 반복될 때
    cands.sort(key=lambda x: (-x[1], -len(x[0])))
    return [n for n, _ in cands[:top]]


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
    overused = _overused_expressions(prev)
    overused_block = ("\n━━━ 이미 여러 번 쓴 표현 — 그대로도 비슷하게도 재사용 금지 (새 표현으로 바꿔라) ━━━\n"
                      + "\n".join(f"- {u}" for u in overused) + "\n") if overused else ""
    motifs = _recurring_motifs(prev, w)
    scenes_block = ("\n━━━ 이미 여러 화에서 반복된 장면·행동·연출 — 이번 화에서 '재현' 금지 ━━━\n"
                    "아래 상황을 또 만들지 마라. 인물의 성격·관계는 매번 '다른 사건·다른 행동'으로 드러내라:\n"
                    + "\n".join(f"- {a} … {b}" for a, b in motifs) + "\n") if motifs else ""
    words = _overused_words(prev, w)
    words_block = ("\n━━━ 이미 너무 자주 쓴 단어 — 이번 화에서 쓰지 마라 (다른 감각·다른 소재로 바꿔라) ━━━\n"
                   "특정 냄새·색·맛·사물에 계속 기대지 마라. 아래 단어는 이번 화에서 거의/전혀 쓰지 말고 새로운 표현을 찾아라:\n"
                   + ", ".join(words) + "\n") if words else ""

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
{overused_block}{scenes_block}{words_block}
{f'[작가의 지시 — 최우선으로 따르라] {directive}' if directive else ''}

집필 규칙:
- **먼저 위 '지금까지 연재된 내용'을 처음부터 끝까지 다시 읽고 시작하라.** 그 위에 이어 쓰는 것이다.
- **앞 회차 절대 준수**: 위에 이미 쓰인 내용과 모순되면 안 된다.
  · 이미 일어난 사건을 다시 처음 일어난 것처럼 쓰지 마라 (예: 이미 치른 재회·고백·죽음·각성·승부의 결말).
  · 능력치·수치(포인트, 금액, 시청자 수, 날짜 등)는 앞 회차의 마지막 값에서 이어가라.
  · 인물의 말투·성격·호칭은 앞 회차에서 확립된 그대로 유지하라.
  · 앞에서 밝혀진 비밀·정보를 인물이 다시 모르는 상태로 되돌리지 마라.
- **장면·연출 반복 절대 금지 (가장 중요)**: 앞 회차에서 이미 나온 '상황·행동·연출'을 다시 재현하지 마라.
  단어만 바꿔 같은 장면을 되풀이하는 것도 금지다. 특히 다음을 매 회차 반복하지 마라 —
  · 인물의 관계를 늘 같은 동작으로 표현하기(손을 잡고 힘주기, 안기, 구원·고백 대사의 재확인),
  · 특정 인물이 매번 같은 방식으로 등장·개입하기(예: 같은 장치·화면·전조로 나타나기),
  · 이미 확인한 감정을 다시 확인하는 데 그치는 장면, 같은 대화의 재탕.
  · 위 '반복된 장면·행동·연출' 목록의 상황은 이번 화에서 절대 재현하지 마라.
  인물의 성격·관계는 '새로운 사건·새로운 행동·새로운 장소'를 통해 다르게 드러내라.
- **표현 중복 금지**: 앞 회차에서 쓴 묘사·비유·문장·대사를 그대로도 비슷하게도 다시 쓰지 마라.
  감정 상투구('심장이 쿵 내려앉았다', '눈이 크게 흔들렸다'), 외양·표정·배경 묘사, 장면 전환 문구를 반복하지 말고,
  위 '이미 여러 번 쓴 표현' 목록은 무슨 일이 있어도 재사용하지 마라.
- **단어 반복 금지**: 특정 냄새·색·맛·사물 단어(예: 나무 이름·'피맛'·'보랏빛' 같은 것)를 회차마다 반복해 인장처럼 쓰지 마라.
  같은 인물·장소·분위기라도 매번 '다른 감각(청각·촉각·후각 등)과 다른 소재'로 묘사하라.
  위 '이미 너무 자주 쓴 단어' 목록은 이번 화에서 거의/전혀 쓰지 마라.
- **분량: 공백 포함 {target:,}자 이상 ({target:,}~{int(target * 1.2):,}자).** 여러 장면으로 구성하라.
{DESCRIPTION_RULES}
- **심경 변화**는 반드시 이번 화의 사건이 원인이어야 하고, 몸짓과 대사로 단계적으로 보여라.
- **시간 일관성**: 앞 화가 끝난 시점 이후에서 시작하고, 낮/밤·이동시간·계절이 맞아야 한다.
- 역사물이면 인명·연호·관직·물건의 고증을 지켜라.
- 이번 화는 지정된 전개를 수행하되, **앞 회차와 뚜렷이 다른 새로운 사건·정보·장소·관계 변화**를 담아
  이야기를 실제로 전진시켜라. 같은 감정 상태를 다시 확인하는 데 그치지 마라.
- 대화 비중 높게, 문단은 짧게.
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

    # ── 반복 감시 (장면 + 단어) ──
    # 이번 화가 '이미 반복된 장면'이나 '이미 과하게 쓴 단어'를 또 되풀이하면, 그것들을 지목해
    # 새로운 사건·다른 표현으로 대체하도록 딱 한 번 다시 쓰게 한다 (반복이 실제로 준 경우에만 채택).
    if not llm.is_mock:
        motifs = _recurring_motifs(prev, w)
        banned = _overused_words(prev, w)

        def _rep(t):
            wc = _word_counts(t)
            scene = [m for m in motifs if m in _chapter_bigrams(t)]
            word = [b for b in banned if wc.get(b, 0) >= 3]      # 이미 과한 단어를 또 3회+ 사용
            return scene, word

        scene_hit, word_hit = _rep(text)
        if len(scene_hit) >= 6 or len(word_hit) >= 2:
            parts = []
            if len(scene_hit) >= 6:
                parts.append("장면·행동: " + ", ".join(f"'{a} {b}'" for a, b in scene_hit[:8])
                             + " — 이 상황들을 삭제하고 완전히 다른 새로운 사건으로 대체하라")
            if word_hit:
                parts.append("반복 단어: " + ", ".join(word_hit[:10])
                             + " — 이 단어들을 이번 화에서 거의/전혀 쓰지 말고 다른 감각·소재로 바꿔라")
            redir = ("[반드시 지켜라] 앞 회차와 똑같은 반복이 또 나왔다. " + " / ".join(parts)
                     + ". 이번 화를 그렇게 다시 써라. " + (directive or "")).strip()
            raw2 = llm.write(_chapter_prompt(w, no, beat, prev, redir, later),
                             mock_text="", max_tokens=16000)
            if not llm.last_error and raw2.strip():
                t2, x2, s2 = _parse_chapter(raw2, no)
                s2_scene, s2_word = _rep(x2)
                if x2.strip() and len(x2) >= min_chars and \
                   (len(s2_scene) + len(s2_word)) < (len(scene_hit) + len(word_hit)):
                    title, text = t2 or title, x2      # 반복이 실제로 줄었을 때만 교체
                    summary = s2 or summary
    return title, text, summary, None


class BlankChapterBody(BaseModel):
    no: int = 0


@router.post("/works/{work_id}/chapters/blank")
def open_blank_chapter(work_id: int, body: BlankChapterBody,
                       user: str = Header(default="solo", alias="X-User-Id")):
    """작가가 '직접 쓸' 빈 회차를 연다 — AI를 안 쓰고, 펜도 안 쓰고, 등급 제한도 없다.
    이 앱의 핵심 기능이라 무료도 쓸 수 있다. 이미 있는 회차면 그걸 그대로 돌려준다."""
    with db.connect() as c:
        w = _load_work(c, work_id, user)
        if not w:
            return {"ok": False, "error": "작품을 찾을 수 없어요."}
        no = int(body.no or 0)
        if no <= 0:                                   # 번호를 안 주면 다음 빈 회차
            used = {r["no"] for r in c.execute(
                "SELECT no FROM chapters WHERE work_id=?", (work_id,)).fetchall()}
            no = next((n for n in range(1, (w["total_chapters"] or 0) + 1) if n not in used), 0)
            if not no:
                return {"ok": False, "error": "예정된 회차를 모두 열었어요. 총 회차 수를 늘려 주세요."}
        if no > (w["total_chapters"] or 0):
            return {"ok": False, "error": "총 회차 수를 넘는 회차예요. 총 회차 수를 먼저 늘려 주세요."}
        row = c.execute("SELECT id FROM chapters WHERE work_id=? AND no=?",
                        (work_id, no)).fetchone()
        if row:
            return {"ok": True, "id": row["id"], "no": no, "created": False}
        plan = next((o for o in (w.get("outline") or []) if int(o.get("no", 0)) == no), None)
        title = str((plan or {}).get("title", "")).strip() or f"{no}화"
        ch_id = c.insert_id(
            "INSERT INTO chapters (work_id, no, title, body, summary, state_json, directive, "
            "beat_idx, created_at, updated_at) VALUES (?,?,?,'','','','',?,datetime('now'),datetime('now'))",
            (work_id, no, title, beat_for(no, w["total_chapters"])),
        )
        return {"ok": True, "id": ch_id, "no": no, "created": True}


@router.post("/works/{work_id}/chapters")
def write_chapter(work_id: int, body: ChapterBody,
                  user: str = Header(default="solo", alias="X-User-Id")):
    with db.connect() as c:
        ok, consume, err = _body_gate(c, user)
        if not ok:
            return err
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
        if consume:
            _pen_spend(c, user, 1)
        return {"ok": True, "id": ch_id, "no": no, "chars": len(text),
                "pens": _pen_balance(c, user)}


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
    with db.connect() as c:
        ok, consume, gerr = _body_gate(c, user)   # 다시 쓰기도 본문 생성 → 프로+펜
        if not ok:
            return gerr
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
        # 덮어쓰기 전에 이전 본문을 휴지통에 보관한다 — 다시 쓰기도 언제든 되돌릴 수 있게.
        old_row = c.execute(
            "SELECT title, body, summary, state_json, directive FROM chapters WHERE id=?",
            (chapter_id,)).fetchone()
        undo = _stash(c, "chapter_prev", user,
                      {"chapter_id": chapter_id, "prev": dict(old_row) if old_row else {}})
        c.execute("UPDATE chapters SET title=?, body=?, summary=?, state_json=?, directive=?, "
                  "updated_at=datetime('now') WHERE id=?",
                  (title, text, summary, "", body.directive.strip(), chapter_id))
        if consume:
            _pen_spend(c, user, 1)
        pens = _pen_balance(c, user)
    return {"ok": True, "undo": undo, "pens": pens}


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
        if data["kind"] == "chapter_prev":
            # '다시 쓰기'로 덮어쓴 회차를 이전 본문으로 되돌린다 (같은 회차 제자리 복원).
            cid = data.get("chapter_id")
            own = c.execute(
                "SELECT ch.work_id FROM chapters ch JOIN works w ON w.id = ch.work_id "
                "WHERE ch.id=? AND w.user_id=?", (cid, user)).fetchone()
            if not own:
                return {"ok": False, "error": "되돌릴 회차가 사라졌어요."}
            p = data.get("prev") or {}
            c.execute("UPDATE chapters SET title=?, body=?, summary=?, state_json=?, directive=?, "
                      "updated_at=datetime('now') WHERE id=?",
                      (p.get("title", ""), p.get("body", ""), p.get("summary", ""),
                       p.get("state_json", ""), p.get("directive", ""), cid))
            out = {"ok": True, "kind": "chapter_prev", "work_id": own["work_id"]}
        elif data["kind"] == "chapter":
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
