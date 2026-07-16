"""LLM 서사 레이어 — 결정된 사건·일과를 그 세계의 질감으로 집필한다."""
import json
import random
import sqlite3
from typing import Generator, Optional

from ..llm import llm


def _cast_line(scenario: dict) -> str:
    return ", ".join(f"{m['name']}({m['role']}, {m.get('note','')})" for m in scenario.get("cast", []))


def _recent_log(c: sqlite3.Connection, avatar_id: int, n: int = 8) -> str:
    rows = c.execute(
        "SELECT day, title, body FROM events WHERE avatar_id=? ORDER BY id DESC LIMIT ?",
        (avatar_id, n),
    ).fetchall()
    return "\n".join(f"- [{r['day']}] {r['title']}: {(r['body'] or '')[:80]}" for r in reversed(rows))


def scene_stream(
    c: sqlite3.Connection, avatar: dict, scenario: dict, slot: dict,
    conflict_note: str, hhmm: str, day: str,
) -> Generator[str, None, None]:
    """'지금' 화면 — 현재 진행형 라이브 장면 (스트리밍)."""
    name = avatar["name"]
    cast = scenario.get("cast", [])
    friend = random.choice(cast)["name"] if cast else "동료"

    shadow_mock = (
        f"그 시각, 그가 모르는 곳.\n"
        f"{conflict_note.split(':')[0] if conflict_note else '마을 어귀'}의 그림자가 조용히 움직인다.\n"
        f"아직 {name}의 귀에는 닿지 않은 이야기다.\n"
    )
    if slot.get("sleeping"):
        mock = (
            f"{hhmm}. {scenario.get('place','')}의 밤은 고요하다.\n"
            f"{name}은(는) 깊이 잠들어 있다. 숨소리가 낮고 고르다.\n"
            f"낮에 있었던 일이 꿈의 언저리를 스치는지, 잠결에 몸을 뒤척인다.\n"
            f"───\n{shadow_mock}"
        )
    else:
        mock = (
            f"{hhmm}, {scenario.get('place','')}.\n"
            f"{name}은(는) {slot['what']} 중이다.\n"
            f"{friend}: \"오늘은 일이 손에 붙는구먼.\"\n"
            f"{name}: \"그러게 말입니다. 이런 날만 같으면 좋겠습니다.\"\n"
            f"───\n{shadow_mock}"
        )

    prompt = f"""당신은 관전형 인생 게임의 서사 작가다. 유저는 아바타의 삶을 몰래 지켜본다.
아바타는 유저의 존재를 모른다. 절대 유저에게 말을 걸지 않는다.

[세계] {scenario.get('era','')} / {scenario.get('place','')}
[아바타] {avatar['name']} — {scenario.get('persona','')}
[고정 등장인물] {_cast_line(scenario)}
[문체] {scenario.get('style','담백한 한국어')}
[최근 있었던 일]
{_recent_log(c, avatar['id'])}
[지금] {day} {hhmm}, 일과: {slot['what']}
[진행 중인 갈등] {conflict_note or '없음'}

두 개의 장면을 병렬로 써라 — 서스펜스는 관객만 아는 데서 나온다.
분량은 넉넉하게 — 유저가 '한 편을 봤다'고 느껴야 한다.

[1부 — 주인공] 지금 이 순간의 장면을 현재형으로 12~16줄.
- 대화는 "이름: "대사"" 형식의 줄로. 지문은 그냥 문장으로.
- 직업과 시대의 디테일(도구, 냄새, 소리, 물때, 돈 단위)을 살려라.
- 진행 중인 갈등의 긴장이 배어나되, 주인공은 아직 전모를 모른다.

그 다음 줄에 정확히 "───" 만 쓴 뒤,

[2부 — 같은 시각, 그가 모르는 곳] 4~6줄.
- 진행 중인 갈등이 있으면: 그를 위협하는 쪽의 움직임을 보여줘라
  (음모가 한 걸음 진행되고, 문서가 준비되고, 배가 떠나고). 관객은 보지만
  주인공은 모른다.
- 갈등이 없으면: 주변 세계의 미묘한 조짐이나 인물들의 수군거림.
- 최근 사건 및 1부와 인물의 위치·동선이 모순되면 안 된다.

공통 규칙: 달력 날짜(년·월·일) 언급 금지. 시간 감각은 'N일차'와 시각뿐.
마지막 줄은 불길하거나 궁금하게. 장면 밖 설명 금지."""
    yield from llm.stream(prompt, mock_text=mock)


