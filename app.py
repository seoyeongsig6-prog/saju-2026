import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET

# ==========================================
# 1. API 설정
# ==========================================
GEMINI_API_KEY = 'AIzaSyBCLFHYrG02HMQXIxX03gidfGW0d2qAzQs'
KIPRIS_SERVICE_KEY = 'dbd303eb405af70e751c6ee7760ca79f4d5089d2eea87bb73e18ca006f27f096'

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-2.0-flash')

# ==========================================
# 2. 핵심 로직: 단어 일치 여부 정밀 검증
# ==========================================
def verify_trademark_existence(tm_name):
    """
    특허청 서버에서 검색된 전체 결과 중 
    사용자가 입력한 단어가 포함되어 있는지 논리적으로 대조합니다.
    """
    url = 'https://kipo-api.kipi.or.kr/openapi/service/trademarkInfoSearchService/getTrademarkList'
    params = {
        'serviceKey': KIPRIS_SERVICE_KEY,
        'searchString': tm_name,
        'numOfRows': '100' # 넉넉하게 100건을 수신
    }
    
    try:
        # 1. 특허청 서버 접속 시도
        resp = requests.get(url, params=params, verify=True, timeout=20)
        if resp.status_code != 200:
            return None, f"특허청 서버 연결 실패 (코드: {resp.status_code})"
        
        # 2. 데이터 분석 (XML 파싱)
        root = ET.fromstring(resp.text)
        items = root.findall('.//item')
        
        # 3. 단어 대조 로직 (공백 및 대소문자 무시)
        matches = []
        clean_input = tm_name.replace(" ", "").upper()
        
        for item in items:
            title = item.findtext('title', "")
            clean_title = title.replace(" ", "").upper()
            
            # 💡 논리적 필터: 입력한 단어가 상표명에 포함되어 있는가?
            if clean_input in clean_title:
                matches.append({
                    "상표명": title,
                    "상태": item.findtext('applicationStatus', ""),
                    "분류(류)": item.findtext('classificationCode', ""),
                    "출원인": item.findtext('applicantName', "")
                })
        
        return matches, resp.text # 검색된 결과와 원본 로그 반환
    except Exception as e:
        return None, f"연결 오류: {str(e)}"

# ==========================================
# 3. UI 구성
# ==========================================
st.set_page_config(page_title="단어 중심 상표 검증", layout="wide")
st.title("🔎 상표 단어 존재 여부 정밀 검증")
st.write("특허청 데이터에서 사용자가 입력한 단어가 포함된 상표를 필터링 없이 찾아냅니다.")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("📝 검증 요청")
    biz_desc = st.text_input("사업 내용", value="베이커리")
    tm_name = st.text_input("검색할 브랜드명", value="봄안고")
    btn = st.button("특허청 실시간 검증 시작", use_container_width=True)

if btn:
    with st.spinner("특허청 서버 데이터를 대조 중입니다..."):
        matches, raw_log = verify_trademark_existence(tm_name)
        
        if matches is not None:
            with col2:
                st.subheader("🔍 검증 결과 리포트")
                
                if matches:
                    # 💡 상표가 발견된 경우 (봄안고 등)
                    st.warning(f"❗ 특허청 데이터베이스에서 '{tm_name}' 단어가 포함된 상표를 발견했습니다.")
                    
                    # 발견된 데이터만 표로 보여줌
                    import pandas as pd
                    st.table(pd.DataFrame(matches))
                    
                    st.divider()
                    
                    # AI 분석 (실제 발견된 데이터를 바탕으로 조언)
                    with st.spinner("AI가 법적 위험도를 분석 중입니다..."):
                        prompt = f"사용자 사업: {biz_desc}, 검색어: {tm_name}. " \
                                 f"특허청에서 실제 발견된 다음 상표들과의 충돌 위험을 조언해줘: {matches}"
                        response = model.generate_content(prompt)
                        st.markdown("#### ⚖️ AI 변리사 분석 의견")
                        st.write(response.text)
                else:
                    # 💡 상표가 정말로 발견되지 않은 경우
                    st.success(f"✅ 특허청 서버 전수 조사 결과, '{tm_name}' 단어를 포함한 상표가 발견되지 않았습니다.")
                    st.info("해당 단어는 현재 특허청 데이터상으로 깨끗한 상태일 가능성이 높습니다.")
        else:
            st.error(f"🚨 검증 불가: {raw_log}")

st.divider()
with st.expander("📡 특허청 서버 수신 원본 데이터(XML) 직접 확인"):
    if btn and raw_log:
        st.code(raw_log[:3000], language='xml')
    else:
        st.write("검증을 시작하면 서버에서 수신한 원본 로그가 여기에 표시됩니다.")