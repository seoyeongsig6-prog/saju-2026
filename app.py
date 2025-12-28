import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 모델 초기화
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [설정] 본인의 쿠팡 파트너스 링크
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화 (결과와 단계를 엄격히 보존)
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'step' not in st.session_state:
    st.session_state.step = 0 # 0:분석전, 1:쿠팡방문버튼, 2:결과확인버튼, 3:내용공개

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
    user_concern = st.text_area("요즘 고민 (비워두면 결과에서 제외)")

    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정을 확인하세요.")
        else:
            with st.spinner("운명의 흐름을 읽는 중..."):
                st.session_state.step = 1 # 즉시 1단계 진입
                birth_date_str = f"{year}년 {month}월 {day}일"
                concern_prompt = f"6. 고민 해결: '{user_concern}'에 대한 조언" if user_concern.strip() else ""
                
                prompt = f"""당신은 역술가입니다. {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
---잠금구분선--- 문구를 사용하여 상단과 하단을 반드시 나누세요.
상단: [사주요약], [MBTI요약], [2026 병오년 총평]
하단: 상세운세(재물/사랑/인간관계/건강), {concern_prompt}"""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류: {e}")

# 3. 결과 출력 및 1버튼 릴레이 로직
if st.session_state.full_report:
    report = st.session_state.full_report
    if "---잠금구분선---" in report:
        top_part, bottom_part = report.split("---잠금구분선---", 1)
    else:
        top_part, bottom_part = report, "상세 데이터를 불러오지 못했습니다."

    st.divider()
    st.markdown(f"## 📜 운명 리포트")
    st.markdown(top_part)

    # === [단계별 버튼 제어] 하나씩만 노출 ===
    
    # 1단계: 쿠팡 방문 버튼 (누르면 링크 열리고 사라짐)
    if st.session_state.step == 1:
        st.write("---")
        st.warning("🔒 상세 운세가 잠겨 있습니다. 아래 버튼을 눌러주세요.")
        if st.button("🚀 1단계: 쿠팡 방문하기", use_container_width=True, type="primary"):
            # 자바스크립트로 링크 열기
            js = f"window.open('{COUPANG_URL}', '_blank')"
            st.components.v1.html(f"<script>{js}</script>", height=0)
            st.session_state.step = 2 # 2단계로 이동
            st.rerun()

    # 2단계: 결과 확인 버튼 (1단계 버튼이 사라진 자리에 등장)
    elif st.session_state.step == 2:
        st.write("---")
        st.info("✅ 쿠팡 창이 열렸습니다. 방문을 마치셨다면 아래 버튼을 눌러 상세 운세를 확인하세요.")
        if st.button("🔓 2단계: 결과 확인하기", use_container_width=True, type="primary"):
            st.session_state.step = 3 # 최종 공개
            st.rerun()

    # 3단계: 최종 내용 공개
    elif st.session_state.step == 3:
        st.success("🎉 모든 잠금이 해제되었습니다.")
        st.markdown(bottom_part)
        st.caption("이 서비스는 쿠팡 파트너스 활동의 일환으로 일정액의 수수료를 제공받습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석")