def beat_text(
    c: sqlite3.Connection, avatar: dict, scenario: dict,
    stage: str, card: dict, outcome: str = "",
) -> str:
    """사건 비트 — 갈등 전개 단계 하나를 소식 형태로 집필."""
    stage_desc = {
        "seed": card.get("seed", ""),
        "rise": card.get("rise", ""),
        "climax": card.get("climax", ""),
        "good": card.get("resolve_good", ""),
        "bad": card.get("resolve_bad", ""),
    }[outcome or stage]

    mock = f"{stage_desc}. {avatar['name']}의 얼굴에 그늘과 결기가 함께 스친다."
    if outcome == "good":
        mock = f"{stage_desc}. 곁에 있던 이들이 제 일처럼 기뻐한다."
    elif outcome == "bad":
        mock = f"{stage_desc}. 그러나 {avatar['name']}은(는) 오래 주저앉아 있지 않는다."

    prompt = f"""관전형 인생 게임의 소식 한 토막을 써라. 유저가 몰래 엿보는 형식이다
(일기 한 대목, 지인의 전언, 마을 소문, 짧은 목격담 중 어울리는 것).

[세계] {scenario.get('era','')} / {scenario.get('place','')}
[아바타] {avatar['name']} — {scenario.get('persona','')}
[고정 등장인물] {_cast_line(scenario)}
[문체] {scenario.get('style','')}
[최근 있었던 일 — 인물의 위치·동선·상황과 모순되면 안 된다]
{_recent_log(c, avatar['id'])}
[사건] {stage_desc}
{"[결과] 아바타가 스스로의 힘으로 이겨냈다. 극복의 방식에 이 인물다움이 드러나게." if outcome == "good" else ""}
{"[결과] 이번에는 졌다. 잃은 것을 구체적으로. 그러나 이야기가 끝나지 않았음을 암시하라." if outcome == "bad" else ""}

5~8문장으로 넉넉하게. 다음이 궁금하게 끝내라. 현실의 달력 날짜는 언급하지 마라. 설명 없이 소식 본문만."""
    return llm.write(prompt, mock_text=mock)


def episode_text(
    c: sqlite3.Connection, avatar: dict, scenario: dict,
    card: dict, stage: str, outcome: str, headline: str,
) -> str:
    """본편 — 헤드라인 카드를 탭하면 열리는 온전한 한 장면.
    대화와 디테일과 감정이 있는, 드라마 한 신(scene) 분량."""
    stage_desc = card.get(outcome or stage, "")
    cast = scenario.get("cast", [])
    friend = cast[0]["name"] if cast else "동료"
    mock = (
        f"{scenario.get('place','')}.\n"
        f"{avatar['name']}은(는) 소식을 듣고 한동안 말이 없다.\n"
        f"{friend}: \"어떻게 할 셈인가.\"\n"
        f"{avatar['name']}: \"……가 봐야지. 가서 부딪쳐 봐야지.\"\n"
        f"{stage_desc}.\n"
        f"바람이 방향을 바꾸고, 그는 신발끈을 고쳐 맨다.\n"
        f"그 뒷모습이 어딘가 결연하다.\n"
    )
    prompt = f"""관전형 인생 게임의 본편 장면을 써라. 유저가 소식 카드를 눌러 펼친,
그 사건의 온전한 한 장면(드라마 한 신)이다.

[세계] {scenario.get('era','')} / {scenario.get('place','')}
[아바타] {avatar['name']} — {scenario.get('persona','')}
[고정 등장인물] {_cast_line(scenario)}
[문체] {scenario.get('style','')}
[최근 있었던 일 — 위치·동선과 모순 금지]
{_recent_log(c, avatar['id'])}
[이 장면의 사건] {headline}: {stage_desc}
{"[결말] 스스로의 힘으로 이겨낸다 — 그 인물다운 방식으로." if outcome == "good" else ""}
{"[결말] 이번에는 진다 — 무엇을 잃는지 구체적으로. 그러나 끝은 아니다." if outcome == "bad" else ""}

15~25줄로 써라.
- 대화가 절반 이상. "이름: "대사"" 형식의 줄로. 지문은 짧은 문장으로.
- 그 직업·시대의 디테일(도구, 소리, 냄새, 돈 단위)을 살려라.
- 인물들의 성격이 말투에 드러나게. 감정은 설명하지 말고 행동과 대사로.
- 달력 날짜 언급 금지. 마지막 줄은 여운 또는 다음 긴장.
- 장면 밖 해설 금지. 본문만."""
    return llm.write(prompt, mock_text=mock, max_tokens=2000)


