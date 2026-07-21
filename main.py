import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="연령별 인구 구조", page_icon="📊", layout="wide")

DEFAULT_PATH = "202606_202606_연령별인구현황_월간.csv"  # 코드와 같은 폴더에 위치


@st.cache_data
def load_data(file):
    df = pd.read_csv(file, encoding="cp949", low_memory=False)
    # 천단위 콤마 제거 후 숫자형 변환 (첫 컬럼=행정구역 제외)
    for col in df.columns[1:]:
        df[col] = df[col].astype(str).str.replace(",", "", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


st.title("📊 연령별 인구 구조 시각화")
st.caption("행정안전부 연령별 인구현황(월간) 데이터 기반")

# ── 데이터 불러오기 ──────────────────────────────
st.sidebar.header("데이터")
uploaded = st.sidebar.file_uploader(
    "CSV 업로드 (없으면 기본 파일 사용)", type=["csv"]
)

if uploaded is not None:
    df = load_data(uploaded)
else:
    try:
        df = load_data(DEFAULT_PATH)
    except FileNotFoundError:
        st.error(
            f"'{DEFAULT_PATH}' 파일을 찾을 수 없습니다. "
            "app.py와 같은 폴더에 해당 CSV 파일을 넣어주세요."
        )
        st.stop()

# ── 지역명 정리 (코드 제거) ───────────────────────
df["지역명"] = (
    df["행정구역"].str.replace(r"\s*\(\d+\)", "", regex=True).str.strip()
)

# ── 연령/성별 컬럼 자동 감지 (기준월이 바뀌어도 자동 대응) ──
age_pattern = re.compile(r"^(\d{4}년\d{2}월)_(계|남|여)_(\d+세|100세 이상)$")
col_info = []
for col in df.columns:
    m = age_pattern.match(col)
    if m:
        yyyymm, gender, age = m.groups()
        age_num = 100 if "이상" in age else int(age.replace("세", ""))
        col_info.append({"col": col, "yyyymm": yyyymm, "gender": gender, "age": age_num})

col_df = pd.DataFrame(col_info)
if col_df.empty:
    st.error("연령별 컬럼을 찾지 못했습니다. CSV 형식을 확인해주세요.")
    st.stop()

yyyymm = col_df["yyyymm"].iloc[0]
st.caption(f"데이터 기준월: {yyyymm}")

# ── 지역 선택 (검색 가능한 선택창: 목록에서 고르거나 직접 타이핑) ──
region_list = sorted(df["지역명"].unique().tolist())
default_idx = region_list.index("서울특별시") if "서울특별시" in region_list else 0

region = st.selectbox(
    "지역을 선택하거나 이름을 입력해 검색하세요",
    options=region_list,
    index=default_idx,
)

genders = st.multiselect("성별 선택", ["계", "남", "여"], default=["계"])
if not genders:
    st.info("최소 하나 이상의 성별을 선택해주세요.")
    st.stop()

row = df[df["지역명"] == region].iloc[0]

# ── 꺾은선 그래프 ─────────────────────────────────
color_map = {"계": "#4C78A8", "남": "#54A24B", "여": "#E45756"}
fig = go.Figure()

for g in genders:
    sub = col_df[col_df["gender"] == g].sort_values("age")
    ages = sub["age"].tolist()
    values = [row[c] for c in sub["col"]]
    fig.add_trace(
        go.Scatter(
            x=ages,
            y=values,
            mode="lines+markers",
            name=g,
            line=dict(color=color_map.get(g), width=2),
        )
    )

fig.update_layout(
    title=f"{region} 연령별 인구 구조 ({yyyymm})",
    xaxis_title="연령(세)",
    yaxis_title="인구수(명)",
    hovermode="x unified",
    template="plotly_white",
    height=550,
)

st.plotly_chart(fig, use_container_width=True)

# ── 요약 지표 ────────────────────────────────────
total_col = f"{yyyymm}_계_총인구수"
if total_col in row.index and pd.notna(row[total_col]):
    c1, c2 = st.columns(2)
    c1.metric("총인구수", f"{int(row[total_col]):,} 명")
    peak_age_row = col_df[col_df["gender"] == "계"]
    if not peak_age_row.empty:
        peak_col = peak_age_row.set_index("age")["col"]
        peak_age = row[peak_col].astype(float).idxmax()
        c2.metric("최다 인구 연령대", f"{peak_age}세")
