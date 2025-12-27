import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 모델 설정
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
    else:
        model = None
except Exception:
    model = None

# [설정] 쿠팡 파트너스 링크 (본인의 링크로 수정하세요)
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화
if 'unlocked' not in st.session_state:
    st.session_state.unlocked = False
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""

# 앱 환경 설정
st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")
st.write("병오년(丙午年)의 기운을 읽어 당신의 삶에 가장 현실적인 방책을 제시합니다.")

# 2. 사용자 입력 섹션
with st.form("fortune_form"):
    user_name = st.text_input("성함", placeholder="본명을 입력해 주세요.")
    
    st.write("### 생년월일 선택")
    col_y, col_m, col_d = st.columns(3)
    with col_y:
        year = st.selectbox("년", range(2026, 1919, -1), index=31)
    with col_m:
        month = st.selectbox("월", range(1, 13), index=0)
    with col_d:
        day = st.selectbox("일", range(1, 32), index=0)
        
    calendar_type = st.radio("날짜 구분", ["양력", "음력"], horizontal=True)
    
    st.divider()
    
    col_time, col_gender = st.columns(2)
    with col_time:
        birth_time = st.time_input("출생 시각", value=datetime.time(12, 0))
    with col_gender:
        gender = st.radio("성별", ["남성", "여성"], horizontal=True)
    
    user_mbti = st.selectbox("당신의 성향(MBTI)", [
        "ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"
    ])

    user_concern = st.text_area("요즘 가장 큰 고민은 무엇인가요? (역술인에게 묻기)", 
                                 placeholder="예: 내년에 이직운이 있을까요? 돈 때문에 힘든데 언제 풀릴까요?")

    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정이 올바르지 않습니다.")
        else:
            with st.spinner("하늘의 기운을 분석하고 있습니다..."):
                st.session_state.unlocked = False # 새로운 분석 시 다시 잠금
                birth_date_str = f"{year}년 {month}월 {day}일"
                
                # 정교화된 전문가 프롬프트
                prompt = f"""
                당신은 전통 명리학과 심리학에 통달한 역술가입니다. {user_name}님의 사주와 성향({user_mbti})을 분석하세요.
                성별: {gender}, 생일: {birth_date_str}({calendar_type}), 시간: {birth_time}
                고민내용: {user_concern}

                [결과 구조 및 필수 지침]
                1. 상단 섹션 (잠금 전 노출):
                   - [사주 요약]: 전체적인 사주의 강점과 특징 (3줄 내외)
                   - [MBTI 요약]: {user_mbti} 성향이 운세와 결합될 때의 특징 (3줄 내외)
                   - [2026 병오년 총평]: 2026년 한 해를 관통하는 가장 중요한 메시지
                
                2. 하단 섹션 (잠금 후 노출):
                   ---잠금구분선---
                   - 1. 통합분석: 2026년의 전체적인 흐름
                   - 2. 재물운 / 3. 인간관계운 / 4. 사랑운 / 5. 건강운 (구체적으로 작성)
                   - 6. 처세 지침: 삼재 여부, 행운의 달, 행운/피해야 할 방위
                   - 7. 고민에 대한 해답: 사용자의 고민("{user_concern}")에 대해 역술가로서의 데이터 기반 솔직하고 직설적인 답변
                
                자기소개는 생략하고, 따뜻하면서도 무게감 있는 어조로 작성하세요.
                상단과 하단 사이에 반드시 "---잠금구분선---"이라는 문구를 넣어주세요.
                """

                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류 발생: {e}")

# 4. 결과 출력 및 잠금 로직
if st.session_state.full_report:
    report = st.session_state.full_report
    
    # 구분선을 기준으로 상단/하단 분리
    if "---잠금구분선---" in report:
        top_part, bottom_part = report.split("---잠금구분선---")
    else:
        top_part = report
        bottom_part = ""

    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 운명 리포트")
    st.markdown(top_part) # 상단 요약 및 총평 출력

    # 잠금 상태 체크
    if not st.session_state.unlocked:
        st.info("💡 더욱 구체적인 운세 상세(재물, 연애, 건강)와 고민 해답을 보려면 아래 버튼을 이용하세요.")
        
        # 쿠팡 버튼 및 이해관계 표시
        st.link_button("👉 쿠팡 방문하고 모든 결과 확인하기", COUPANG_URL)
        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")
        
        if st.button("✅ 방문을 완료했습니다 (잠금 해제)"):
            st.session_state.unlocked = True
            st.rerun()
    else:
        st.success("🔓 잠금이 해제되었습니다. 상세 분석 결과를 확인하세요.")
        st.markdown(bottom_part) # 하단 상세 내용 및 고민 답변 출력
        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석 - 본 결과는 참고용이며 삶의 주체는 본인에게 있습니다.")