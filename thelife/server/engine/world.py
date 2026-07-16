"""세계 텍스처 — 시나리오 팩 로딩, 커스텀 아바타의 세계 생성, 생존 유명인 차단."""
import json
from pathlib import Path

import yaml

from ..llm import llm

DATA = Path(__file__).resolve().parent.parent.parent / "data"

BLOCK_MESSAGE = (
    "그의 삶은 아직 진행 중입니다.\n"
    "지금 이 순간에도 현실에서 살아가고 있는 사람의 삶은 "
    "The Life가 대신 지어낼 수 없어요.\n"
    "그의 이야기가 완결되면, 언젠가 이곳에서 만날 수 있을 거예요."
)

# 프로토타입용 최소 목록. 실서비스에서는 LLM 판별 + 운영 목록으로 확장.
LIVING_FAMOUS = {
    "손흥민", "유재석", "아이유", "김연아", "페이커", "이재용", "봉준호",
    "일론 머스크", "팀 쿡", "빌 게이츠", "테일러 스위프트", "손정의", "방시혁",
}


def load_scenarios() -> dict:
    packs = {}
    for f in sorted((DATA / "scenarios").glob("*.yaml")):
        pack = yaml.safe_load(f.read_text(encoding="utf-8"))
        packs[pack["id"]] = pack
    return packs


def load_conflict_cards() -> dict:
    cards = {}
    for f in sorted((DATA / "conflicts").glob("*.yaml")):
        for card in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            cards[card["id"]] = card
    return cards


def cards_for(scenario: dict, cards: dict) -> list:
    """전용 카드 + (현실 시나리오에만) 공용 카드. 역사 세계에 현대 카드가 새지 않게."""
    out = []
    allow_common = scenario.get("type") == "현실"
    for card in cards.values():
        scope = card.get("scenario", "common")
        if scope == scenario["id"] or (scope == "common" and allow_common):
            out.append(card)
    return out


def is_living_famous(name: str) -> bool:
    name = name.strip()
    if name in LIVING_FAMOUS:
        return True
    if llm.is_mock:
        return False
    answer = llm.write(
        f"'{name}'은(는) 현재 생존해 있는 실존 유명인(연예인, 운동선수, 기업인, 정치인 등)인가? "
        f"확실히 그렇다면 YES, 아니면 NO 한 단어로만 답하라.",
        mock_text="NO",
    )
    return answer.strip().upper().startswith("YES")


def scenario_card_index(scenario: dict, global_cards: dict) -> tuple:
    """이 시나리오에서 쓸 수 있는 갈등 카드 목록 + id 색인.
    아바타 생성 시 즉석 생성된 카드(scenario['cards'])도 은행에 합류한다."""
    cards = cards_for(scenario, global_cards)
    embedded = scenario.get("cards") or []
    by_id = dict(global_cards)
    for c in embedded:
        by_id[c["id"]] = c
    return cards + embedded, by_id


