import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 모델 초기화 (에러 방지용 최상단 선언)
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
            with st.spinner("만세력을 정확히 구성하여 기운의 흐름을 분석 중입니다..."):
                birth_date_str = f"{year}년 {month}월 {day}일"
                # 시간 정보가 누락되지 않도록 프롬프트에 명시
                birth_time_str = birth_time.strftime("%H시 %M분")
                concern_prompt = f"### 💡 고민 해결 처세술\n'{user_concern}'에 대한 명리학적 해법을 제시하세요." if user_concern.strip() else ""
                
                # 전문성 강화 및 '(가정)' 키워드 금지 지시
                prompt = f"""
                당신은 30년 경력의 정통 명리학자입니다. 
                사용자 정보: {user_name}, {gender}, 생년월일 {birth_date_str}({calendar_type}), 출생시간 {birth_time_str}, MBTI {user_mbti}.

                [절대 준수 지침]
                1. 모든 정보(특히 출생시간)가 제공되었으므로 '정보 부족', '추측', '가정' 등의 단어를 절대 사용하지 마세요.
                2. 전문적인 만세력 분석을 기반으로 '일간', '용신', '십성', '합형충파해' 용어를 사용하여 깊이 있게 설명하세요.
                3. 답변 중간에 반드시 '---잠금구분선---'이라는 문구를 한 번만 포함하여 요약과 상세 내용을 나누세요.

                [리포트 구성]
                (구분선 이전)
                - 사주 원국 분석 (일간과 오행 구성)
                - 2026 병오년 총평
                ---잠금구분선---
                (구분선 이후)
                - 재물/사랑/인간관계 정밀 분석
                {concern_prompt}
                - ✨ 2026 행운을 주는 물건: 사용자의 기운을 보완할 작은 휴대용 소품 3가지 추천과 명리학적 근거.
                """
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류: {e}")

# 3. 결과 출력 및 UI 개선
if st.session_state.full_report:
    report = st.session_state.full_report
    # ValueError 방지를 위한 안전한 분할 로직
    if "---잠금구분선---" in report:
        top_part, bottom_part = report.split("---잠금구분선---", 1)
    else:
        top_part, bottom_part = report, "상세 분석 내용을 생성 중 오류가 발생했습니다. 다시 시도해 주세요."

    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 정밀 운명 리포트")
    st.markdown(top_part)
    st.markdown(bottom_part)
    
    # 쿠팡 파트너스 섹션 강조 디자인
    st.write("")
    st.markdown(f"""
        <div style="text-align: center; margin-top: 30px; padding: 20px; border: 1px solid #e6e6e6; border-radius: 15px; background-color: #fcfcfc;">
            <p style="font-size: 16px; font-weight: bold; color: #333; margin-bottom: 15px;">🔮 나에게 행운을 가져다줄 아이템 확인하기</p>
            <a href="{COUPANG_URL}" target="_blank" style="
                display: inline-block; padding: 12px 40px; background-color: #ff4b4b; 
                color: white; text-decoration: none; font-weight: bold; font-size: 16px; border-radius: 8px;
            ">🎁 행운의 아이템 보러가기</a>
            <p style="font-size: 12px; color: #888; margin-top: 15px; line-height: 1.5;">
                이 포스팅은 쿠팡 파트너스 활동의 일환으로,<br>이에 따른 일정액의 수수료를 제공받습니다.
            </p>
        </div>
    """, unsafe_allow_html=True)

st.caption("© 2026 서영식 사주&처세 정밀 분석")