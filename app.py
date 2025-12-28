import streamlit as st
import google.generativeai as genai
import datetime
import streamlit.components.v1 as components

# 1. API 키 및 모델 초기화 (에러 방지용)
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [설정] 본인의 쿠팡 파트너스 링크
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 2. 쿼리 파라미터를 이용한 상태 관리 (버튼 클릭 감지)
if "clicked" in st.query_params:
    st.session_state.step = 2 # 클릭된 상태라면 바로 2단계로

if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'step' not in st.session_state:
    st.session_state.step = 0 # 0: 분석전, 1: 방문버튼, 2: 결과보기

st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")

# 3. 사용자 입력 섹션
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
    user_concern = st.text_area("요즘 고민 (비워두면 결과에서 제외)")

    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정 에러. Secrets를 확인하세요.")
        else:
            with st.spinner("분석 중..."):
                st.session_state.step = 1
                st.query_params.clear() # 이전 클릭 기록 삭제
                birth_date_str = f"{year}년 {month}월 {day}일"
                concern_prompt = f"6. 고민 해결: '{user_concern}'에 대한 조언" if user_concern.strip() else ""
                
                prompt = f"""역술가로서 {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
---잠금구분선--- 문구를 사용하여 요약과 상세 내용을 반드시 나누세요.
상단: [사주요약], [MBTI요약], [2026 병오년 총평]
하단: 상세운세(재물/사랑/인간관계/건강), {concern_prompt}"""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"오류: {e}")

# 4. 결과 출력 및 [원클릭] 순차 로직
if st.session_state.full_report:
    report = st.session_state.full_report
    top_part, bottom_part = report.split("---잠금구분선---", 1) if "---잠금구분선---" in report else (report, "")

    st.divider()
    st.markdown(f"## 📜 운명 리포트")
    st.markdown(top_part)

    # === 각 단계마다 '딱 하나'의 버튼만 노출 ===
    
    # [1단계] 쿠팡 방문 버튼: 클릭 시 즉시 쿠팡이 열리고 화면이 바뀜
    if st.session_state.step == 1:
        st.write("---")
        st.warning("🔒 상세 분석 결과가 잠겨 있습니다.")
        
        # HTML/JS 버튼: 새 창 열기 + 부모 창 쿼리 파라미터 변경
        button_html = f"""
        <div style="text-align: center;">
            <button id="coupang-btn" style="
                width: 100%; padding: 15px; background-color: #ff4b4b; color: white;
                border: none; border-radius: 10px; font-size: 18px; font-weight: bold; cursor: pointer;
            ">🚀 쿠팡 방문하고 상세운세 풀기</button>
        </div>
        <script>
            document.getElementById('coupang-btn').onclick = function() {{
                window.open('{COUPANG_URL}', '_blank');
                const url = new URL(window.parent.location.href);
                url.searchParams.set('clicked', 'true');
                window.parent.location.href = url.href;
            }};
        </script>
        """
        components.html(button_html, height=70)

    # [2단계] 확인 및 완료: 1단계 버튼은 사라지고 상세 내용 노출
    elif st.session_state.step == 2:
        st.write("---")
        st.success("🎉 방문이 확인되었습니다. 상세 분석 결과를 공개합니다.")
        st.markdown(bottom_part)
        
        if st.button("🧧 처음으로 돌아가기"):
            st.query_params.clear()
            st.session_state.step = 0
            st.rerun()

st.divider()
st.caption("이 서비스는 쿠팡 파트너스 활동의 일환으로 쿠팡으로부터 일정액의 수수료를 제공 받습니다.")