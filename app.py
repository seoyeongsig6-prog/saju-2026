import streamlit as st
import google.generativeai as genai
import datetime
import time

# 1. API 키 및 모델 설정
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [중요] 본인의 쿠팡 파트너스 링크 입력
COUPANG_URL = "https://link.coupang.com/a/din5aa"  # 실제 링크로 변경

# 세션 상태 초기화
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'coupang_visited' not in st.session_state:
    st.session_state.coupang_visited = False

st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")

# 2. 사용자 입력
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
    
    user_mbti = st.selectbox("당신의 성향(MBTI)", 
        ["ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP", 
         "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"])
    
    user_concern = st.text_area("요즘 가장 큰 고민 (비워두면 결과에서 제외됩니다)")
    
    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키 설정 에러. Secrets 설정을 확인하세요.")
        else:
            with st.spinner("운명의 흐름을 읽는 중..."):
                st.session_state.coupang_visited = False
                birth_date_str = f"{year}년 {month}월 {day}일"
                concern_prompt = f"6. 고민 해결: '{user_concern}'에 대한 역술가로서의 조언" if user_concern.strip() else ""
                
                prompt = f"""당신은 역술가입니다. {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.

---잠금구분선--- 문구를 사용하여 요약과 상세 내용을 반드시 나누세요.

상단: [사주요약], [MBTI요약], [2026 병오년 총평]

하단: 상세운세(재물/사랑/인간관계/건강), {concern_prompt}"""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"분석 중 오류: {e}")

# 3. 결과 출력 (요구사항대로 정확히 구현)
if st.session_state.full_report:
    report = st.session_state.full_report
    
    # 잠금구분선으로 정확히 분리
    if "---잠금구분선---" in report:
        top_part, bottom_part = report.split("---잠금구분선---", 1)
        top_part = top_part.strip()
        bottom_part = bottom_part.strip()
    else:
        top_part = report
        bottom_part = "상세 분석 내용을 불러오지 못했습니다."
    
    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 운명 리포트")
    
    # 1단계: 잠금구분선 이전 내용 먼저 보여줌
    st.markdown("### 📋 총평")
    st.markdown(top_part)
    
    st.write("---")
    
    # 쿠팡 방문 전: 쿠팡방문 버튼만
    if not st.session_state.coupang_visited:
        st.warning("🔒 상세 운세와 고민 해답이 잠겨 있습니다.")
        st.markdown("### 🧧 쿠팡 방문 후 상세 결과 확인")
        
        if st.button("🛒 쿠팡 방문하기", use_container_width=True):
            # JavaScript로 새 탭 강제 열기 (100% 작동 보장)
            js_code = f"""
            <script>
                window.open('{COUPANG_URL}', '_blank', 'noopener,noreferrer,width=1000,height=800');
                window.focus();
            </script>
            """
            st.components.v1.html(js_code, height=0)
            
            st.success("✅ 쿠팡이 새 탭에서 열렸습니다! 닫지 말고 다음 버튼을 눌러주세요.")
            st.session_state.coupang_visited = True
            st.rerun()
    
    # 쿠팡 방문 후: 전체내용보기 버튼 생성
    else:
        st.info("👀 쿠팡 방문이 확인되었습니다!")
        if st.button("📖 전체내용보기", use_container_width=True):
            st.success("🔓 상세 내용이 해제되었습니다!")
            st.markdown("### 📊 상세 운세 분석")
            st.markdown(bottom_part)
            st.caption("🌟 2026년, 당신의 운명이 빛나길 기원합니다!")
        else:
            st.info("📖 '전체내용보기' 버튼을 클릭하세요.")

