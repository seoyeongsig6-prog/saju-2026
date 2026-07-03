import streamlit as st
import google.generativeai as genai
import datetime
import json
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ============================================================
# 1. 기본 설정
# ============================================================
def get_secret(key, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


model = None
_gemini_key = get_secret("GEMINI_API_KEY")
if _gemini_key:
    try:
        genai.configure(api_key=_gemini_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception:
        model = None

st.set_page_config(page_title="AI 조직 세부진단 키트 (Pro)", layout="centered")

hide_st_style = """
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stAppDeployButton {display:none;}
    #stDecoration {display:none;}
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# ============================================================
# 2. 문항 데이터 모델
# ============================================================
# 5점 척도 공통 옵션 (긍정형 진술 / 부정형 진술)
LIKERT_POS = (
    ["전혀 그렇지 않다", "그렇지 않다", "보통이다", "그렇다", "매우 그렇다"],
    [0, 1, 2, 3, 4],
)
LIKERT_NEG = (
    ["매우 그렇다", "그렇다", "보통이다", "그렇지 않다", "전혀 그렇지 않다"],
    [0, 1, 2, 3, 4],
)

CATEGORIES = {
    "adoption": "① AI 도입현황",
    "depth": "② 업무 활용 깊이",
    "ops": "③ 운영체계",
    "governance": "④ 거버넌스·리스크정책",
    "people": "⑤ 인력·교육",
    "culture": "⑥ 조직문화·변화저항",
    "performance": "⑦ 성과·ROI",
    "risk": "⑧ 리스크 노출·대응",
}

SECTIONS = [
    {
        "key": "basic",
        "title": "0. 기업 기본정보",
        "scored": False,
        "questions": [
            {"id": "company_name", "type": "text", "label": "회사명 (또는 조직명)"},
            {"id": "respondent_role", "type": "select", "label": "응답자 직책",
             "options": ["대표/CEO", "임원(C-level)", "부서장/팀장", "실무자", "HR 담당자", "기타"]},
            {"id": "respondent_dept", "type": "select", "label": "응답자 소속 부서",
             "options": ["경영지원/HR", "IT/개발", "마케팅/영업", "기획/전략", "생산/운영", "연구개발(R&D)", "고객서비스", "기타"]},
            {"id": "industry", "type": "select", "label": "업종(대분류)",
             "options": ["제조업", "IT/소프트웨어", "금융/보험", "유통/커머스", "서비스업", "건설/부동산", "의료/제약", "교육", "공공/비영리", "미디어/콘텐츠", "기타"]},
            {"id": "org_type", "type": "select", "label": "조직 유형",
             "options": ["스타트업(초기)", "스타트업(성장기)", "중소기업", "중견기업", "대기업", "공공기관", "비영리단체"]},
            {"id": "employee_count", "type": "select", "label": "임직원 수",
             "options": ["10인 미만", "10~49인", "50~99인", "100~299인", "300~999인", "1000인 이상"]},
            {"id": "founded_years", "type": "select", "label": "설립 연차",
             "options": ["3년 미만", "3~7년", "8~15년", "16~30년", "30년 이상"]},
            {"id": "biz_model", "type": "multiselect", "label": "사업 형태 (복수 선택)",
             "options": ["B2B", "B2C", "B2G", "내부(사내) 서비스"]},
            {"id": "annual_revenue", "type": "select", "label": "연매출 구간",
             "options": ["10억 미만", "10~50억", "50~100억", "100~500억", "500~1000억", "1000억 이상", "비공개"]},
            {"id": "hq_region", "type": "select", "label": "본사 소재지",
             "options": ["수도권", "충청권", "영남권", "호남권", "강원/제주", "해외"]},
        ],
    },
    {
        "key": "adoption",
        "title": "1. AI 도입 현황",
        "scored": True,
        "questions": [
            {"id": "adoption_status", "type": "radio", "label": "전사 AI 도입 여부",
             "options": ["전혀 도입 안 함", "검토/논의 중", "일부 부서 파일럿 중", "여러 부서 도입 완료", "전사 표준 도구로 정착"],
             "scores": [0, 1, 2, 3, 4], "weight": 3},
            {"id": "adoption_period", "type": "radio", "label": "도입 기간",
             "options": ["미도입", "6개월 미만", "6개월~1년", "1~2년", "2년 이상"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "adoption_trigger", "type": "multiselect", "label": "최초 도입 계기 (복수 선택)",
             "options": ["경영진 지시", "현업 부서 자발적 도입", "경쟁사 대응", "고객/시장 요구", "비용절감 목적", "신사업 기회 포착", "기타"]},
            {"id": "leading_dept", "type": "select", "label": "도입을 주도한 부서",
             "options": ["IT/전산", "경영기획", "HR", "현업부서 개별", "전담 TF/CoE", "외부 컨설팅사", "없음"]},
            {"id": "tools_used", "type": "multiselect", "label": "현재 사용 중인 AI 도구 (복수 선택)",
             "options": ["ChatGPT(OpenAI)", "Microsoft Copilot", "Claude(Anthropic)", "Google Gemini",
                         "네이버 클로바X", "자체 구축 sLLM", "Midjourney 등 이미지생성", "GitHub Copilot 등 코드생성", "기타"]},
            {"id": "tool_payment", "type": "radio", "label": "도구 결제 형태",
             "options": ["전부 무료 버전만 사용", "일부만 유료", "대부분 유료 라이선스", "엔터프라이즈 계약 체결"],
             "scores": [0, 1, 2, 3]},
            {"id": "adoption_scope", "type": "radio", "label": "도입 범위",
             "options": ["미도입", "특정 개인 수준", "특정 부서/팀 단위", "여러 부서 확산", "전사 표준화"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "budget_dedicated", "type": "radio", "label": "AI 관련 전담 예산 편성 여부",
             "options": ["없음", "검토 중", "부서별 소액 배정", "전사 예산 편성", "연간 정례 예산 편성"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "expansion_plan", "type": "radio", "label": "향후 1년 내 확장 계획",
             "options": ["계획 없음", "검토 중", "일부 확대 예정", "적극 확대 예정", "전사 전환 확정"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "adoption_note", "type": "textarea", "label": "도입 과정에서 가장 어려웠던 점을 자유롭게 서술해 주세요."},
        ],
    },
    {
        "key": "depth",
        "title": "2. 업무 활용 깊이",
        "scored": True,
        "questions": [
            {"id": "usage_areas", "type": "multiselect", "label": "AI를 활용 중인 업무 영역 (복수 선택)",
             "options": ["기획/전략", "마케팅/콘텐츠", "영업", "고객지원/CS", "개발/엔지니어링",
                         "데이터분석", "HR/채용", "재무/회계", "생산/품질관리", "법무/컴플라이언스"]},
            {"id": "usage_frequency", "type": "radio", "label": "조직 내 평균 활용 빈도",
             "options": ["거의 사용 안 함", "월 1~2회", "주 1~2회", "거의 매일", "업무 필수 도구화"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "automation_ratio", "type": "radio", "label": "반복업무 자동화 대체 비율(체감)",
             "options": ["0%", "1~10%", "11~30%", "31~60%", "61% 이상"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "decision_usage", "type": "radio", "label": "의사결정 과정에서의 활용도",
             "options": ["전혀 활용 안 함", "단순 정보조회만", "보조자료로 참고", "주요 의사결정에 반영", "데이터기반 의사결정 핵심도구"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "content_gen", "type": "radio", "label": "콘텐츠/문서 생성 활용도",
             "options": ["전혀 활용 안 함", "가끔 초안 작성 보조", "정기적으로 활용", "주요 산출물 대부분 활용", "생성-검수-배포가 표준 프로세스화"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "code_gen", "type": "radio", "label": "코드/개발 생성 활용도 (해당없음 포함)",
             "options": ["해당없음(개발조직 없음)", "거의 안 씀", "보조적으로 사용", "적극 사용", "코드리뷰·배포 프로세스에 통합"],
             "scores": [None, 0, 1, 2, 4]},
            {"id": "review_process", "type": "radio", "label": "AI 산출물 검수·피드백 프로세스",
             "options": ["없음", "개인별 임의 확인", "팀 단위 리뷰 존재", "표준 검수 프로세스 존재", "품질지표로 관리"],
             "scores": [0, 1, 2, 3, 4], "weight": 3, "critical": True},
            {"id": "data_usage", "type": "radio", "label": "데이터 분석/인사이트 도출 활용도",
             "options": ["전혀 활용 안 함", "가끔 참고", "정기적으로 활용", "주요 리포트 대부분 활용", "데이터 파이프라인에 통합"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "customer_facing", "type": "radio", "label": "고객 대응(챗봇 등) 활용 여부",
             "options": ["없음", "검토 중", "시범 운영", "일부 채널 운영", "전체 채널 핵심 운영"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "depth_note", "type": "textarea", "label": "가장 성공적이었던 AI 활용 사례를 서술해 주세요."},
        ],
    },
    {
        "key": "ops",
        "title": "3. 운영체계",
        "scored": True,
        "questions": [
            {"id": "operation_mode", "type": "radio", "label": "운영 방식",
             "options": ["운영체계 없음", "부서별 자율 운영", "중앙 IT 통제", "전담 TF 운영", "CoE(전사 전담조직) 운영"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "dedicated_org", "type": "radio", "label": "전담 조직/인력 여부",
             "options": ["없음", "겸직 담당자 1명", "겸직 담당자 여러 명", "전담팀 존재(소규모)", "전담 조직 + 임원(C-Level) 존재"],
             "scores": [0, 1, 2, 3, 4], "weight": 3, "critical": True},
            {"id": "vendor_management", "type": "radio", "label": "벤더/도구 관리 프로세스",
             "options": ["없음(개인이 임의 선택)", "부서별 임의 선택", "IT 승인 절차 존재", "전사 벤더 관리 프로세스 존재", "벤더 성과평가 체계까지 운영"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "budget_owner", "type": "select", "label": "예산 편성 주체",
             "options": ["없음", "각 부서장", "IT부서", "경영기획실", "경영진(C-Level) 직접 승인"]},
            {"id": "integration_level", "type": "radio", "label": "기존 시스템과의 통합 수준",
             "options": ["개별 툴로 파편적 사용", "일부 연동", "주요 시스템과 부분 연동", "핵심 업무 시스템에 통합", "전사 데이터/시스템과 완전 통합"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "sop_existence", "type": "radio", "label": "표준운영절차(SOP)/가이드라인 존재 여부",
             "options": ["없음", "작성 중", "일부 부서만 존재", "전사 가이드라인 존재", "가이드라인 + 정기 업데이트 체계"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "tool_selection_process", "type": "radio", "label": "신규 도구 도입 의사결정 프로세스",
             "options": ["프로세스 없이 개인 판단", "구두 협의 수준", "간단한 승인 절차", "평가 기준에 따른 심사", "파일럿→검증→확산 정식 프로세스"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "incident_response", "type": "radio", "label": "장애/오류 발생 시 대응 프로세스",
             "options": ["없음", "그때그때 대응", "담당자 선에서 처리", "매뉴얼 존재", "매뉴얼 + 사후 재발방지 프로세스"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "ops_note", "type": "textarea", "label": "운영상 가장 큰 애로사항을 서술해 주세요."},
        ],
    },
    {
        "key": "governance",
        "title": "4. 거버넌스·리스크정책",
        "scored": True,
        "questions": [
            {"id": "security_policy", "type": "radio", "label": "데이터보안정책 존재 여부",
             "options": ["없음", "구두 권고 수준", "문서화된 정책 존재", "정책 + 정기 교육", "정책 + 기술적 통제(접근제어 등) 적용"],
             "scores": [0, 1, 2, 3, 4], "weight": 3, "critical": True},
            {"id": "confidential_policy", "type": "radio", "label": "기밀/개인정보 입력 금지 지침",
             "options": ["없음", "권고사항 수준", "명문화된 지침 존재", "지침 + 정기 교육", "지침 + 기술적 차단(DLP 등) 적용"],
             "scores": [0, 1, 2, 3, 4], "weight": 3, "critical": True},
            {"id": "copyright_policy", "type": "radio", "label": "저작권/라이선스 정책",
             "options": ["없음", "검토 중", "가이드라인 존재", "가이드라인 + 계약서 반영", "가이드라인 + 정기 점검"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "ethics_guideline", "type": "radio", "label": "AI 윤리 가이드라인 존재 여부",
             "options": ["없음", "검토 중", "선언적 수준의 원칙만 존재", "구체적 가이드라인 존재", "가이드라인 + 위반시 조치 규정"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "responsibility", "type": "radio", "label": "오류·사고 발생 시 책임소재 규정",
             "options": ["없음", "암묵적으로만 존재", "일부 규정 존재", "명문화된 규정 존재", "규정 + 실제 적용 사례 있음"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "audit_cycle", "type": "radio", "label": "감사/모니터링 주기",
             "options": ["없음", "비정기적", "연 1회", "분기별", "상시 모니터링"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "compliance_check", "type": "radio", "label": "법규 준수 점검(저작권법·개인정보보호법 등)",
             "options": ["없음", "필요시에만 확인", "연 1회 점검", "정기 점검 체계", "전담 법무 검토 프로세스"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "governance_body", "type": "radio", "label": "거버넌스 협의체(위원회 등) 존재 여부",
             "options": ["없음", "검토 중", "비정기 협의체", "정기 협의체 운영", "협의체 + 정기 경영보고"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "governance_note", "type": "textarea", "label": "거버넌스 관련 우려사항을 서술해 주세요."},
        ],
    },
    {
        "key": "people",
        "title": "5. 인력·교육",
        "scored": True,
        "questions": [
            {"id": "training_exist", "type": "radio", "label": "교육 실시 여부",
             "options": ["없음", "검토 중", "일회성 실시", "정기적 실시", "전사 정례 교육 체계"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "training_types", "type": "multiselect", "label": "실시 중인 교육 종류 (복수 선택)",
             "options": ["집합교육", "온라인 교육(LMS)", "사내 강사 육성", "외부 전문기관 위탁", "자율학습 지원(구독료 지원 등)", "실무 프로젝트 코칭"]},
            {"id": "training_scope", "type": "radio", "label": "교육 대상 범위",
             "options": ["없음", "일부 관심자만", "특정 부서", "전 임직원 대상", "전 임직원 + 신규입사자 필수"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "completion_rate", "type": "radio", "label": "교육 이수율",
             "options": ["교육 없음", "30% 미만", "30~60%", "60~90%", "90% 이상"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "literacy_level", "type": "radio", "label": "조직 전반의 AI 리터러시 수준 (자체 평가)",
             "options": ["매우 낮음", "낮음", "보통", "높음", "매우 높음"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "champion_program", "type": "radio", "label": "사내 챔피언/앰버서더 제도",
             "options": ["없음", "검토 중", "비공식적으로 존재", "공식 제도 운영", "제도 + 인센티브 운영"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "hiring_reflect", "type": "radio", "label": "채용 시 AI 역량 반영 여부",
             "options": ["전혀 반영 안 함", "일부 직무만 우대", "다수 직무에 우대", "필수 역량으로 명시", "채용 프로세스에 AI역량 평가 포함"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "eval_reflect", "type": "radio", "label": "성과평가/보상에 AI 활용도 반영 여부",
             "options": ["전혀 반영 안 함", "검토 중", "일부 반영", "정식 평가항목으로 반영", "보상·승진과 직접 연계"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "knowledge_sharing", "type": "radio", "label": "사내 활용사례/노하우 공유 체계",
             "options": ["없음", "비정기적 공유", "부서 단위 공유", "전사 공유 채널 운영", "공유 채널 + 정기 발표회"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "people_note", "type": "textarea", "label": "교육·역량 강화 관련 가장 큰 고민을 서술해 주세요."},
        ],
    },
    {
        "key": "culture",
        "title": "6. 조직문화·변화저항",
        "scored": True,
        "questions": [
            {"id": "leadership_attitude", "type": "radio", "label": "경영진의 AI 도입 태도",
             "options": ["부정적/회의적", "관망", "관심은 있으나 소극적", "적극 지지", "직접 솔선수범하여 활용"],
             "scores": [0, 1, 2, 3, 4], "weight": 3},
            {"id": "psychological_safety", "type": "radio", "label": "실패·실험에 대한 심리적 안전감",
             "options": ["매우 낮음", "낮음", "보통", "높음", "매우 높음"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "resistance_intensity", "type": "radio", "label": "조직 내 저항 강도 (체감)",
             "options": ["매우 강한 저항", "상당히 있음", "보통", "약간 있음", "저항 거의 없음"],
             "scores": [0, 1, 2, 3, 4], "weight": 3, "critical": True},
            {"id": "resistance_factors", "type": "multiselect", "label": "저항 요인 (복수 선택)",
             "options": ["일자리 불안", "기술 신뢰 부족", "학습 시간/여유 부족", "기존 방식 고수", "실패 경험/트라우마",
                         "윗선의 무관심", "보안/윤리 우려", "성과 불확실성", "기타"]},
            {"id": "resistance_layer", "type": "multiselect", "label": "저항이 가장 큰 계층 (복수 선택)",
             "options": ["경영진", "중간관리자", "실무자(주니어)", "실무자(시니어)", "특정 부서(현업)"]},
            {"id": "change_mgmt_program", "type": "radio", "label": "변화관리 프로그램 운영 여부",
             "options": ["없음", "검토 중", "비정기 시행", "정기 프로그램 운영", "전담 변화관리 조직/전문가 투입"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "communication_freq", "type": "radio", "label": "관련 커뮤니케이션(타운홀·뉴스레터 등) 빈도",
             "options": ["전혀 없음", "연 1~2회", "분기별", "월별", "상시 채널 운영"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "failure_tolerance", "type": "radio", "label": "실패를 허용하는 문화 수준",
             "options": ["매우 낮음", "낮음", "보통", "높음", "매우 높음"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "cross_dept_collab", "type": "radio", "label": "부서 간 협업/지식공유 수준",
             "options": ["매우 낮음", "낮음", "보통", "높음", "매우 높음"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "success_sharing", "type": "radio", "label": "성공사례 공유 빈도",
             "options": ["전혀 없음", "가끔", "보통", "자주", "매우 자주"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "culture_note", "type": "textarea", "label": "조직 저항과 관련된 구체적 에피소드를 서술해 주세요."},
        ],
    },
    {
        "key": "performance",
        "title": "7. 성과·ROI",
        "scored": True,
        "questions": [
            {"id": "kpi_exist", "type": "radio", "label": "AI 관련 성과지표(KPI) 존재 여부",
             "options": ["없음", "검토 중", "부서별 자체 지표", "전사 표준 지표 존재", "지표 + 정기 리뷰 체계"],
             "scores": [0, 1, 2, 3, 4], "weight": 3, "critical": True},
            {"id": "kpi_types", "type": "multiselect", "label": "측정 중인 지표 (복수 선택)",
             "options": ["생산성/시간절감", "비용절감", "품질 향상", "업무 속도", "매출/수익 기여", "고객만족도", "기타"]},
            {"id": "quant_effect", "type": "radio", "label": "정량적 성과 체감 정도",
             "options": ["전혀 없음", "미미함", "보통", "상당함", "매우 큼"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "roi_calculated", "type": "radio", "label": "ROI(투자대비효과) 산정 여부",
             "options": ["산정 안 함", "검토 중", "일부 프로젝트만 산정", "주요 프로젝트 산정", "전 프로젝트 정례 산정"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "report_cycle", "type": "radio", "label": "성과 보고 주기",
             "options": ["보고 안 함", "비정기적", "연 1회", "분기별", "월별 정례보고"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "expectation_gap", "type": "radio", "label": "\"AI 도입 성과가 기대했던 수준에 미치지 못한다\"",
             "options": LIKERT_NEG[0], "scores": LIKERT_NEG[1]},
            {"id": "failure_learning", "type": "radio", "label": "\"실패한 AI 프로젝트에서도 교훈을 얻어 다음 시도에 반영한다\"",
             "options": LIKERT_POS[0], "scores": LIKERT_POS[1]},
            {"id": "competitor_position", "type": "radio", "label": "경쟁사 대비 AI 활용 수준 인식",
             "options": ["훨씬 뒤처짐", "다소 뒤처짐", "비슷한 수준", "다소 앞섬", "업계 선도 수준"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "future_investment", "type": "radio", "label": "향후 12개월 추가 투자 의향",
             "options": ["투자 축소 예정", "현행 유지", "소폭 확대", "적극 확대", "전사 핵심전략으로 격상"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "performance_note", "type": "textarea", "label": "성과와 관련된 구체적 수치나 사례가 있다면 서술해 주세요."},
        ],
    },
    {
        "key": "risk",
        "title": "8. 리스크 노출·대응",
        "scored": True,
        "questions": [
            {"id": "security_incident", "type": "radio", "label": "정보유출/보안사고 경험",
             "options": ["경험 있음(심각)", "경험 있음(경미)", "아슬아슬했던 적 있음", "경험 없음", "경험 없음 + 예방체계 구축 완료"],
             "scores": [0, 1, 2, 3, 4], "weight": 3, "critical": True},
            {"id": "hallucination_issue", "type": "radio",
             "label": "\"AI가 생성한 잘못된 정보(할루시네이션)로 업무상 문제가 발생한 적이 있다\"",
             "options": LIKERT_NEG[0], "scores": LIKERT_NEG[1], "weight": 2},
            {"id": "legal_concern", "type": "radio", "label": "\"우리 조직은 AI 사용에 따른 법적 리스크에 충분히 대비하고 있다\"",
             "options": LIKERT_POS[0], "scores": LIKERT_POS[1]},
            {"id": "customer_complaint", "type": "radio", "label": "AI 산출물로 인한 고객 클레임 경험",
             "options": ["경험 있음(심각)", "경험 있음(경미)", "아슬아슬했던 적 있음", "경험 없음", "경험 없음 + 예방체계 구축 완료"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "vendor_lockin", "type": "radio", "label": "\"특정 AI 벤더에 대한 의존도가 높아 전환이 어렵다고 느낀다\"",
             "options": LIKERT_NEG[0], "scores": LIKERT_NEG[1]},
            {"id": "bias_issue", "type": "radio", "label": "\"AI 산출물에서 편향되거나 차별적인 결과를 발견한 적이 있다\"",
             "options": LIKERT_NEG[0], "scores": LIKERT_NEG[1], "weight": 2},
            {"id": "regulation_readiness", "type": "radio", "label": "AI 관련 규제(EU AI Act, 국내 AI기본법 등) 대응 준비도",
             "options": ["전혀 파악 못함", "인지만 하고 있음", "일부 검토", "대응 계획 수립", "대응 완료/전담 관리"],
             "scores": [0, 1, 2, 3, 4]},
            {"id": "incident_process", "type": "radio", "label": "사고 발생 시 대응 프로세스/매뉴얼 존재 여부",
             "options": ["없음", "검토 중", "간단한 절차만 존재", "매뉴얼 존재", "매뉴얼 + 정기 훈련"],
             "scores": [0, 1, 2, 3, 4], "weight": 2},
            {"id": "risk_note", "type": "textarea", "label": "리스크 관련 가장 우려되는 지점을 서술해 주세요."},
        ],
    },
]


def _validate_sections():
    for section in SECTIONS:
        for q in section["questions"]:
            if "scores" in q:
                assert len(q["scores"]) == len(q["options"]), (
                    f"{section['key']}.{q['id']}: options/scores 길이 불일치"
                )


_validate_sections()

TOTAL_STEPS = len(SECTIONS)

# ============================================================
# 3. 세션 상태 초기화
# ============================================================
if "step" not in st.session_state:
    st.session_state.step = 0
if "unlocked" not in st.session_state:
    st.session_state.unlocked = False
if "report" not in st.session_state:
    st.session_state.report = ""
if "answers" not in st.session_state:
    # 문항 응답은 위젯의 key가 아니라 이 딕셔너리에 직접 저장한다.
    # Streamlit은 특정 런에서 렌더링되지 않은 위젯의 session_state를 지워버리므로
    # (다른 단계로 이동하면 이전 단계 위젯이 이번 런에 없다고 간주해 값이 삭제됨),
    # 단계 이동 후에도 값을 유지하려면 위젯 key에 의존하지 않고 별도 dict로 관리해야 한다.
    st.session_state.answers = {}


def wkey(section_key, qid):
    return f"w_{section_key}.{qid}"


def _option_index(options, current):
    """현재 값이 옵션 목록에 있으면 그 인덱스를, 없으면(=미응답) None을 반환한다.

    None을 반환하면 select/radio가 아무 것도 선택되지 않은 상태로 렌더링되어
    '미응답'과 '첫 번째(대개 최악의) 보기를 실제로 선택함'이 구분된다.
    """
    if current in options:
        return options.index(current)
    return None


# ============================================================
# 4. 렌더링 / 스코어링 / 프롬프트 유틸
# ============================================================
def render_question(section_key, q):
    field_id = f"{section_key}.{q['id']}"
    key = wkey(section_key, q["id"])
    qtype = q["type"]
    label = q["label"]
    current = st.session_state.answers.get(field_id)

    if qtype == "text":
        val = st.text_input(label, value=current or "", key=key)
    elif qtype == "select":
        options = q["options"]
        val = st.selectbox(label, options, index=_option_index(options, current), key=key)
    elif qtype == "radio":
        options = q["options"]
        val = st.radio(label, options, index=_option_index(options, current), key=key)
    elif qtype == "multiselect":
        options = q["options"]
        safe_default = [v for v in (current or []) if v in options]
        val = st.multiselect(label, options, default=safe_default, key=key)
    elif qtype == "textarea":
        val = st.text_area(label, value=current or "", key=key, height=90)

    st.session_state.answers[field_id] = val


def get_answer(section_key, qid, default=None):
    return st.session_state.answers.get(f"{section_key}.{qid}", default)


CRITICAL_CAP = 40  # 레드플래그(치명적 항목) 발생 시 해당 영역 점수 상한


def compute_scores():
    """영역별 0~100 성숙도 점수 계산 (문항별 가중치 + 레드플래그 게이팅 반영)

    운영방식/거버넌스처럼 조직 리스크에 직결되는 항목은 weight를 높게 주고,
    "없음"/"경험 있음(심각)" 같은 치명적 응답(critical=True)이 선택되면
    다른 항목 점수가 아무리 높아도 해당 영역 점수를 CRITICAL_CAP 이하로 캡핑한다.
    """
    result = {}
    flags = {}
    for section in SECTIONS:
        if not section["scored"]:
            continue
        weighted_sum = 0.0
        weight_total = 0.0
        triggered = []
        for q in section["questions"]:
            if "scores" not in q:
                continue
            val = get_answer(section["key"], q["id"])
            if val not in q["options"]:
                continue
            idx = q["options"].index(val)
            raw = q["scores"][idx]
            if raw is None:
                continue
            valid_scores = [s for s in q["scores"] if s is not None]
            max_s = max(valid_scores) if valid_scores else 4
            if max_s == 0:
                continue
            weight = q.get("weight", 1)
            weighted_sum += (raw / max_s) * weight
            weight_total += weight
            if q.get("critical") and raw == 0:
                triggered.append(q["label"])
        score = round(weighted_sum / weight_total * 100) if weight_total else 0
        if triggered:
            score = min(score, CRITICAL_CAP)
        result[section["key"]] = score
        flags[section["key"]] = triggered
    return result, flags


def render_radar(scores: dict):
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("plotly가 설치되어 있지 않아 레이더 차트를 표시할 수 없습니다.")
        return
    labels = [CATEGORIES[k] for k in scores.keys()]
    values = list(scores.values())
    labels_closed = labels + labels[:1]
    values_closed = values + values[:1]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values_closed, theta=labels_closed, fill="toself", name="진단 결과"))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(l=30, r=30, t=30, b=30),
    )
    st.plotly_chart(fig, use_container_width=True)


def build_answer_summary():
    lines = []
    for section in SECTIONS:
        lines.append(f"\n### {section['title']}")
        for q in section["questions"]:
            val = get_answer(section["key"], q["id"])
            if val in (None, "", []):
                val = "(무응답)"
            if isinstance(val, list):
                val = ", ".join(val) if val else "(무응답)"
            lines.append(f"- {q['label']}: {val}")
    return "\n".join(lines)


def build_prompt(scores: dict, flags: dict):
    score_lines = "\n".join(f"- {CATEGORIES[k]}: {v}/100점" for k, v in scores.items())
    flag_lines = "\n".join(
        f"- {CATEGORIES[k]}: {', '.join(v)}" for k, v in flags.items() if v
    ) or "(해당 없음)"
    answer_summary = build_answer_summary()
    company_name = get_answer("basic", "company_name") or "해당 조직"

    prompt = f"""
너는 조직의 AI 전환(AX) 성숙도를 진단하는 전문 컨설턴트다. 아래는 '{company_name}'이(가) 90개 이상의 문항에 응답한
정밀 진단 설문 원자료와, 그 응답을 바탕으로 8개 영역별로 계산된 0~100점 성숙도 점수다.
이 데이터는 100% 확실한 응답이므로 '정보가 부족하다', '추가 확인이 필요하다'는 표현은 쓰지 말고,
주어진 데이터를 최대한 구체적으로 인용하며 실전적인 진단 보고서를 작성하라.

[영역별 성숙도 점수 (문항별 가중치 반영, 치명적 항목 발견 시 {CRITICAL_CAP}점 이하로 캡핑됨)]
{score_lines}

[영역별 레드플래그(치명적 항목) 발생 내역]
{flag_lines}

[설문 원자료]
{answer_summary}

[보고서 작성 지침]
1. 절대 뭉뚱그리지 말고, 응답 항목을 직접 근거로 들어 분석하라. (예: "귀사는 '{company_name}'의 경우 도입기간이 1~2년임에도
   전담조직이 없다는 점에서...")
2. 8개 영역 각각에 대해 점수, 현황요약, 강점, 약점/리스크, 구체적 실행 권고안(담당 주체 포함)을 제시하라. 레드플래그가
   발생한 영역은 왜 점수가 낮게 캡핑되었는지 반드시 명시하고, 이를 최우선 개선과제로 다뤄라.
3. 조직저항 영역은 근본원인 분석과 계층별(경영진/중간관리자/실무자) 대응전략을 별도로 심층 분석하라.
4. 전체 결과를 종합해 조직의 'AI 도입 성숙도 단계'에 이름을 붙여라 (예: 1단계 관망기 / 2단계 실험기 / 3단계 확산기 /
   4단계 정착기 / 5단계 고도화기 중 하나를 선택하고 근거를 제시).
5. 단기(0~3개월)/중기(3~12개월)/장기(1년 이상) 우선순위 액션플랜을 각각 3~5개씩, 담당 주체와 기대효과를 포함해 제시하라.
6. 분기별 12개월 로드맵을 표 형태로 제시하라.
7. 불필요한 홍보성 수식어("30년 경력의 전문가" 등)는 배제하고 팩트와 데이터 기반으로 작성하라.
8. 전체 분량은 상세한 정식 컨설팅 보고서 수준으로, 마크다운 제목(#, ##)과 표를 적극 활용해 구조화하라.

[보고서 목차]
# {company_name} AI 조직 세부진단 보고서
## 1. 종합 진단 요약 (Executive Summary)
## 2. AI 도입 성숙도 단계 판정
## 3. 영역별 상세 분석 (8개 영역)
## 4. SWOT 분석
## 5. 조직 저항 심층 분석
## 6. 거버넌스·리스크 점검표
## 7. 우선순위 액션플랜 (단기/중기/장기)
## 8. 12개월 로드맵 (분기별 표)
## 9. 맺음말
"""
    return prompt


def send_backup_email(company_name: str, report_text: str, answer_summary: str):
    """진단 완료 시 회사 백업 메일함으로 원본 응답 + 리포트를 자동 발송한다.

    SMTP_EMAIL / SMTP_PASSWORD(발신 계정, 예: Gmail 앱 비밀번호) 시크릿이
    설정되어 있지 않으면 조용히 건너뛴다 (사용자 플로우를 막지 않음).
    """
    smtp_email = get_secret("SMTP_EMAIL")
    smtp_password = get_secret("SMTP_PASSWORD")
    if not smtp_email or not smtp_password:
        return False, "SMTP 시크릿 미설정"

    backup_email = get_secret("BACKUP_EMAIL", smtp_email)
    today = datetime.date.today().isoformat()

    msg = MIMEMultipart()
    msg["From"] = smtp_email
    msg["To"] = backup_email
    msg["Subject"] = f"[AI조직진단] {company_name} 진단결과 ({today})"
    body = f"{report_text}\n\n{'=' * 40}\n[원본 응답 전체]\n{answer_summary}\n"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


# ============================================================
# 5. 접근 게이트 (아임웹 결제 링크 + 접근코드 확인)
# ============================================================
st.title("🧭 AI 조직 세부진단 키트 (Pro)")
st.caption("90개 이상의 문항으로 조직의 AI 도입 현황을 다각도로 정밀 진단하는 유료 리포트입니다.")

raw_codes = get_secret("ACCESS_CODES", "")
valid_codes = [c.strip() for c in raw_codes.split(",") if c.strip()] if raw_codes else []
imweb_url = get_secret("IMWEB_PRODUCT_URL")

if raw_codes and not valid_codes:
    # ACCESS_CODES가 설정은 됐지만(콤마/공백만 있는 등) 파싱 후 남는 코드가 없는 경우:
    # "설정 안 함(오픈)"과 "설정했으나 값이 잘못됨"을 반드시 구분해서, 후자는 절대
    # 열어주지 않고 막아야 한다 (그렇지 않으면 유료 진단이 조용히 무료로 뚫려버린다).
    st.error("⚠️ ACCESS_CODES 시크릿 설정에 오류가 있어 접근을 확인할 수 없습니다. 관리자에게 문의하세요.")
    st.stop()

if valid_codes and not st.session_state.unlocked:
    st.info("본 진단은 결제 후 이용 가능합니다. 아임웹에서 결제를 완료하면 발급되는 주문번호를 접근 코드로 입력해 주세요.")
    if imweb_url:
        st.link_button("💳 결제하러 가기 (아임웹)", imweb_url)

    qp_code = st.query_params.get("code", "")
    code_input = st.text_input("접근 코드(주문번호) 입력", value=qp_code, type="password")

    auto_try = bool(qp_code) and "code_auto_tried" not in st.session_state
    if st.button("코드 확인") or auto_try:
        st.session_state.code_auto_tried = True
        if code_input in valid_codes:
            st.session_state.unlocked = True
            st.rerun()
        else:
            st.error("접근 코드가 올바르지 않습니다. 아임웹 주문 내역의 주문번호를 다시 확인해 주세요.")
    st.stop()
elif not valid_codes:
    st.caption("⚠️ 접근 코드가 설정되어 있지 않아 테스트 모드로 열려 있습니다. (운영 전 ACCESS_CODES 시크릿을 설정하세요)")

if model is None:
    # 문항 작성 자체는 막지 않되(응답은 저장 가능), 90개 문항을 다 채운 뒤
    # 마지막 단계에서야 실패를 알게 되는 일이 없도록 미리 경고한다.
    st.warning(
        "⚠️ GEMINI_API_KEY가 설정되어 있지 않습니다. 문항은 작성/저장할 수 있지만, "
        "마지막 단계의 '진단 결과 생성'은 지금 실패합니다. 운영 전 시크릿을 설정해 주세요."
    )

# ============================================================
# 5-1. 진행상황 저장/이어하기 (중단·접속끊김 대비)
# ============================================================
# 서버(Streamlit) 세션은 재시작되거나 접속이 끊기면 사라지므로, 서버에 의존하지
# 않고 사용자가 직접 파일로 내려받아 보관했다가 다시 업로드해서 이어가는 방식으로 구현한다.
with st.expander("💾 진행 상황 저장 / 이어서 하기 (중간에 중단하거나 접속이 끊겨도 안전)"):
    st.caption(
        "문항이 많아 한 번에 끝내기 어려울 수 있습니다. 언제든 아래 버튼으로 지금까지의 "
        "답변을 파일로 저장해두었다가, 나중에 그 파일을 업로드하면 저장한 시점부터 이어서 "
        "진행할 수 있습니다. (단, 현재 페이지는 '다음/이전' 버튼을 한 번 눌러야 저장 대상에 포함되며, "
        "결제 확인(접근 코드)은 이 파일에 포함되지 않으므로 세션이 끊긴 뒤에는 접근 코드를 다시 "
        "입력한 후 이 파일을 불러오면 됩니다.)"
    )
    progress_payload = {
        "step": st.session_state.step,
        "answers": st.session_state.answers,
    }
    st.download_button(
        "💾 진행 상황 저장하기",
        data=json.dumps(progress_payload, ensure_ascii=False, indent=2),
        file_name=f"AI진단_진행상황_{datetime.date.today().isoformat()}.json",
        mime="application/json",
    )

    uploaded_progress = st.file_uploader("저장해둔 진행 상황 파일(.json) 업로드", type=["json"])
    if uploaded_progress is not None and st.button("📂 불러온 내용으로 이어서 진행하기"):
        try:
            loaded = json.loads(uploaded_progress.read().decode("utf-8"))
            if not isinstance(loaded.get("answers"), dict):
                raise ValueError("answers 필드가 없거나 형식이 올바르지 않습니다.")
            loaded_step = loaded.get("step", 0)
            if not isinstance(loaded_step, int) or not (0 <= loaded_step < TOTAL_STEPS):
                raise ValueError(f"step 값이 올바르지 않습니다: {loaded_step!r}")
            st.session_state.answers.update(loaded["answers"])
            st.session_state.step = loaded_step
            st.success("진행 상황을 불러왔습니다.")
            st.rerun()
        except Exception as e:
            st.error(f"파일을 불러오는 중 오류가 발생했습니다: {e} (올바른 저장 파일인지 확인해 주세요)")

# ============================================================
# 6. 진단 위저드
# ============================================================
step = st.session_state.step
section = SECTIONS[step]

st.progress((step) / (TOTAL_STEPS - 1) if TOTAL_STEPS > 1 else 1.0)
st.subheader(section["title"])
st.caption(f"{step + 1} / {TOTAL_STEPS} 단계")

with st.form(f"form_{section['key']}"):
    for q in section["questions"]:
        render_question(section["key"], q)
    col1, col2 = st.columns(2)
    with col1:
        prev_clicked = st.form_submit_button("◀ 이전", disabled=(step == 0))
    with col2:
        next_label = "진단 결과 생성 ▶" if step == TOTAL_STEPS - 1 else "다음 ▶"
        next_clicked = st.form_submit_button(next_label)

if prev_clicked and step > 0:
    st.session_state.step -= 1
    st.rerun()

if next_clicked and step == 0 and not get_answer("basic", "company_name"):
    st.error("회사명(또는 조직명)을 입력해 주세요.")
    next_clicked = False

if next_clicked:
    if step < TOTAL_STEPS - 1:
        st.session_state.step += 1
        st.rerun()
    else:
        if model is None:
            st.error("API 키 설정을 확인하세요 (GEMINI_API_KEY 시크릿 필요).")
        else:
            with st.spinner("90개 이상의 응답을 종합하여 정밀 진단 보고서를 생성 중입니다..."):
                scores, flags = compute_scores()
                st.session_state.scores = scores
                prompt = build_prompt(scores, flags)
                try:
                    response = model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.4,
                            max_output_tokens=8192,
                        ),
                    )
                    st.session_state.report = response.text
                    company_name = get_answer("basic", "company_name") or "무명 조직"
                    # 백업 메일은 사용자 화면 표시를 막아서는 안 되는 부가 기능이므로,
                    # 별도 스레드에서 발송하고 결과를 기다리지 않는다(성공 여부는 확인 못함).
                    threading.Thread(
                        target=send_backup_email,
                        args=(company_name, response.text, build_answer_summary()),
                        daemon=True,
                    ).start()
                    st.session_state.backup_attempted = True
                except Exception as e:
                    st.error(f"오류: {e}")

# ============================================================
# 7. 결과 출력
# ============================================================
if st.session_state.report:
    st.divider()
    st.markdown("## 📊 영역별 성숙도 점수")
    render_radar(st.session_state.get("scores", {}))

    st.markdown("## 📜 정밀 진단 보고서")
    st.markdown(st.session_state.report)

    st.download_button(
        "⬇️ 보고서 다운로드 (Markdown)",
        data=st.session_state.report,
        file_name=f"AI조직진단보고서_{datetime.date.today().isoformat()}.md",
        mime="text/markdown",
    )

    if st.session_state.get("backup_attempted"):
        st.caption("📧 회사 백업 메일함으로 발송을 시도했습니다. (실패하더라도 위 다운로드 버튼으로 항상 보관 가능합니다)")

    st.divider()
    if st.button("🔄 새 진단 시작하기"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

st.caption("© 2026 AI 조직 세부진단 키트")
