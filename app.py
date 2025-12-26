import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 최신 모델 설정
try:
    API_KEY = st.secrets["AIzaSyBwVil9UWKJYSI5phwKaAJ8j8F_LVoCmno"]
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("API 키 설정이 필요합니다. Streamlit Cloud의 Secrets 설정을 확인해 주세요."

# 앱 환경 설정
st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")
st.write("병오년(丙午年)의 기운을 읽어 당신의 삶에 가장 현실적인 방책을 제시합니다.")

# 2. 사용자 입력 섹션
with st.form("fortune_form"):
    user_name = st.text_input("성함", placeholder="필히 본명을 써주세요.")
    
    col1, col2 = st.columns(2)
    with col1:
        birth_date = st.date_input(
            "생년월일", 
            value=datetime.date(1995, 1, 1),
            min_value=datetime.date(1900, 1, 1),
            max_value=datetime.date(2026, 12, 31)
        )
        calendar_type = st.radio("날짜 구분", ["양력", "음력"], horizontal=True)
        
    with col2:
        birth_time = st.time_input("출생 시각", value=datetime.time(12, 0))
        gender = st.radio("성별", ["남성", "여성"], horizontal=True)
    
    st.divider()
    
    user_mbti = st.selectbox("당신의 성향(MBTI)", [
        "ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
        "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"
    ])

    submit_button = st.form_submit_button("2026년 운명 리포트 생성")

# 3. 분석 및 결과 출력
if submit_button:
    if not user_name:
        st.error("성함을 입력해 주세요.")
    else:
        with st.spinner("하늘의 기운과 땅의 흐름을 읽고 있습니다..."):
            korean_date = birth_date.strftime('%Y년 %m월 %d일')
            
            # 고도화된 프롬프트
            prompt = f"""
            당신은 전통 명리학의 정수를 통달한 역술가입니다. 2026년 병오년(丙午年)의 강한 불(火)의 기운과 
            사용자의 사주, 그리고 성향({user_mbti})을 심층 분석하여 리포트를 작성하세요.

            [사용자 데이터]
            - 성함: {user_name}
            - 생일: {korean_date} ({calendar_type})
            - 시간: {birth_time}
            - 성별: {gender}
            - MBTI: {user_mbti}

            [작성 필수 지침]
            1. 절대 자기소개(예: 30년 경력 등)를 하지 마세요. 인사말 후 바로 분석에 들어갑니다.
            2. 톤앤매너: 전문 역술인의 무게감과 신뢰감을 유지하되, 지친 현대인에게 따뜻한 위로와 용기를 주는 어조를 사용하세요.
            3. MBTI 처리: 상단 분석 섹션 외의 본문에서는 'MBTI'라는 단어를 직접 쓰지 말고, {user_mbti}의 특징을 사주 풀이에 자연스럽게 녹여내세요.
            4. 삼재 체크: 사용자의 출생 연도(띠)를 기준으로 2026년이 삼재(들삼재, 눌삼재, 날삼재)에 해당하는지 반드시 판별하여 언급하세요.

            [결과 구조 및 목차]
            제목: "2026 {user_name}님의 사주와 처세"

            [상단 요약 분석]
            - **사주 분석**: 타고난 사주 원국의 핵심 기운과 특징을 짧고 굵게 요약.
            - **MBTI 분석**: {user_mbti} 성향이 가진 기질적 장단점을 짧게 요약.

            [본문 상세 분석]
            1. 통합분석: 사주의 기운과 성향 기질이 병오년의 기운과 만나 일으키는 전체적인 흐름.
            2. 2026년 사주: 올해 마주할 결정적인 운명적 변곡점.
            3. 2026년 사업/직장운: 사업과 직장의 운과 체세법.
            4. 2026년 재물운: 재산의 증식, 투자, 소득의 흐름에 대한 전문적 조언.
            5. 2026년 인간관계운: 주변인과의 갈등 관리 및 인덕을 쌓는 처세술.
            6. 2026년 사랑운: 인연의 만남과 유지, 깊어지는 정에 대한 지침.

            [실전 처세 지침]
            - **올해 귀한 것과 피해야 할 것**: 운을 돋우는 습관/물건과 운을 깎아먹는 행동/환경에 대한 조언. (삼재 여부 포함)
            - **행운의 시기**: 2026년 중 가장 기운이 좋은 달(月)들을 명시하고 이유 설명.
            - **방위(方向) 가이드**: 동, 서, 남, 북 중 이동이나 계약에 길한 방향과 절대 경계해야 할 방향 제시.
            """

            try:
                response = model.generate_content(prompt)
                st.divider()
                st.markdown(response.text)
                
            except Exception as e:
                if "429" in str(e):
                    st.error("🚨 현재 요청이 집중되고 있습니다. 약 1분 후 다시 리포트를 생성해 주세요.")
                else:
                    st.error(f"오류가 발생했습니다: {e}")

st.caption("© 2026 서영식 사주&처세 융합 분석 - 이 분석은 삶의 지혜를 더하는 참고용 지침서입니다.")