def build_scenario(form: dict) -> dict:
    """자유 입력으로 세계 텍스처 팩을 생성한다 (LLM 1회, 목업 폴백).

    이름만 필수. 실존 인물이면 실제 생애를 바탕으로, 아니면 입력된
    정보(나이·직업·시대·성격)로 세계를 짓는다. 목표는 유저가 자유롭게
    쓰되, 비우면 그 인물에게 가장 어울리는 목표를 정한다.
    갈등 카드 5장도 이 인물 전용으로 함께 생성된다."""
    name = form["name"].strip()
    age = (form.get("age") or "").strip()
    occupation = (form.get("occupation") or "").strip()
    era = (form.get("era") or "").strip()
    persona = (form.get("persona") or "").strip()
    goal = (form.get("goal") or "").strip()

    mock_goal = goal or f"{name}다운 삶을 완성한다"
    mock_occ = occupation or "자유인"
    mock_era = era or "현대 한국"
    mock = {
        "id": "custom",
        "type": "현실",
        "name": name,
        "era": mock_era,
        "place": f"{mock_era}의 어느 마을",
        "goal": mock_goal,
        "persona": f"{age or '30'}세. {persona or '성실하고 다정하다'}",
        "style": "담백하고 따뜻한 한국어. 직업의 디테일을 살린다.",
        "money_unit": "원" if "현대" in mock_era else "냥",
        "cast": [
            {"name": "박씨", "role": f"오랜 동료 {mock_occ}", "affinity": 70, "note": "무뚝뚝하지만 정이 깊다"},
            {"name": "순임", "role": "단골 상인", "affinity": 60, "note": "소문에 밝다"},
            {"name": "장씨", "role": "마을 어른", "affinity": 55, "note": "잔소리가 많지만 지혜롭다"},
        ],
        "milestones": [
            "기반을 다진다", "뜻밖의 시련을 이겨낸다", "결정적인 기회를 붙잡는다", mock_goal,
        ],
        "schedule": [
            {"t": "06:00", "what": "기상, 하루 준비"},
            {"t": "08:00", "what": f"{mock_occ} 일을 시작한다"},
            {"t": "12:00", "what": "점심, 동료들과 한담"},
            {"t": "14:00", "what": "오후 일"},
            {"t": "19:00", "what": "저녁, 하루를 정리"},
            {"t": "22:00", "what": "잠자리에 든다"},
        ],
        "luck_dict": {
            "소": ["잊고 있던 곗돈 순번이 돌아온다", "옛 친구가 작은 빚을 갚으러 온다"],
            "중": ["뜻밖의 큰 주문이 들어온다", "은인이 나서서 보증을 서준다"],
            "대": ["오래 막혔던 큰 계약이 성사된다", "잃어버린 줄 알았던 목돈이 돌아온다"],
        },
        "cards": [],
    }
    if llm.is_mock:
        return mock

    card_schema = {
        "id": "gen_1", "type": "관계|재정|신체|자연|권력|내면", "scale": "소|중|대",
        "min_act": 1, "title": "제목", "seed": "조짐", "rise": "고조", "climax": "절정",
        "resolve_good": "스스로의 힘으로 이겨낸 결말", "resolve_bad": "잃은 것이 생기는 결말",
        "luck_hook": "행운이 닿으면 벌어지는 일",
    }
    known = []
    if age: known.append(f"나이 {age}")
    if occupation: known.append(f"직업 {occupation}")
    if era: known.append(f"시대/배경 {era}")
    if persona: known.append(f"성격 {persona}")

    prompt = f"""당신은 관전형 인생 게임의 세계 설계자다. 아래 인물이 살아갈 세계 텍스처 팩을 JSON으로 만들어라.

인물 이름: {name}
알려진 정보: {', '.join(known) if known else '없음 — 이름에서 추론하라'}
인생 목표: {('"' + goal + '"') if goal else '유저가 정하지 않았다 — 이 인물에게 가장 어울리는 목표를 하나 정하라'}

중요한 판단:
- 이 이름이 실존했던 역사적 인물(예: 이순신, 세종, 나폴레옹, 스티브 잡스 등 고인)이라면
  type을 "역사"로 하고, 실제 생애 — 그 시대, 실제 주변 인물, 실제 겪은 갈등 — 를
  바탕으로 세계를 지어라. 목표가 비어 있으면 그 인물 생애의 실제 목표를 쓰라.
- 그렇지 않으면 type을 "현실"로 하고, 주어진 정보로 실감나는 세계를 지어라.

JSON 스키마 (다른 텍스트 없이 JSON만 출력):
{json.dumps({k: v for k, v in mock.items() if k != 'cards'}, ensure_ascii=False, indent=1)}
여기에 더해 "cards" 필드: 이 인물 전용 갈등 카드 5장의 배열. 각 카드 스키마:
{json.dumps(card_schema, ensure_ascii=False)}

요구사항:
- cast는 그 세계에 실재할 법한(역사 인물이면 실제 인물) 고정 인물 3~4명.
- milestones는 목표까지의 단계 4개. 마지막은 목표 그 자체.
- schedule은 그 인물의 현실적인 하루 6~8개 슬롯 (t는 "HH:MM").
- luck_dict는 그 세계에서 행운이 나타나는 그럴듯한 형태 (소/중/대 각 2~3개).
- cards의 scale 분포는 소2/중2/대1 정도. min_act: 대형 카드는 2~3.
- 갈등은 실존 인물이면 실제 생애의 갈등을 우선 재료로 삼아라."""
    raw = llm.write(prompt, mock_text=json.dumps(mock, ensure_ascii=False), max_tokens=3500)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        pack = json.loads(raw)
        pack["id"] = "custom"
        pack["name"] = name
        if goal:
            pack["goal"] = goal
        if pack.get("type") not in ("역사", "현실"):
            pack["type"] = "현실"
        cards = []
        for i, c in enumerate(pack.get("cards") or []):
            if not isinstance(c, dict) or not c.get("title"):
                continue
            c["id"] = f"gen_{i+1}"
            c["scenario"] = "custom"
            c["scale"] = c.get("scale") if c.get("scale") in ("소", "중", "대") else "중"
            try:
                c["min_act"] = max(1, min(3, int(c.get("min_act", 1))))
            except Exception:
                c["min_act"] = 1
            cards.append(c)
        pack["cards"] = cards
        for key in ("era", "place", "persona", "style", "milestones", "schedule", "luck_dict", "cast", "goal"):
            if not pack.get(key):
                pack[key] = mock[key]
        return pack
    except Exception:
        return mock
