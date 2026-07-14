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


def build_custom_scenario(form: dict) -> dict:
    """커스텀 아바타의 세계 텍스처 팩을 생성한다 (LLM 1회, 목업 폴백)."""
    name = form["name"]
    occupation = form.get("occupation", "자유인")
    era = form.get("era", "현대 한국")
    goal = form["goal"]
    persona = form.get("persona", "성실하고 다정하다")
    age = form.get("age", "30")

    mock = {
        "id": "custom",
        "type": "현실",
        "name": name,
        "era": era,
        "place": f"{era}의 어느 마을",
        "goal": goal,
        "persona": f"{age}세. {persona}",
        "style": "담백하고 따뜻한 한국어. 직업의 디테일을 살린다.",
        "money_unit": "원" if "현대" in era else "냥",
        "cast": [
            {"name": "박씨", "role": f"오랜 동료 {occupation}", "affinity": 70, "note": "무뚝뚝하지만 정이 깊다"},
            {"name": "순임", "role": "단골 상인", "affinity": 60, "note": "소문에 밝다"},
            {"name": "장씨", "role": "마을 어른", "affinity": 55, "note": "잔소리가 많지만 지혜롭다"},
        ],
        "milestones": [
            f"{occupation}으로서 기반을 다진다",
            "뜻밖의 시련을 이겨낸다",
            "결정적인 기회를 붙잡는다",
            goal,
        ],
        "schedule": [
            {"t": "06:00", "what": "기상, 하루 준비"},
            {"t": "08:00", "what": f"{occupation} 일을 시작한다"},
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
    }
    if llm.is_mock:
        return mock

    prompt = f"""당신은 관전형 인생 게임의 세계 설계자다. 아래 인물의 세계 텍스처 팩을 JSON으로 만들어라.
인물: 이름 {name}, 나이 {age}, 직업 {occupation}, 시대 {era}, 성격 {persona}, 인생 목표 "{goal}"

JSON 스키마 (다른 텍스트 없이 JSON만 출력):
{json.dumps(mock, ensure_ascii=False, indent=1)}

요구사항:
- cast는 그 직업·시대에 실재할 법한 고정 인물 3명 (이름, 역할, note).
- milestones는 목표까지의 단계 4개. 마지막은 목표 그 자체.
- schedule은 그 직업의 현실적인 하루 6~8개 슬롯.
- luck_dict는 그 세계에서 행운이 나타나는 그럴듯한 형태 (소/중/대 각 2개).
- style은 서사 문체 지침 한 줄."""
    raw = llm.write(prompt, mock_text=json.dumps(mock, ensure_ascii=False))
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        pack = json.loads(raw)
        pack["id"] = "custom"
        pack["type"] = "현실"
        pack["name"] = name
        pack["goal"] = goal
        return pack
    except Exception:
        return mock
