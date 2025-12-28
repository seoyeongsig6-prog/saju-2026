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

# [설정] 사용자님의 쿠팡 파트너스 링크
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""

st.set_page_config(page_title="2026 사주&처세 정밀 분석", layout="centered")
st.title("🏮 2026 사주&처세 정밀 분석")

# 2. 사용자 입력 섹션
with st.form("fortune_form"):
    user_name = st.text_input("성함", placeholder="본명을 입력해 주세요.")
    st.write("### 생년월일 및 출생 정보")
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
    
    user_mbti = st.selectbox("성향(MBTI)", ["ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP", "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"])
    user_concern = st.text_area("구체적인 고민 (비워두면 리포트에서 제외)")

    if st.form_submit_button("정밀 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정을 확인하세요.")
        else:
            with st.spinner("만세력을 구성하고 2026년의 기운을 대조하고 있습니다..."):
                birth_date_str = f"{year}년 {month}월 {day}일"
                concern_prompt = f"### 💡 고민 해결 처세술\n'{user_concern}'에 대한 명리학적 해법을 제시하세요." if user_concern.strip() else ""
                
                # 전문 명리학 + 행운의 물건 지침 강화
                prompt = f"""
                당신은 정통 명리학자입니다. {user_name}({gender}, {birth_date_str}, {user_mbti})의 2026년(丙午年) 운세를 분석하세요.

                [작성 지침]
                - 뻔한 덕담이 아니라 십성(十星)과 용신을 활용해 전문적으로 분석하세요.
                - 2026년 병오년의 강렬한 화(火) 기운이 사용자의 원국에 미치는 영향을 상세히 서술하세요.
                
                [행운의 물건 지침]
                - 마지막 항목인 '행운을 주는 물건'은 반드시 **가볍게 지니고 다닐 수 있는 작은 물건**(예: 카드, 키링, 손수건, 특정 원석 등)으로 추천하세요.
                - "사주상 어떤 기운이 부족하고, 병오년의 기운이 이러하니 이 물건이 그 간극을 메워준다"는 논리적인 근거를 반드시 포함하세요.

                [리포트 구조]
                1. 📋 사주 원국 분석 및 핵심 용신
                2. 🏮 2026 병오년 총평 (세운 분석)
                3. 📊 재물/사랑/인간관계/건강 정밀 분석
                {concern_prompt}
                4. ✨ 2026 행운을 주는 물건 (휴대 가능한 소품 위주 추천)
                """
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류: {e}")

# 3. 결과 출력
if st.session_state.full_report:
    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 정밀 운명 리포트")
    st.markdown(st.session_state.full_report)
    
    # --- 행운의 물건 보기 버튼 섹션 (디자인 최적화) ---
    st.write("")
    st.markdown(f"""
        <div style="text-align: center; margin-top: 20px;">
            <a href="{COUPANG_URL}" target="_blank" style="
                display: inline-block;
                padding: 12px 35px;
                background-color: #3d3d3d;
                color: #ffffff;
                text-decoration: none;
                font-weight: 600;
                font-size: 16px;
                border-radius: 8px;
                border: 1px solid #2d2d2d;
                transition: background 0.3s ease;
            ">🎁 행운을 주는 물건 확인하기</a>
            <p style="font-size: 11px; color: #888; margin-top: 10px;">
                이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
            </p>
        </div>
    """, unsafe_allow_html=True)

st.caption("© 2026 서영식 사주&처세 정밀 분석")