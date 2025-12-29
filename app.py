import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 모델 설정
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 페이지 설정 및 UI 숨기기
st.set_page_config(page_title="2026 사주&처세 정밀 분석", layout="centered")

# --- Streamlit 기본 메뉴 및 헤더/푸터 숨기기 (모바일 최적화) ---
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

if 'full_report' not in st.session_state:
    st.session_state.full_report = ""

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

    if st.form_submit_button("정밀 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정을 확인하세요.")
        else:
            with st.spinner("하늘의 기운을 수치화하여 정밀 분석 중입니다..."):
                birth_date_str = f"{year}년 {month}월 {day}일"
                birth_time_str = birth_time.strftime("%H시 %M분")
                
                # 데이터 일관성을 위한 초정밀 프롬프트
                prompt = f"""
                당신은 오차가 없는 정통 명리학자입니다. 
                대상자: {user_name}, {gender}, {birth_date_str}({calendar_type}), {birth_time_str}, MBTI {user_mbti}.

                [절대 준수 지침]
                1. 정확한 만세력 로직에 따라 연주/월주/일주/시주를 먼저 '확정'한 후 답변을 시작하세요. 
                2. 답변 도중 일간(日干)이나 오행의 비중이 바뀌면 안 됩니다. 한 번 정한 결과를 끝까지 유지하세요.
                3. '추측', '가정', '정보 부족' 등의 면피용 표현은 신뢰도를 떨어뜨리므로 절대 사용 금지입니다.
                4. 분석은 명리학 전문 용어(십성, 용신, 합형충파해)를 사용하여 논리적으로 서술하세요.

                [리포트 구조]
                1. 📋 **사주 원국 확정**: 일간(Day Master)과 8글자의 오행 구성을 명확히 제시
                2. 🏮 **2026 병오년(丙午年) 분석**: 세운과의 충/합 정밀 분석
                3. 📊 **재물/명예/건강 처세술**: 사주 기반의 실질적 조언
                4. ✨ **2026 행운을 주는 물건**: 
                   사주상 부족한 기운을 보완할 '휴대용 소품' 3가지 추천 (논리적 근거 포함)
                """
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                    st.session_state.target_name = user_name
                except Exception as e:
                    st.error(f"오류: {e}")

# 3. 결과 출력
if st.session_state.full_report:
    st.divider()
    st.markdown(f"## 📜 {st.session_state.target_name}님의 2026년 정밀 운명 리포트")
    
    # 사주 팔자의 구조를 시각적으로 이해하도록 돕는 문구
    st.info("💡 본 리포트는 입력하신 출생 시각을 바탕으로 사주 팔자(四柱八字)를 확정하여 분석되었습니다.")
    
    
    
    st.markdown(st.session_state.full_report)
    
    # 쿠팡 파트너스 최적화 UI
    st.markdown(f"""
        <div style="text-align: center; margin-top: 25px; padding: 20px; border-top: 1px solid #eee;">
            <p style="font-size: 15px; color: #444; margin-bottom: 12px; font-weight: 500;">
                ✨ 리포트에서 추천된 '행운의 아이템'을 확인해보세요.
            </p>
            <a href="{COUPANG_URL}" target="_blank" style="
                display: inline-block; padding: 12px 35px; background-color: #3d3d3d; 
                color: white; text-decoration: none; font-weight: bold; font-size: 15px; border-radius: 6px;
            ">🛍️ 행운을 주는 물건 보기</a>
            <p style="font-size: 11px; color: #999; margin-top: 15px;">
                이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
            </p>
        </div>
    """, unsafe_allow_html=True)

st.caption("© 2026 서영식 사주&처세 정밀 분석")