def briefing_text(scenario: dict, hhmm: str) -> str:
    """오프닝 브리핑 — 스토리가 시작되는 순간의 해설.
    그 세계의 날짜·시각·날씨·현장 분위기, 그리고 그가 지금 무엇을 하고 있는지."""
    name = scenario.get("name", "")
    mock = (
        f"이야기가 시작된다.\n"
        f"{scenario.get('era','')}. 시각은 {hhmm}.\n"
        f"하늘은 낮게 가라앉아 있고, {scenario.get('place','')}에는 바람이 분다.\n"
        f"당신의 {name}은(는) 지금 이곳에서 하루를 살아가고 있다.\n"
        f"그의 목표 — \"{scenario.get('goal','')}\".\n"
        f"그는 아직 모른다. 이 삶을 처음부터 끝까지 지켜볼 존재가 있다는 것을."
    )
    prompt = f"""관전형 인생 게임의 오프닝 해설을 써라. 유저가 이 삶을 처음 여는 순간,
카메라가 하늘에서 내려오며 세계를 소개하는 내레이션이다.

[세계] {scenario.get('era','')} / {scenario.get('place','')}
[주인공] {name} — {scenario.get('persona','')}
[인생 목표] {scenario.get('goal','')}
[현실의 현재 시각] {hhmm} — 그 세계의 같은 시각으로 동기화하라

8~12문장으로 넉넉하게 써라. 반드시 담을 것:
- 그 세계의 지금 날짜 (역사 세계면 그 시대의 실제 연호/절기로: "정유년 구월 초하루" 식.
  현대면 계절감으로. 현실 세계의 2020년대 연도는 금지)
- 시각({hhmm})과 그 시각의 빛, 날씨, 공기
- 현장의 분위기 — 소리, 냄새, 오가는 사람들
- 당신의 {name}은(는) 어떤 사정으로 지금 여기서 무엇을 하고 있는지
- 마지막 문장: 그는 모른다, 지켜보는 존재가 있다는 것을 — 의 여운
해설체("당신의 {name}은…")로. 본문만."""
    return llm.write(prompt, mock_text=mock, max_tokens=1500)


def diary_text(c: sqlite3.Connection, avatar: dict, scenario: dict, day: str, day_no: int) -> str:
    """하루의 끝 — 아바타가 쓴 1인칭 일기. 감정은 여기서만 말해진다."""
    rows = c.execute(
        "SELECT kind, title, body FROM events WHERE avatar_id=? AND day=? AND kind != 'shadow' "
        "ORDER BY id", (avatar["id"], day),
    ).fetchall()
    day_log = "\n".join(f"- {r['title']}: {(r['body'] or '')[:60]}" for r in rows) or "- 특별한 일 없음"
    mock = (
        f"{day_no}일차.\n오늘도 하루가 갔다. 몸은 고되지만 마음은 이상하게 고요하다. "
        f"목표는 아직 멀고, 길은 험하다. 그래도 내일 아침에는 또 일어나 나갈 것이다. "
        f"그게 내가 아는 유일한 방법이니까."
    )
    prompt = f"""아래 인물이 오늘 하루를 마치고 쓰는 일기를 써라. 1인칭.

[인물] {avatar['name']} — {scenario.get('persona','')}
[세계] {scenario.get('era','')} / {scenario.get('place','')}
[인생 목표] (그의 마음속에 늘 있다)
[오늘 있었던 일]
{day_log}

4~6문장. 규칙:
- 사건의 나열이 아니라 사건에 대한 '마음'을 써라 — 두려움, 오기, 그리움, 작은 기쁨.
- 그 인물의 말투와 시대의 언어로. (이순신이라면 난중일기의 결로)
- 달력 날짜 금지. 첫 줄은 "{day_no}일차." 로 시작.
- 누군가 읽을 것을 모르는, 혼자만의 글이다."""
    return llm.write(prompt, mock_text=mock)


