import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 모델 초기화 (에러 방지를 위해 최상단 선언)
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [필수] 본인의 쿠팡 파트너스 링크 입력
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화
if 'unlocked' not in st.session_state:
    st.session_state.unlocked = False
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'step' not in st.session_state:
    st.session_state.step = 1 # 1: 방문 전, 2: 확인 대기

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
                st.session_state.unlocked = False
                st.session_state.step = 1
                birth_date_str = f"{year}년 {month}월 {day}일"
                
                # 고민 상담 항목 조건부 처리
                concern_text = ""
                if user_concern.strip():
                    concern_text = f"6. 고민 해결: '{user_concern}'에 대한 조언"
                
                prompt = f"""역술가로서 {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
                ---잠금구분선--- 문구를 사용하여 상단과 하단을 나누세요.
                상단: [사주요약], [MBTI요약], [2026 병오년 총평]
                하단: 상세운세(재물/사랑/인간관계/건강), {concern_text}"""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류: {e}")

# 3. 결과 출력 및 2단계 버튼 로직
if st.session_state.full_report:
    report = st.session_state.full_report
    top_part, bottom_part = report.split("---잠금구분선---", 1) if "---잠금구분선---" in report else (report, "")

    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 운명 리포트")
    st.markdown(top_part) # 총평 상시 노출

    if not st.session_state.unlocked:
        st.write("---")
        
        # [상태 1] 방문 버튼만 노출 (요청하신 HTML <a> 태그 방식)
        if st.session_state.step == 1:
            st.warning("🔒 상세 분석 결과와 고민 해답이 잠겨 있습니다.")
            
            # 직접 HTML 링크 섹션
            st.markdown(f"""
                <div style="text-align: center; padding: 20px; border: 2px solid #ff6b6b; border-radius: 10px;">
                    <p style="margin-bottom: 15px; font-weight: bold;">🧧 아래 링크를 클릭하여 쿠팡을 방문해 주세요.</p>
                    <a href="{COUPANG_URL}" target="_blank" style="
                        display: inline-block;
                        padding: 15px 30px;
                        background-color: #ff6b6b;
                        color: white;
                        text-decoration: none;
                        font-weight: bold;
                        border-radius: 5px;
                    ">🚀 쿠팡 방문하고 상세운세 풀기</a>
                </div>
                """, unsafe_allow_html=True)
            
            st.write("")
            if st.button("방문 페이지를 열었습니다 (다음으로)"):
                st.session_state.step = 2
                st.rerun()
        
        # [상태 2] 방문 버튼을 누른 후 (확인 버튼만 노출)
        elif st.session_state.step == 2:
            st.info("✅ 쿠팡 방문이 확인되었습니다.")
            if st.button("🔓 전체 확인하기", type="primary"):
                st.session_state.unlocked = True
                st.rerun()

        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")
    
    else:
        # 잠금 해제 완료 시 내용 출력
        st.success("🔓 모든 잠금이 해제되었습니다.")
        st.markdown(bottom_part)
        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석")