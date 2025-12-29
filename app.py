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

# [설정] 사용자님의 고유 쿠팡 파트너스 링크
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""

# 페이지 설정 및 UI 숨기기 설정
st.set_page_config(page_title="2026 사주&처세 정밀 분석", layout="centered")

# --- Streamlit 기본 메뉴 및 헤더/푸터 숨기기 CSS ---
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
            with st.spinner("만세력을 정밀하게 분석하여 운명의 흐름을 읽고 있습니다..."):
                birth_date_str = f"{year}년 {month}월 {day}일"
                birth_time_str = birth_time.strftime("%H시 %M분")
                
                # 전문성 강화 및 '(가정)' 키워드 금지 지시
                prompt = f"""
                당신은 30년 경력의 정통 명리학자입니다. 
                사용자 정보: {user_name}, {gender}, {birth_date_str}({calendar_type}), {birth_time_str}, MBTI {user_mbti}.

                [절대 준수 지침]
                1. 출생 정보가 명확하므로 '가정', '추측', '정보 부족', '제외합니다' 등의 면피용 표현을 절대 사용하지 마세요. 
                2. 철저히 '십성', '용신', '오행의 조후' 등 명리학적 근거로만 확신에 찬 어조로 답변하세요.
                3. 전체 내용을 하나의 완성된 리포트로 작성하세요.

                [리포트 필수 구조]
                1. 📋 **사주 원국 분석**: 일간의 특징과 오행의 생극제화 분석 (전문 용어 사용)
                2. 🏮 **2026년 병오년(丙午年) 총평**: 세운의 천간과 지지가 주는 핵심 운세 분석
                3. 📊 **영역별 정밀 처세**: 재물운, 명예운, 건강운, 인간관계에 대한 사주적 조언
                4. ✨ **2026 행운을 주는 물건**: 
                   사주상 부족한 기운을 보완할 '가볍게 휴대 가능한 소품' 3가지를 추천하고 그 이유를 명리학적으로 설명하세요.
                """
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"분석 중 오류: {e}")

# 3. 결과 출력
if st.session_state.full_report:
    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 정밀 운명 리포트")
    st.markdown(st.session_state.full_report)
    
    # 쿠팡 파트너스 최적화 디자인
    st.write("")
    st.markdown(f"""
        <div style="text-align: center; margin-top: 25px; padding: 20px; border-top: 1px solid #eee;">
            <p style="font-size: 15px; color: #444; margin-bottom: 12px; font-weight: 500;">
                ✨ 리포트에서 추천된 '행운의 아이템'을 확인해보세요.
            </p>
            <a href="{COUPANG_URL}" target="_blank" style="
                display: inline-block; padding: 12px 35px; background-color: #4a4a4a; 
                color: white; text-decoration: none; font-weight: bold; font-size: 15px; border-radius: 6px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            ">🛍️ 행운을 주는 물건 보기</a>
            <p style="font-size: 12px; color: #999; margin-top: 15px;">
                이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
            </p>
        </div>
    """, unsafe_allow_html=True)

st.caption("© 2026 진담 사주&처세 정밀 분석")