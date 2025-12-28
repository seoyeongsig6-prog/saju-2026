import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 모델 초기화 (에러 방지용)
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [필수] 여기에 본인의 쿠팡 파트너스 링크를 넣으세요.
# 이 링크 하나로 AI가 추천한 모든 물건의 수익이 사용자님께 돌아갑니다.
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""

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
            st.error("API 키 설정을 확인하세요.")
        else:
            with st.spinner("하늘의 기운을 읽고 있습니다..."):
                birth_date_str = f"{year}년 {month}월 {day}일"
                concern_prompt = f"### 💡 고민 해결 조언\n'{user_concern}'에 대한 역술가로서의 조언을 작성하세요." if user_concern.strip() else ""
                
                # AI에게 행운의 아이템을 구체적으로 추천하도록 지시
                prompt = f"""당신은 전문 역술가입니다. {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
                
                [필수 구조]
                1. 📋 2026 병오년 총평
                2. 📊 재물/사랑/인간관계/건강 상세 분석
                {concern_prompt}
                3. ✨ 2026 행운을 주는 물건: 
                   이 사용자의 사주와 MBTI를 고려하여 올해 기운을 보강해줄 구체적인 행운의 아이템(예: 특정 색상의 지갑, 풍수 인테리어 소품, 행운의 원석 팔찌 등) 3가지를 추천하고 그 이유를 설명하세요."""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류: {e}")

# 3. 결과 출력 및 사용자 링크 연결
if st.session_state.full_report:
    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 운명 리포트")
    
    # AI가 생성한 전문 출력 (행운의 물건 포함)
    st.markdown(st.session_state.full_report)
    
    # 행운의 물건 섹션 바로 아래에 사용자님의 링크 배치
    st.write("---")
    st.info(f"🔮 **{user_name}님의 행운을 극대화할 아이템들을 지금 바로 확인해보세요.**")
    
    # 사용자님의 파트너스 링크가 걸린 큰 버튼
    st.markdown(f"""
        <div style="text-align: center; margin: 20px 0;">
            <a href="{COUPANG_URL}" target="_blank" style="
                display: inline-block; width: 100%; padding: 20px 0; background-color: #ff4b4b; 
                color: white; text-decoration: none; font-weight: bold; font-size: 20px; 
                border-radius: 12px; box-shadow: 0 4px 15px rgba(255, 75, 75, 0.4);
                transition: all 0.3s ease;
            ">🎁 2026 행운의 아이템 구매하러 가기</a>
        </div>
    """, unsafe_allow_html=True)
    
    st.caption("※ 위 링크를 통해 구매 시 쿠팡 파트너스 활동의 일환으로 일정액의 수수료를 제공받을 수 있습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석")