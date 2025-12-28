import streamlit as st
import google.generativeai as genai
import datetime
import time

# 1. API 키 및 모델 설정 (정의 에러 방지)
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [설정] 본인의 쿠팡 파트너스 링크 입력
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'step' not in st.session_state:
    st.session_state.step = 0 # 0: 분석전, 1: 방문전, 2: 확인전, 3: 완료

st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")

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
    user_mbti = st.selectbox("당신의 성향(MBTI)", ["ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP", "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"])
    user_concern = st.text_area("요즘 가장 큰 고민 (비워두면 리포트에서 제외)")

    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정 에러. Secrets를 확인하세요.")
        else:
            with st.spinner("분석 중..."):
                # 상태 초기화
                st.session_state.step = 1
                birth_date_str = f"{year}년 {month}월 {day}일"
                concern_prompt = f"6. 고민 해결: '{user_concern}'에 대한 조언" if user_concern.strip() else ""
                
                prompt = f"""당신은 역술가입니다. {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
---잠금구분선--- 문구를 사용하여 요약과 상세 내용을 나누세요.
상단: [사주요약], [MBTI요약], [2026 병오년 총평]
하단: 상세운세(재물/사랑/인간관계/건강), {concern_prompt}"""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류: {e}")

# 3. 결과 출력 및 버튼 로직 (순차적 노출 보장)
if st.session_state.full_report:
    report = st.session_state.full_report
    top_part, bottom_part = report.split("---잠금구분선---", 1) if "---잠금구분선---" in report else (report, "")

    st.divider()
    st.markdown(f"## 📜 운명 리포트")
    st.markdown(top_part) # 상단 총평은 항상 노출

    # === 버튼 로직 (중요: if-elif-else 구조로 동시 노출 절대 불가) ===
    
    # [1단계] 쿠팡 방문 전: 오직 방문 버튼만 표시
    if st.session_state.step == 1:
        st.write("---")
        st.warning("🔒 상세 운세와 고민 해답이 잠겨 있습니다.")
        if st.button("🧧 1단계: 쿠팡 방문하고 열쇠 받기 (새 창)"):
            # JavaScript로 새 창 열기
            js = f"window.open('{COUPANG_URL}', '_blank')"
            st.components.v1.html(f"<script>{js}</script>", height=0)
            # 상태 변경 후 즉시 리런 (1단계 버튼 사라짐)
            st.session_state.step = 2
            st.rerun()

    # [2단계] 방문 버튼 클릭 후: 오직 확인 버튼만 표시
    elif st.session_state.step == 2:
        st.write("---")
        st.info("✅ 방문이 완료되었다면 아래 버튼을 눌러주세요.")
        if st.button("🔓 2단계: 전체 확인하기 (잠금 해제)", type="primary"):
            st.session_state.step = 3
            st.rerun()
            
    # [3단계] 최종 완료: 버튼 모두 사라지고 상세 내용 표시
    elif st.session_state.step == 3:
        st.success("🔓 모든 잠금이 해제되었습니다.")
        st.markdown(bottom_part)

st.divider()
st.caption("이 서비스는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")