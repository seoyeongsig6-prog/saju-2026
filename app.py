import streamlit as st
import google.generativeai as genai
import datetime
import time

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
COUPANG_URL = "https://link.coupang.com/a/XXXXXX" 

# 세션 상태 초기화
if 'unlocked' not in st.session_state:
    st.session_state.unlocked = False
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'visit_clicked' not in st.session_state:
    st.session_state.visit_clicked = False # 방문 버튼 클릭 여부

# 앱 환경 설정
st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")

# 2. 사용자 입력 섹션 (동일)
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
    user_mbti = st.selectbox("당신의 성향(MBTI)", ["ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP", "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"])
    user_concern = st.text_area("요즘 가장 큰 고민은 무엇인가요?", placeholder="예: 이직, 금전, 연애 등")

    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정이 올바르지 않습니다.")
        else:
            with st.spinner("하늘의 기운을 분석하고 있습니다..."):
                st.session_state.unlocked = False 
                st.session_state.visit_clicked = False # 새로운 분석 시 초기화
                birth_date_str = f"{year}년 {month}월 {day}일"
                
                prompt = f"""당신은 역술가입니다. {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
                [필수 구조]
                1. [사주 요약] / 2. [MBTI 요약] / 3. 2026 병오년 총평
                ---잠금구분선---
                4. 상세운세: 통합분석, 재물운, 인간관계운, 사랑운, 건강운
                5. 특별 조언: 삼재 여부, 행운의 달/방위
                6. 고민 해결: "{user_concern}"에 대한 솔직하고 직설적인 답변"""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류 발생: {e}")

# 4. 결과 출력 및 2단계 잠금 로직
if st.session_state.full_report:
    report = st.session_state.full_report
    top_part, bottom_part = report.split("---잠금구분선---") if "---잠금구분선---" in report else (report, "")

    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 운명 리포트")
    st.markdown(top_part) # 요약본 상시 노출

    if not st.session_state.unlocked:
        st.write("---")
        st.warning("🔒 **상세 분석 결과(재물, 연애, 건강, 고민 해결)가 잠겨 있습니다.**")
        
        # [1단계] 방문 버튼
        st.write("**1단계: 아래 버튼을 눌러 쇼핑몰을 방문해 주세요.**")
        # 클릭 시 session_state를 변경하기 위해 html/js 대신 Streamlit의 기능을 조합합니다.
        if st.link_button("👉 쿠팡 방문하기 (새 창)", COUPANG_URL):
            # 링크 버튼은 클릭 시 rerun하지 않으므로, 유저가 클릭했음을 알리는 트리거가 필요합니다.
            st.session_state.visit_clicked = True
        
        # 사용자가 방문 버튼을 눌렀다고 '선언'하면 그제서야 '확인' 버튼을 보여줍니다.
        # (심리적으로 버튼을 눌러야 다음 단계가 나온다는 것을 인지시킴)
        if st.checkbox("쿠팡 페이지를 열었습니다. (체크 시 확인 버튼 등장)"):
            st.write("**2단계: 방문이 완료되었다면 아래 확인 버튼을 눌러주세요.**")
            if st.button("✅ 방문 완료 및 결과 보기"):
                with st.status("데이터 대조 및 잠금 해제 중...", expanded=True) as status:
                    time.sleep(3)
                    status.update(label="확인 완료! 상세 운세를 공개합니다.", state="complete", expanded=False)
                st.session_state.unlocked = True
                st.rerun()

        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")
    else:
        st.success("🔓 모든 분석 결과가 공개되었습니다.")
        st.markdown(bottom_part)
        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석")