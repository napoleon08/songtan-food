import datetime
import re

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

NEIS_URL = "https://open.neis.go.kr/hub"
DEFAULT_SCHOOL = "송탄고등학교"

st.set_page_config(
    page_title="우리학교 급식 데이터",
    page_icon="🍚",
    layout="wide",
)

st.title("🍚 우리학교 급식 데이터")
st.caption("나이스(NEIS) 교육정보 개방 API로 학교 급식을 조회하고 비교합니다.")

st.info(
    "학교 이름으로 검색한 뒤 3곳 이상을 선택하면 같은 날짜의 중식을 비교할 수 있습니다. "
    "송탄고등학교가 기본 선택 학교입니다."
)

def api_get(endpoint, params):
    response = requests.get(f"{NEIS_URL}/{endpoint}", params=params, timeout=15)
    response.raise_for_status()
    return response.json()

@st.cache_data(ttl=600)
def search_schools(query):
    data = api_get("schoolInfo", {"Type": "json", "SCHUL_NM": query})
    if "schoolInfo" in data:
        return data["schoolInfo"][1].get("row", [])
    result = data.get("RESULT", {})
    if result.get("CODE") == "INFO-200":
        return []
    raise ValueError(result.get("MESSAGE", "학교 조회에 실패했습니다."))

def search_with_abbreviation(query):
    schools = search_schools(query)
    if schools:
        return schools

    replacements = [
        ("여고", "여자고등학교"),
        ("여중", "여자중학교"),
        ("여초", "여자초등학교"),
        ("고", "고등학교"),
        ("중", "중학교"),
        ("초", "초등학교"),
    ]
    for short, full in replacements:
        if query.endswith(short):
            expanded = query[:-len(short)] + full
            schools = search_schools(expanded)
            if schools:
                return schools
    return []

def school_label(school):
    return f"{school['SCHUL_NM']} · {school.get('LCTN_SC_NM', '지역 미상')}"

@st.cache_data(ttl=300)
def get_meal(school_code, office_code, ymd):
    data = api_get(
        "mealServiceDietInfo",
        {
            "Type": "json",
            "ATPT_OFCDC_SC_CODE": office_code,
            "SD_SCHUL_CODE": school_code,
            "MMEAL_SC_CODE": "2",
            "MLSV_FROM_YMD": ymd,
            "MLSV_TO_YMD": ymd,
        },
    )
    if "mealServiceDietInfo" not in data:
        result = data.get("RESULT", {})
        if result.get("CODE") == "INFO-200":
            return None
        raise ValueError(result.get("MESSAGE", "급식 조회에 실패했습니다."))
    rows = data["mealServiceDietInfo"][1].get("row", [])
    return rows[0] if rows else None

def clean_menu(menu_text):
    dishes = []
    for dish in menu_text.split("<br/>"):
        dish = re.sub(r"\s*\([0-9.]+\)", "", dish).strip()
        dish = re.sub(r"\s+", " ", dish)
        if dish:
            dishes.append(dish)
    return dishes


# 한국 시간 기준 오늘
today_kst = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date()

st.sidebar.header("학교 검색")
query = st.sidebar.text_input("학교 이름", value=DEFAULT_SCHOOL)

try:
    schools = search_with_abbreviation(query)
except (requests.RequestException, ValueError) as error:
    st.error(f"학교 검색에 실패했습니다: {error}")
    st.stop()

if not schools:
    st.warning("학교를 찾지 못했습니다. 정식 학교 이름으로 다시 검색해 주세요.")
    st.stop()

labels = [school_label(s) for s in schools]
selected_label = st.sidebar.selectbox("검색 결과에서 학교 선택", labels)
selected_single = schools[labels.index(selected_label)]

date = st.sidebar.date_input("급식 날짜", value=today_kst)
ymd = date.strftime("%Y%m%d")

st.subheader("📅 선택한 학교의 급식")

try:
    meal = get_meal(
        selected_single["SD_SCHUL_CODE"],
        selected_single["ATPT_OFCDC_SC_CODE"],
        ymd,
    )
except (requests.RequestException, ValueError) as error:
    st.error(f"급식 조회에 실패했습니다: {error}")
    meal = None

if meal is None:
    st.info("조회한 날짜에는 급식 정보가 없습니다.")
else:
    dishes = clean_menu(meal.get("DDISH_NM", ""))
    c1, c2, c3 = st.columns(3)
    c1.metric("학교", selected_single["SCHUL_NM"])
    c2.metric("메뉴 수", f"{len(dishes)}개")
    c3.metric("칼로리", meal.get("CAL_INFO", "-"))

    st.markdown("### 🍽️ 오늘의 중식")
    cols = st.columns(3)
    for i, dish in enumerate(dishes):
        cols[i % 3].markdown(f"**{i + 1}. {dish}**")

    with st.expander("원본 데이터 보기"):
        st.write(meal.get("DDISH_NM", ""))
        st.caption("괄호 속 숫자는 나이스 API가 제공하는 알레르기 유발 식품 번호입니다.")

st.divider()
st.subheader("🏫 학교 3곳 이상 비교")

compare_labels = st.multiselect(
    "비교할 학교를 선택하세요",
    labels,
    default=[selected_label] if len(labels) == 1 else labels[:3],
    help="현재 검색 결과에서 여러 학교를 선택해 같은 날짜의 중식을 비교합니다.",
)

if len(compare_labels) < 3:
    st.warning("필수 조건: 학교를 3곳 이상 한 번에 선택해 비교하세요.")
else:
    compare_rows = []
    for label in compare_labels:
        school = schools[labels.index(label)]
        try:
            row = get_meal(
                school["SD_SCHUL_CODE"],
                school["ATPT_OFCDC_SC_CODE"],
                ymd,
            )
        except (requests.RequestException, ValueError):
            row = None

        if row:
            dishes = clean_menu(row.get("DDISH_NM", ""))
            compare_rows.append(
                {
                    "학교": school["SCHUL_NM"],
                    "지역": school.get("LCTN_SC_NM", ""),
                    "메뉴 수": len(dishes),
                    "칼로리": parse_kcal(row.get("CAL_INFO", "")),
                    "메뉴": " · ".join(dishes),
                }
            )
        else:
            compare_rows.append(
                {
                    "학교": school["SCHUL_NM"],
                    "지역": school.get("LCTN_SC_NM", ""),
                    "메뉴 수": 0,
                    "칼로리": None,
                    "메뉴": "급식 정보 없음",
                }
            )

    comparison = pd.DataFrame(compare_rows)
    st.dataframe(comparison, hide_index=True, width="stretch")

    chart_df = comparison.dropna(subset=["칼로리"]).copy()
    if not chart_df.empty:
        fig = px.bar(
            chart_df,
            x="학교",
            y="칼로리",
            text="칼로리",
            title=f"{date.strftime('%Y-%m-%d')} 학교별 중식 칼로리 비교",
        )
        fig.update_layout(yaxis_title="칼로리 (kcal)", xaxis_title="")
        st.plotly_chart(fig, width="stretch")

    st.caption("이 그래프로 알 수 있는 것: 같은 날짜에 학교별 급식 칼로리와 메뉴 수를 비교할 수 있습니다.")

st.divider()
st.caption("데이터 출처: 나이스 교육정보 개방 포털 · 급식식단정보 API")

def parse_kcal(value):
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(value))
    return float(match.group(1)) if match else None
