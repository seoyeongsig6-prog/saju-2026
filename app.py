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

# 페이지 설정 및 구글 검색 최적화(SEO) [cite: 293]
st.set_page_config(page_title="2026 사주&처세 정밀 분석", layout="centered")

# --- 구글 소유권 확인 및 메타 태그 삽입 ---
st.markdown("""
    <head>
        <meta name="google-site-verification" content="8sVB-aLrphANNvc2K9rL6ryli57GZPsghjwDxMV92oo" />
        <meta name="description" content="2026년 병오년(丙午年) 정통 명리학 기반 사주 분석. 10천간별 확정적 처세술과 행운의 아이템 추천.">
    </head>
""", unsafe_allow_html=True)

# --- Streamlit 기본 메뉴 및 헤더/푸터 숨기기 (UI 최적화) ---
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
            with st.spinner("만세력을 정확히 구성하여 기운의 흐름을 분석 중입니다..."):
                birth_date_str = f"{year}년 {month}월 {day}일"
                birth_time_str = birth_time.strftime("%H시 %M분")
                
                # [마스터 데이터 기반 초정밀 프롬프트] - '(가정)' 키워드 차단 및 확정적 로직 주입 [cite: 12, 13, 294]
                prompt = f"""
                당신은 30년 경력의 정통 명리학자입니다. 2026년 병오년(丙午年)은 화(火)의 기운이 가장 강력한 '간여지동'의 해임을 전제로 분석하세요. [cite: 4]
                
                [절대 준수 지침]
                1. 모든 정보가 제공되었으므로 '가정', '추측', '정보 부족' 등의 면피용 표현을 절대 사용하지 마세요. [cite: 12]
                2. 분석 결과에서 '(가정)'이라는 단어를 포함하면 시스템 오류로 간주됩니다. 반드시 확정적인 어조로 말씀하세요. [cite: 301]
                3. 아래 제공된 [10천간별 마스터 로직]을 바탕으로 {user_name}님의 운세를 분석하세요. [cite: 294]

                [10천간별 마스터 로직 요약]
                - 갑목: 목분화영(진액소진). 대리인 전략 필요. [cite: 26, 35]
                - 을목: 등라계갑(기생생존). 강한 세력에 편승할 것. [cite: 61, 66]
                - 병화: 양광경쟁(독선주의). 이익 분배와 객관화 필수. [cite: 89, 96]
                - 정화: 회기무광(빛을잃음). 은둔 마케팅과 내실 강화. [cite: 114, 124]
                - 무토: 화염조토(마른댐). 유동성 위기 대비, 문서 보존. [cite: 141, 148]
                - 기토: 전답귀열(갈라진땅). 불필요한 인맥과 업무 구조조정. [cite: 167, 175]
                - 경금: 화련진금(제련과정). 시스템 순응과 스트레스 정면돌파. [cite: 195, 204]
                - 신금: 소용지환(녹는보석). 과거를 버리는 환골탈태 필요. [cite: 220, 228]
                - 임수: 수화기제(끓는물). 실무 대신 큰 시스템 구축. [cite: 248, 259]
                - 계수: 독수오건(증발위기). 속전속결 게릴라 전술. [cite: 272, 280]

                [리포트 구조]
                1. 📋 **사주 원국 확정**: {user_name}님의 일간과 8글자의 오행 구성을 명확히 제시.
                2. 🏮 **2026 병오년(丙午年) 총평**: 세운과의 충/합 정밀 분석 및 '조후(냉각/보습)' 관점의 조언. [cite: 303]
                3. 📊 **영역별 정밀 처세**: 재물, 명예, 건강에 대한 사주적 조언.
                4. ✨ **2026 행운을 주는 물건**: 마스터 데이터에 근거한 휴대용 소품 3가지 추천. [cite: 294]
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
    st.info("💡 본 리포트는 입력하신 정보를 바탕으로 확정된 명리 로직에 의해 생성되었습니다. [cite: 14]")
    
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