def shadow_text(c: sqlite3.Connection, avatar: dict, scenario: dict, card: dict, stage: str) -> str:
    """주변의 움직임 — 주인공은 모르고, 지켜보는 이만 아는 위협의 진행."""
    stage_desc = card.get(stage, "")
    mock = (
        f"{avatar['name']}이(가) 모르는 곳에서 일이 움직인다. {stage_desc}. "
        f"바람이 먼저 알고 방향을 바꾼다."
    )
    prompt = f"""관전형 인생 게임. 유저에게만 보이는 '그가 모르는 움직임' 한 토막을 써라.
주인공을 위협하는 쪽의 시점이다 — 음모가 진행되고, 서류가 넘어가고, 배가 은밀히 뜬다.

[세계] {scenario.get('era','')} / {scenario.get('place','')}
[주인공] {avatar['name']} — 그는 이 일을 아직 모른다
[고정 등장인물] {_cast_line(scenario)}
[최근 있었던 일 — 위치·동선과 모순 금지]
{_recent_log(c, avatar['id'])}
[진행 중인 갈등의 현재 국면] {card.get('title','')}: {stage_desc}

2~4문장. 주인공은 등장시키지 말고, 위협이 한 걸음 다가오는 것만 보여줘라.
불길한 여운으로 끝내라. 달력 날짜 언급 금지. 본문만."""
    return llm.write(prompt, mock_text=mock)


def daily_text(avatar: dict, scenario: dict, slots: list, rng: random.Random) -> str:
    """갈등 없는 날의 잔잔한 일상 한 줄."""
    slot = rng.choice(slots)
    cast = scenario.get("cast", [])
    friend = rng.choice(cast)["name"] if cast else "동료"
    lines = [
        f"{slot['what']}로 하루가 갔다. {friend}와(과) 나눈 실없는 농담이 오래 남았다.",
        f"{slot['what']} 중에 문득 하늘을 오래 봤다. 목표가 조금 더 가까워진 기분이 들었다.",
        f"평범한 하루. {slot['what']}, 그리고 저녁의 고단함. 그래도 몸은 정직하게 나아간다.",
    ]
    return rng.choice(lines)


def intervention_text(
    c: sqlite3.Connection, avatar: dict, scenario: dict, size: str,
    luck_line: str, conflict_title: str, hhmm: str,
) -> str:
    """개입 번역 — 행운이 세계의 인과로 배달되는 장면 + 아바타의 해석.
    반드시 '지금 이 순간'의 상황·인물 위치와 아귀가 맞아야 한다."""
    mock = (
        f"{luck_line}. 사람들은 우연이라 했다.\n"
        f"{avatar['name']}은(는) 한참 말이 없다가 낮게 중얼거렸다. "
        f"\"……하늘이 돕는구나.\"\n그 하늘이 누구인지, 그는 끝내 모를 것이다."
    )
    prompt = f"""관전형 인생 게임. 유저(정체를 숨긴 행운의 근원)가 아바타에게 행운을 보냈다.
행운은 절대 날것으로 떨어지지 않고, 그 세계의 인과로 번역되어 도착한다.

[세계] {scenario.get('era','')} / {scenario.get('place','')}
[아바타] {avatar['name']} — {scenario.get('persona','')}
[고정 등장인물] {_cast_line(scenario)}
[지금 시각] {hhmm}
[최근 있었던 일 — 지금 누가 어디에 있는지의 근거]
{_recent_log(c, avatar['id'], 10)}
[행운의 형태 (영감일 뿐 — 상황에 맞게 각색하라)] {luck_line}
[얽힌 갈등] {conflict_title or '없음'}
[크기] {size}

이 행운이 '지금' 도착하는 장면을 4~6문장으로 써라.
- **일관성 절대 규칙**: 최근 사건과 모순되면 안 된다. 방금 곁에 있던 인물이
  '멀리서 서찰을 보내는' 식의 모순은 중대한 오류다. 인물의 현재 위치·동선,
  지금 시각(새벽/한낮/밤)에 자연스러운 사건이어야 한다.
- 행운의 형태가 지금 상황과 어긋나면, 같은 크기의 다른 우연으로 바꿔라.
- 가능하면 고정 등장인물이 행운의 운반자가 되게 하라 — 지금 그가 있을 법한
  자리에서.
- 마지막에는 아바타가 이 행운을 자기 세계의 언어로 해석하는 한 마디
  ("하늘이 돕는구나" 같은)를 넣어라. 아바타는 유저의 존재를 절대 모른다."""
    return llm.write(prompt, mock_text=mock)


