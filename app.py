import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 설정 (보안을 위해 Streamlit Secrets 사용)
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
    else:
        model = None
except Exception:
    model = None

# 앱 환경 설정
st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")
st.write("병오년(丙午年)의 기운과 당신의 성향을 읽어 삶의 가장 현실적인 방책을 제시합니다.")

# 2. 사용자 입력 섹션
with st.form("fortune_form"):
    user_name = st.text_input("성함", placeholder="본명을 입력해 주시면 더 정확합니다.")
    
    st.write("### 생년월일 선택")
    col_y, col_m, col_d = st.columns(3)
    with col_y:
        year = st.selectbox("년", range(2026, 1919, -1), index=31) # 기본값 1995년
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
    
    user_mbti = st.selectbox("당신의 성향(MBTI)", [
        "ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"
    ])

    # [신규] 고민 상담 입력창
    user_concern = st.text_area("고민이나 묻고 싶은 점을 상세히 쓰세요.", placeholder="예: 이직을 하고 싶은데 괜찮을까요? / 올해는 연애운이 있을까요?")

    submit_button = st.form_submit_button("2026년 운명 리포트 생성")

# 3. 분석 및 결과 출력
if submit_button:
    if not user_name:
        st.error("성함을 입력해 주세요.")
    elif model is None:
        st.error("API 키 설정이 올바르지 않습니다. 관리자 설정(Secrets)을 확인해 주세요.")
    else:
        with st.spinner("하늘의 기운과 당신의 마음을 읽고 있습니다..."):
            birth_date_str = f"{year}년 {month}월 {day}일"
            
            # 정교화된 전문가 프롬프트
            prompt = f"""
            당신은 전통 명리학과 현대 심리학에 통달한 역술가입니다. 2026년 {user_name}님의 사주와 성향({user_mbti})을 심층 분석하세요.

            [사용자 데이터]
            - 성함: {user_name}
            - 생일: {birth_date_str}({calendar_type}), 시간: {birth_time}
            - 성별: {gender}
            - MBTI: {user_mbti}
            - 현재 고민: {user_concern if user_concern else "특별히 언급 없음"}

            [작성 필수 지침]
            1. 절대 자기소개를 하지 마세요. 인사말 후 바로 분석 리포트 형식으로 출력합니다.
            2. 결과 최상단에 다음 두 섹션을 반드시 포함하세요:
               - [사주 요약]: 사용자의 선천적 운의 특징을 2~3줄로 정리.
               - [MBTI 요약]: {user_mbti} 성향이 삶의 처세에 미치는 영향을 2~3줄로 정리.
            3. 그 아래에 "2026 병오년 총평"을 큰 제목으로 작성하세요.
            4. 상세 분석 항목은 다음과 같습니다:
               1. 통합분석 / 2. 2026년 사주 / 3. 재물운 / 4. 인간관계운 / 5. 사랑운 / 6. 건강운(신규)
            5. 반드시 포함할 내용: 2026년 삼재 여부, 행운의 달, 행운의 방위, 피해야 할 방위.
            6. [고민 상담 답변]: 사용자가 적은 "{user_concern}"에 대해 사주와 성향을 고려하여 역술가로서 매우 솔직하고 구체적인 조언을 리포트 마지막에 작성하세요.
            7. 따뜻하면서도 무게감 있는 전문가의 어조를 유지하세요.
            """

            try:
                response = model.generate_content(prompt)
                st.divider()
                st.markdown(f"## 📜 2026 {user_name}님의 운명 리포트")
                st.markdown(response.text)
                
            except Exception as e:
                st.error(f"분석 중 오류가 발생했습니다: {e}")

st.caption("© 2026 서영식 사주&처세 융합 분석")