import streamlit as st
import google.generativeai as genai
import datetime

# 1. 전역 변수 초기화 및 모델 설정 (NameError 원천 차단)
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [설정] 쿠팡 파트너스 링크 (본인의 링크로 수정)
COUPANG_URL = "https://link.coupang.com/a/din5aa" 

# 세션 상태 초기화
if 'unlocked' not in st.session_state:
    st.session_state.unlocked = False
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'step' not in st.session_state:
    st.session_state.step = 0 # 0: 분석 전, 1: 방문 전(링크만), 2: 방문 후(확인만)

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
            with st.spinner("분석 중..."):
                st.session_state.unlocked = False
                st.session_state.step = 1 # 분석 직후 1단계(링크만 노출)로 설정
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
                    st.error(f"오류: {e}")

# 3. 결과 출력 및 1버튼 순차 노출 (격리 로직)
if st.session_state.full_report:
    report = st.session_state.full_report
    # ValueError 방지: 구분선이 없을 경우 대비
    if "---잠금구분선---" in report:
        top_part, bottom_part = report.split("---잠금구분선---", 1)
    else:
        top_part, bottom_part = report, "상세 내용을 불러오지 못했습니다. 다시 생성해 주세요."

    st.divider()
    st.markdown(top_part) # 상단 요약은 상시 노출

    # === 버튼 격리 섹션: if-elif 구조로 동시 노출 절대 불가 ===
    if not st.session_state.unlocked:
        st.write("---")
        
        # [상태 1] step이 1일 때: 오직 HTML 링크만 표시
        if st.session_state.step == 1:
            st.warning("🔒 상세 운세와 고민 해답이 잠겨 있습니다.")
            # 요청하신 HTML 방식의 큰 레드 링크 박스
            st.markdown(f"""
                <div style="text-align: center; padding: 20px; border: 3px solid #ff4b4b; border-radius: 15px;">
                    <p style="margin-bottom: 15px; font-weight: bold; font-size: 18px;">🧧 아래 링크를 클릭하여 쿠팡을 방문해 주세요.</p>
                    <a href="{COUPANG_URL}" target="_blank" style="
                        display: inline-block; padding: 18px 40px; background-color: #ff4b4b; 
                        color: white; text-decoration: none; font-weight: bold; font-size: 20px; border-radius: 10px;
                    ">🚀 쿠팡 방문하고 상세운세 풀기</a>
                    <p style="margin-top: 15px; font-size: 14px; color: #666;">(클릭하면 새 창에서 쿠팡이 열립니다)</p>
                </div>
            """, unsafe_allow_html=True)
            
            st.write("")
            # 링크 클릭 후 이 버튼을 누르면 링크가 사라지고 다음 버튼이 나타남
            if st.button("🧧 위 링크를 클릭하여 페이지를 열었습니다 (다음으로)"):
                st.session_state.step = 2
                st.rerun()

        # [상태 2] step이 2일 때: 오직 확인 버튼만 표시 (1단계 링크는 사라짐)
        elif st.session_state.step == 2:
            st.info("✅ 방문이 완료되었습니다. 아래 버튼을 눌러 리포트를 완성하세요.")
            if st.button("🔓 2단계: 전체 결과 확인하기 (잠금 해제)", type="primary", use_container_width=True):
                st.session_state.unlocked = True
                st.rerun()
            
            if st.button("◀ 방문 링크 다시 보기 (단계 리셋)"):
                st.session_state.step = 1
                st.rerun()

        st.caption("이 서비스는 쿠팡 파트너스 활동의 일환으로 쿠팡으로부터 일정액의 수수료를 제공 받습니다.")
    
    else:
        # [상태 3] 잠금 해제 완료: 모든 상세 내용 표시
        st.success("🔓 모든 잠금이 해제되었습니다.")
        st.markdown(bottom_part)
        st.caption("이 서비스는 쿠팡 파트너스 활동의 일환으로 쿠팡으로부터 일정액의 수수료를 제공 받습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석")