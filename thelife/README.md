# The Life — 프로토타입 (Phase 0)

> 가장 너답게, 가장 특별한 삶을 경험하라

관전형 AI 인생 게임. 아바타가 스스로 살아가고, 유저는 지켜본다 —
시즌에 딱 세 번의 행운을 빼고는. 기획서: `../docs/THE-LIFE-DEV-PLAN.md`

## 실행

```bash
cd thelife
pip install -r requirements.txt

# 실제 LLM 사용 (없으면 목업 텍스트로 동작)
export GEMINI_API_KEY=...

uvicorn server.main:app --port 8000
# 브라우저(모바일 권장)에서 http://localhost:8000
```

`GEMINI_API_KEY`가 없으면 **목업 모드**로 동작한다 — 서사가 템플릿
문장으로 나오지만 일과표·갈등 엔진·행운 게이지·시즌 루프 전체를
그대로 체험/검증할 수 있다.

## 구조

```
server/
  main.py                 API + 정적 서빙
  db.py                   SQLite (아바타·시즌·사건·게이지)
  llm.py                  LLM 레이어 (Gemini / 목업 폴백)
  engine/
    world.py              시나리오 팩 로딩, 커스텀 세계 생성, 생존 유명인 차단
    schedule.py           일과표 — 언제 들어가도 '지금'이 있다
    conflicts.py          갈등 엔진 — 씨앗→고조→절정→해소, 패배 모델 C
    narrative.py          서사 집필 (장면·비트·개입 번역·전기)
    intervention.py       개입 — 시즌 3회, 행운 게이지, 세계-인과 번역
    season.py             따라잡기 시뮬레이션, 시즌 완결
data/
  scenarios/*.yaml        세계 텍스처 팩 (이순신·어부·빵집)
  conflicts/*.yaml        갈등 은행 (파일 기반 → 추후 DB 이관)
web/                      카톡형 모바일 웹 (지금 / 그동안 / 이야기)
```

## 핵심 규칙 (기획서 요약)

- 유저는 조작할 수 없다. 아바타는 유저의 존재를 모른다.
- 아바타는 스스로의 힘으로 난관을 극복한다. 전투는 질 수 있지만
  시즌 목표는 결국 이루어진다.
- 개입은 시즌당 3회. 돈으로 횟수를 살 수 없고 크기만 살 수 있다.
- 행운은 날것으로 떨어지지 않는다 — 그 세계의 인과로 번역되어 배달된다.

## 테스트 도구

- 우하단 `+1일`, `+7일`: 가상 시계 빨리감기 (며칠치 삶이 시뮬레이션된다)
- `↺`: 아바타 리셋
- 광고/충전 버튼은 목업 (실제 SDK 연동은 Phase 1)
