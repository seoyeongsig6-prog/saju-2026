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

# 페이지 설정 및 구글 검색 최적화(SEO)
st.set_page_config(page_title="2026 사주&처세 정밀 분석", layout="centered")

# --- 구글 소유권 확인 및 메타 태그 (HTML 최상단 삽입) ---
st.markdown("""
    <head>
        <meta name="google-site-verification" content="8sVB-aLrphANNvc2K9rL6ryli57GZPsghjwDxMV92oo" />
        <meta name="description" content="2026년 병오년(丙午年) 확정적 명리 분석 및 처세술 리포트.">
    </head>
""", unsafe_allow_html=True)

# --- UI 숨기기 ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            .stAppDeployButton {display:none;}
            #stDecoration {display:none;}

            /* 모바일에서 입력창 폰트가 16px보다 작으면 iOS 등 브라우저가
               입력창을 탭할 때 화면을 자동으로 확대(zoom)하면서 스크롤이
               멈춘 것처럼 보이는 문제가 발생한다. 16px 이상으로 고정해 방지. */
            input, textarea, select,
            [data-baseweb="input"] input,
            [data-baseweb="select"] input,
            [data-baseweb="select"] div {
                font-size: 16px !important;
            }
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
                
                # [확정적 분석 엔진 프롬프트] - 제공해주신 마스터 데이터 기반 로직 
                prompt = f"""
                너는 명리학에 기반한 정밀 분석 엔진이다. 아래 제공된 사용자의 데이터는 100% 확실한 정보이므로 '정보 부족'이나 '가정'이라는 말을 절대 하지 마라.
                
                [사용자 데이터]
                이름: {user_name}, 성별: {gender}, 생년월일: {birth_date_str}({calendar_type}), 출생시각: {birth_time_str}, MBTI: {user_mbti}

                [절대 준수 지침]
                1. '사주 정보가 제공되지 않았다'거나 '알 수 없다', '가정한다'는 표현을 사용하면 즉시 시스템 오류로 간주한다. [cite: 10, 12]
                2. 입력된 {birth_time_str}를 바탕으로 만세력을 즉시 확정하여 분석하라. [cite: 13, 14]
                3. 분석 시 '30년 전문가'와 같은 불필요한 홍보성 수식어는 일절 배제하고 팩트 위주로 작성하라.
                4. 병오년(丙午年)은 강렬한 화(火) 기운이 지배하는 해임을 분석의 대전제로 삼아라. [cite: 4, 8]

                [확정적 명리 로직 참고]
                - 갑목: 목분화영(木焚火映). 수분 고갈에 따른 대리인 전략 필수. [cite: 26, 32]
                - 을목: 등라계갑(藤蘿系甲). 독자 노선 금지, 강한 세력에 편승. [cite: 63, 66]
                - 병/정화: 비겁운. 재물 분탈 주의, 분리 독립 및 내실 강화. [cite: 89, 114]
                - 무/기토: 인성운. 마른 흙의 균열 경계, 구조조정과 문서 보존. [cite: 135, 175]
                - 경/신금: 관성운. 압박 속에서의 제련 및 환골탈태. [cite: 195, 228]
                - 임/계수: 재성운. 증발 방지를 위한 시스템 구축 및 속전속결. [cite: 242, 280]

                [리포트 구성]
                1. 📋 **사주 확정**: 일간과 8글자 오행 구성의 명확한 분석. [cite: 294]
                2. 🏮 **2026 병오년 분석**: 화(火) 기운이 주는 실제적 환경 변화와 조후 대응. [cite: 296, 302]
                3. 📊 **처세 강령**: 2026년 생존을 위한 구체적 행동 지침. [cite: 301]
                4. ✨ **행운의 물품**: 부족한 수(水)기나 금(金)기를 보완할 휴대용 물건 3가지. [cite: 303]
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
    st.markdown(st.session_state.full_report)
    
    # 쿠팡 파트너스 UI
    st.markdown(f"""
        <div style="text-align: center; margin-top: 25px; padding: 20px; border-top: 1px solid #eee;">
            <p style="font-size: 15px; color: #444; margin-bottom: 12px; font-weight: 500;">
                ✨ 리포트 추천 행운 아이템 확인하기
            </p>
            <a href="{COUPANG_URL}" target="_blank" style="
                display: inline-block; padding: 10px 30px; background-color: #3d3d3d; 
                color: white; text-decoration: none; font-weight: bold; font-size: 15px; border-radius: 6px;
            ">🛍️ 아이템 확인하기</a>
            <p style="font-size: 12px; color: #999; margin-top: 15px;">
                이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
            </p>
        </div>
    """, unsafe_allow_html=True)

st.caption("© 2026 서영식 사주&처세 정밀 분석")