import streamlit as st
import google.generativeai as genai
import datetime
import time

# 1. API 키 및 모델 초기화 (에러 방지를 위해 상단 배치)
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    model = None

# [설정] 본인의 쿠팡 파트너스 링크로 수정하세요
COUPANG_URL = "https://link.coupang.com/a/XXXXXX" 

# 세션 상태 초기화
if 'unlocked' not in st.session_state:
    st.session_state.unlocked = False
if 'full_report' not in st.session_state:
    st.session_state.full_report = ""
if 'show_check_button' not in st.session_state:
    st.session_state.show_check_button = False

# 앱 화면 설정
st.set_page_config(page_title="2026 사주&처세 융합 분석", layout="centered")
st.title("🏮 2026 사주&처세 융합 분석")

# 2. 사용자 정보 입력 섹션
with st.form("fortune_form"):
    user_name = st.text_input("성함", placeholder="본명을 입력해 주세요.")
    
    st.write("### 생년월일 선택 (한글)")
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
    user_concern = st.text_area("요즘 가장 큰 고민은 무엇인가요? (역술인에게 묻기)", placeholder="예: 이직, 재물, 연애 등 구체적일수록 좋습니다.")

    if st.form_submit_button("2026년 운명 리포트 생성"):
        if not user_name:
            st.error("성함을 입력해 주세요.")
        elif model is None:
            st.error("API 키가 설정되지 않았습니다. 관리자 설정(Secrets)을 확인해 주세요.")
        else:
            with st.spinner("하늘의 기운을 읽고 있습니다..."):
                # 초기화
                st.session_state.unlocked = False
                st.session_state.show_check_button = False
                birth_date_str = f"{year}년 {month}월 {day}일"
                
                prompt = f"""당신은 역술가입니다. {user_name}({user_mbti}, {gender}, {birth_date_str})의 2026년 운세를 분석하세요.
                내용은 다음 문구를 기준으로 상단과 하단을 정확히 나누세요: ---잠금구분선---
                상단에는 [사주요약], [MBTI요약], [2026 병오년 총평]을 쓰고,
                하단에는 상세운세(재물/사랑/인간관계/건강)와 사용자의 고민("{user_concern}")에 대한 솔직한 답변을 작성하세요."""
                
                try:
                    response = model.generate_content(prompt)
                    st.session_state.full_report = response.text
                except Exception as e:
                    st.error(f"분석 중 오류 발생: {e}")

# 3. 결과 출력 및 2단계 버튼 로직 (순차 노출)
if st.session_state.full_report:
    report = st.session_state.full_report
    top_part, bottom_part = report.split("---잠금구분선---") if "---잠금구분선---" in report else (report, "")

    st.divider()
    st.markdown(f"## 📜 {user_name}님의 2026년 운명 리포트")
    st.markdown(top_part) # 총평 요약 상시 노출

    if not st.session_state.unlocked:
        st.write("---")
        st.warning("🔒 **상세 분석 결과와 고민 해답이 잠겨 있습니다.**")
        
        # [단계 1] 방문하기 버튼만 먼저 보여줌
        if not st.session_state.show_check_button:
            st.write("👉 **1단계: 아래 버튼을 눌러 쇼핑몰을 잠시 방문해 주세요.**")
            # 이 버튼을 클릭하면 세션 상태가 변경되면서 화면이 다시 그려집니다.
            if st.button("🧧 쿠팡 방문하고 열쇠 받기"):
                st.session_state.show_check_button = True
                # 실제 쿠팡 링크를 새 창으로 열어줍니다.
                st.markdown(f'<meta http-equiv="refresh" content="0; url={COUPANG_URL}">', unsafe_allow_html=True)
                st.rerun()
        
        # [단계 2] 1단계를 거쳐야만 등장하는 확인 버튼
        else:
            st.info("✅ **2단계: 방문이 확인되었습니다. 마지막 버튼을 눌러 결과를 확인하세요.**")
            if st.button("🔓 전체 리포트 잠금 해제"):
                with st.status("방문 데이터 검증 중...", expanded=True) as status:
                    time.sleep(3)
                    status.update(label="확인 완료! 상세 분석을 공개합니다.", state="complete", expanded=False)
                st.session_state.unlocked = True
                st.rerun()
            
            if st.button("다시 방문하기"):
                st.session_state.show_check_button = False
                st.rerun()

        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")
    
    else:
        # 잠금 해제 후 모든 내용 출력
        st.success("🔓 잠금이 해제되었습니다. 상세 분석 결과를 확인하세요.")
        st.markdown(bottom_part)
        st.caption("이 서비스는 쿠팡파트너스 활동의 일환으로 쿠팡으로부터 이에 따른 일정액의 수수료를 제공 받습니다.")

st.caption("© 2026 서영식 사주&처세 융합 분석")