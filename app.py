import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 설정 (보안을 위해 Secrets 권장, 로컬 테스트 시에는 직접 입력 가능)
# 웹 배포 시에는 Streamlit Cloud의 Secrets에 GEMINI_API_KEY를 꼭 넣어주세요.
def init_model():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["AIzaSyBdlzoJ4h_HZ-7LBZbTEnoal8zXQye5Qbo"]
        else:
            # 로컬 테스트용: Secrets가 없을 때만 아래에 직접 키를 넣으세요.
            # 주의: GitHub에 올릴 때는 이 부분을 비우거나 Secrets를 사용하세요.
            api_key = "발급받은_새로운_API_키" 
        
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-2.0-flash')
    except Exception:
        return None

model = init_model()

# 앱 환경 설정
st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")
st.write("병오년(丙午年)의 기운을 읽어 당신의 삶에 가장 현실적인 방책을 제시합니다.")

# 2. 사용자 입력 섹션 (100% 한글 날짜 선택기)
with st.form("fortune_form"):
    user_name = st.text_input("성함", placeholder="필히 본명을 써주세요.")
    
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

    submit_button = st.form_submit_button("2026년 운명 리포트 생성")

# 3. 분석 및 결과 출력
if submit_button:
    if not user_name:
        st.error("성함을 입력해 주세요.")
    elif model is None:
        st.error("API 키 설정이 올바르지 않습니다. 관리자 설정을 확인해 주세요.")
    else:
        with st.spinner("하늘의 기운을 읽고 있습니다..."):
            birth_date_str = f"{year}년 {month}월 {day}일"
            prompt = f"전문 역술가로서 2026년 {user_name}님의 사주와 성향({user_mbti})을 분석해줘. 생일은 {birth_date_str}({calendar_type})이며 {gender}야. 삼재 여부와 행운의 달, 방위를 포함해서 상세히 알려줘. 자기소개는 생략해."

            try:
                response = model.generate_content(prompt)
                st.divider()
                st.markdown(f"### 📜 2026 {user_name}님의 사주와 처세")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"분석 중 오류가 발생했습니다: {e}")

st.caption("© 2026 서영식 사주&처세 융합 분석")