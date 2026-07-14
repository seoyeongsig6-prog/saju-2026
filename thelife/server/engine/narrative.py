"""LLM 서사 레이어 — 결정된 사건·일과를 그 세계의 질감으로 집필한다."""
import random
import sqlite3
from typing import Generator

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

    if slot.get("sleeping"):
        mock = (
            f"{hhmm}. {scenario.get('place','')}의 밤은 고요하다.\n"
            f"{name}은(는) 깊이 잠들어 있다. 숨소리가 낮고 고르다.\n"
            f"낮에 있었던 일이 꿈의 언저리를 스치는지, 잠결에 몸을 뒤척인다.\n"
            f"창밖으로 달빛이 길게 들어와 있다.\n"
        )
    else:
        mock = (
            f"{hhmm}, {scenario.get('place','')}.\n"
            f"{name}은(는) {slot['what']} 중이다.\n"
            f"{friend}: \"오늘은 일이 손에 붙는구먼.\"\n"
            f"{name}: \"그러게 말입니다. 이런 날만 같으면 좋겠습니다.\"\n"
            f"{conflict_note or '별일 없는 하루가 천천히 흘러간다.'}\n"
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

지금 이 순간의 장면을 현재형으로 8~12줄 써라.
- 대화는 "이름: "대사"" 형식의 줄로. 지문은 그냥 문장으로.
- 직업과 시대의 디테일(도구, 냄새, 소리, 물때, 돈 단위)을 살려라.
- 진행 중인 갈등이 있으면 대화에 그 긴장이 배어나게 하되, 해결하지 마라.
- 마지막 줄은 다음이 살짝 궁금해지게 끝내라. 장면 밖 설명은 금지."""
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
[사건] {stage_desc}
{"[결과] 아바타가 스스로의 힘으로 이겨냈다. 극복의 방식에 이 인물다움이 드러나게." if outcome == "good" else ""}
{"[결과] 이번에는 졌다. 잃은 것을 구체적으로. 그러나 이야기가 끝나지 않았음을 암시하라." if outcome == "bad" else ""}

3~5문장. 다음이 궁금하게 끝내라. 설명 없이 소식 본문만."""
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
    avatar: dict, scenario: dict, size: str, luck_line: str, conflict_title: str,
) -> str:
    """개입 번역 — 행운이 세계의 인과로 배달되는 장면 + 아바타의 해석."""
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
[번역된 행운] {luck_line}
[얽힌 갈등] {conflict_title or '없음'}
[크기] {size}

이 행운이 도착하는 장면을 4~6문장으로 써라.
- 가능하면 고정 등장인물이 행운의 운반자가 되게 하라.
- 마지막에는 아바타가 이 행운을 자기 세계의 언어로 해석하는 한 마디
  ("하늘이 돕는구나" 같은)를 넣어라. 아바타는 유저의 존재를 절대 모른다."""
    return llm.write(prompt, mock_text=mock)


def biography_text(c: sqlite3.Connection, avatar: dict, scenario: dict, season: dict) -> str:
    """시즌 종료 — 완결된 전기."""
    rows = c.execute(
        "SELECT day, kind, title, body FROM events WHERE season_id=? ORDER BY id",
        (season["id"],),
    ).fetchall()
    log = "\n".join(f"- [{r['day']}] {r['title']}" for r in rows if r["kind"] != "daily")[:4000]

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