def generate_conflict(
    c: sqlite3.Connection, avatar: dict, scenario: dict, season: dict,
    scale: str, avoid_titles: list,
) -> Optional[dict]:
    """즉흥 갈등 발제 — 지금 이 삶의 상황에서 새 갈등을 만들어 구조로 반환.
    LLM이 없거나 실패하면 None (갈등 은행으로 폴백)."""
    from . import world  # 순환 참조 방지용 지연 임포트

    if llm.is_mock:
        return None

    schema = {
        "type": "관계|재정|신체|자연|권력|내면 중 하나",
        "title": "짧은 제목",
        "seed": "조짐 — 갈등이 처음 모습을 드러내는 사건",
        "rise": "고조 — 긴장이 커지는 전개",
        "climax": "절정 — 정면으로 부딪히는 순간",
        "resolve_good": "아바타가 스스로의 힘으로 이겨낸 결말",
        "resolve_bad": "이번에는 지고, 무언가를 잃는 결말",
        "luck_hook": "행운(개입)이 닿으면 벌어지는 일",
    }
    prompt = f"""당신은 관전형 인생 게임의 갈등 설계자다. 아래 인물의 삶에 지금 새로 시작될 갈등 하나를 발제하라.

[세계] {scenario.get('era','')} / {scenario.get('place','')}
[아바타] {avatar['name']} — {scenario.get('persona','')}
[인생 목표] {season['goal']}
[고정 등장인물] {_cast_line(scenario)}
[최근 있었던 일]
{_recent_log(c, avatar['id'])}
[이미 다룬 갈등 — 반복 금지] {', '.join(t for t in avoid_titles if t) or '없음'}

규칙:
- 규모는 '{scale}' (소=일상의 파문, 중=며칠짜리 시련, 대=목표를 위협하는 큰 산).
- 실존 인물이면 실제 생애의 갈등을 재료로 삼아도 좋다.
- 시대에 없는 물건·개념 금지. 고정 등장인물을 얽어라.
- 극복의 주체는 아바타다. resolve_good은 그 인물다운 방식이어야 한다.
- 출력은 아래 스키마의 JSON 하나만:
{json.dumps(schema, ensure_ascii=False, indent=1)}"""
    raw = llm.write(prompt, mock_text="", max_tokens=1200)
    card = world.parse_llm_json(raw)
    if not card:
        return None
    for key in ("title", "seed", "rise", "climax", "resolve_good", "resolve_bad"):
        if not card.get(key):
            return None
    card["id"] = f"dyn_{avatar['id']}_{random.randrange(10**8)}"
    card["scale"] = scale
    card["min_act"] = 1
    card["scenario"] = "dynamic"
    return card


def biography_text(c: sqlite3.Connection, avatar: dict, scenario: dict, season: dict) -> str:
    """시즌 종료 — 완결된 전기."""
    import datetime as _dt

    def _rel(day: str) -> str:
        try:
            n = (_dt.date.fromisoformat(day) - _dt.date.fromisoformat(season["started_day"])).days + 1
            return f"{max(1, n)}일차"
        except Exception:
            return "어느 날"

    rows = c.execute(
        "SELECT day, kind, title, body FROM events WHERE season_id=? ORDER BY id",
        (season["id"],),
    ).fetchall()
    log = "\n".join(f"- [{_rel(r['day'])}] {r['title']}" for r in rows if r["kind"] != "daily")[:4000]

    mock = (
        f"『{avatar['name']} — {season['goal']}』\n\n"
        f"{scenario.get('era','')}의 {avatar['name']}은(는) 마침내 목표에 닿았다. "
        f"길은 곧지 않았다. 지기도 했고, 잃기도 했다. 그러나 그는 매번 제 힘으로 일어섰고, "
        f"때로는 설명할 수 없는 행운이 그의 곁을 스쳤다.\n\n"
        f"이것은 그 여정의 기록이다.\n{log}\n\n"
        f"그리고 이 삶을 처음부터 끝까지 지켜본 존재가 있었다는 것을, 그는 끝내 알지 못했다."
    )
    prompt = f"""아래 사건 기록을 바탕으로, 목표를 이룬 한 인물의 짧은 전기를 써라.

[인물] {avatar['name']} — {scenario.get('persona','')}
[세계] {scenario.get('era','')} / {scenario.get('place','')}
[목표] {season['goal']}
[사건 기록]
{log}

12~20문장. 3막 구조(시작-시련-성취)로. 패배와 상실도 숨기지 말고,
스스로의 힘으로 일어선 순간들을 중심에 둬라. 마지막 문장은
'이 삶을 지켜본 이름 없는 존재'에 대한 여운으로 끝내라."""
    return llm.write(prompt, mock_text=mock)
