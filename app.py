import streamlit as st
import google.generativeai as genai
import datetime

# 1. API 키 및 모델 초기화 (NameError 방지)
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [설정] 본인의 쿠팡 파트너스 링크 입력
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화 (단계별 제어 로직)
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'step' not in st.session_state:
    st.session_state.step = 0  # 0: 분석 전, 1: 방문 버튼, 2: 확인 버튼, 3: 완료

st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")

# 2. 사용자 입력 섹션
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
    user_concern = st.text_area("요즘 가장 큰 고민 (비워두면 결과에서 제외)")

    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정 에러. Secrets를 확인하세요.")
        else:
            with st.spinner("운명의 흐름을 읽는 중..."):
                st.session_state.step = 1 # 분석 직후 1단계 진입
                birth_date_str = f"{year}년 {month}월 {day}일"
                concern_prompt = f"6. 고민 해결: '{user_concern}'에 대한 조언" if user_concern.strip() else ""
                
                prompt = f"""당신은 역술가입니다. {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
---잠금구분선--- 문구를 사용하여 요약과 상세 내용을 반드시 나누세요.
상단: [사주요약], [MBTI요약], [2026 병오년 총평]
하단: 상세운세(재물/사랑/인간관계/건강), {concern_prompt}"""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"분석 중 오류: {e}")

# 3. 결과 출력 및 [순차 노출] 버튼 로직 (중복 노출 절대 불가)
if st.session_state.full_report:
    report = st.session_state.full_report
    # 구분선으로 상/하단 분리
    if "---잠금구분선---" in report:
        top_part, bottom_part = report.split("---잠금구분선---", 1)
    else:
        top_part, bottom_part = report, "상세 분석 내용을 불러오지 못했습니다."

    st.divider()
    st.markdown(f"## 📜 운명 리포트")
    st.markdown(top_part)

    # === 버튼 로직: if-elif 구조로 각 단계당 딱 1개의 UI만 노출 ===
    
    # [1단계] 쿠팡 방문 버튼: 클릭 시 새 창 열기 + 다음 단계 버튼으로 교체
    if st.session_state.step == 1:
        st.write("---")
        st.warning("🔒 상세 분석 결과가 잠겨 있습니다.")
        st.markdown("### 🧧 쿠팡 방문 후 상세 결과 확인")
        
        # 브라우저 팝업 차단을 피하기 위해 HTML <a> 태그를 버튼처럼 스타일링
        st.markdown(f"""
            <div style="text-align: center; margin: 20px 0;">
                <a href="{COUPANG_URL}" target="_blank" style="
                    display: inline-block; width: 100%; padding: 15px 0; background-color: #ff4b4b; 
                    color: white; text-decoration: none; font-weight: bold; font-size: 18px; 
                    border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.2);
                ">🚀 1단계: 쿠팡 방문하기 (새 창 열림)</a>
            </div>
            """, unsafe_allow_html=True)
        
        # 위 링크를 클릭한 사용자가 돌아와서 누를 버튼 (이걸 눌러야 1단계가 사라짐)
        if st.button("🧧 쿠팡 페이지를 열었습니다 (다음으로)", use_container_width=True):
            st.session_state.step = 2
            st.rerun()

    # [2단계] 확인 및 잠금 해제 버튼
    elif st.session_state.step == 2:
        st.write("---")
        st.info("✅ 방문이 완료되었다면 아래 버튼을 눌러 상세 운세를 확인하세요.")
        if st.button("🔓 2단계: 결과 확인하기 (잠금 해제)", use_container_width=True, type="primary"):
            st.session_state.step = 3
            st.rerun()

    # [3단계] 최종 완료: 버튼이 모두 사라지고 상세 내용 노출
    elif st.session_state.step == 3:
        st.write("---")
        st.success("🎉 모든 잠금이 해제되었습니다.")
        st.markdown(bottom_part)
        st.caption("이 서비스는 쿠팡 파트너스 활동의 일환으로 쿠팡으로부터 일정액의 수수료를 제공 받습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석")