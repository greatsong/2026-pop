import glob
import os
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="연령별 인구 구조", page_icon="📊", layout="wide")


def find_default_csv():
    """코드 파일과 같은 폴더에서 CSV를 자동으로 찾는다 (한글 파일명 정규화 문제 회피)."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = glob.glob(os.path.join(base_dir, "*.csv"))
    return candidates[0] if candidates else None


@st.cache_data
def load_data(file):
    df = pd.read_csv(file, encoding="cp949", low_memory=False)
    for col in df.columns[1:]:
        df[col] = df[col].astype(str).str.replace(",", "", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


st.title("📊 연령별 인구 구조 시각화")
st.caption("행정안전부 연령별 인구현황(월간) 데이터 기반")

# ── 데이터 불러오기 ──────────────────────────────
st.sidebar.header("데이터")
uploaded = st.sidebar.file_uploader(
    "CSV 업로드 (없으면 같은 폴더의 파일 자동 사용)", type=["csv"]
)

if uploaded is not None:
    df = load_data(uploaded)
else:
    default_path = find_default_csv()
    if default_path is None:
        st.error(
            "같은 폴더에서 CSV 파일을 찾을 수 없습니다. "
            "이 코드 파일과 같은 폴더에 CSV 파일을 넣어주세요."
        )
        st.stop()
    df = load_data(default_path)
    st.sidebar.caption(f"불러온 파일: {os.path.basename(default_path)}")

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

# 계(전체) 연령 컬럼만 나이순 정렬
total_cols = col_df[col_df["gender"] == "계"].sort_values("age")
age_cols = total_cols["col"].tolist()
ages = total_cols["age"].tolist()

# ── 지역 선택 (검색 가능한 선택창: 목록에서 고르거나 직접 타이핑) ──
region_list = sorted(df["지역명"].unique().tolist())
default_idx = region_list.index("서울특별시") if "서울특별시" in region_list else 0

region = st.selectbox(
    "지역을 선택하거나 이름을 입력해 검색하세요 (읍/면/동 포함)",
    options=region_list,
    index=default_idx,
)

genders = st.multiselect("그래프에 표시할 성별", ["계", "남", "여"], default=["계"])
if not genders:
    st.info("최소 하나 이상의 성별을 선택해주세요.")
    st.stop()

row = df[df["지역명"] == region].iloc[0]

# ── ① 선택 지역 인구 구조 꺾은선 그래프 ────────────
color_map = {"계": "#4C78A8", "남": "#54A24B", "여": "#E45756"}
fig1 = go.Figure()

for g in genders:
    sub = col_df[col_df["gender"] == g].sort_values("age")
    g_ages = sub["age"].tolist()
    values = [row[c] for c in sub["col"]]
    fig1.add_trace(
        go.Scatter(
            x=g_ages,
            y=values,
            mode="lines+markers",
            name=g,
            line=dict(color=color_map.get(g), width=2),
        )
    )

fig1.update_layout(
    title=f"{region} 연령별 인구 구조 ({yyyymm})",
    xaxis_title="연령(세)",
    yaxis_title="인구수(명)",
    hovermode="x unified",
    template="plotly_white",
    height=500,
)

st.plotly_chart(fig1, use_container_width=True)

# ── 요약 지표 ────────────────────────────────────
total_col = f"{yyyymm}_계_총인구수"
if total_col in row.index and pd.notna(row[total_col]):
    c1, c2 = st.columns(2)
    c1.metric("총인구수", f"{int(row[total_col]):,} 명")
    peak_col_map = total_cols.set_index("age")["col"]
    peak_age = row[peak_col_map].astype(float).idxmax()
    c2.metric("최다 인구 연령대", f"{peak_age}세")

st.divider()

# ── ② 인구 구조가 가장 유사한 지역 Top 5 ───────────
st.subheader(f"🔍 '{region}'와(과) 인구 구조가 가장 비슷한 지역 Top 5")

# 연령별 인구수 행렬 (지역 x 연령)
matrix = df[age_cols].to_numpy(dtype=float)
matrix = np.nan_to_num(matrix, nan=0.0)

# 지역별 합계로 나눠 "구성비"로 정규화 (총인구가 0인 지역은 제외)
row_sums = matrix.sum(axis=1)
valid_mask = row_sums > 0
prop_matrix = np.zeros_like(matrix)
prop_matrix[valid_mask] = matrix[valid_mask] / row_sums[valid_mask, None]

target_idx = df.index[df["지역명"] == region][0]
target_vec = prop_matrix[target_idx]

# 코사인 유사도 계산
norms = np.linalg.norm(prop_matrix, axis=1)
target_norm = np.linalg.norm(target_vec)

with np.errstate(invalid="ignore", divide="ignore"):
    cos_sim = (prop_matrix @ target_vec) / (norms * target_norm)
cos_sim = np.nan_to_num(cos_sim, nan=-1.0)

sim_series = pd.Series(cos_sim, index=df.index)
sim_series[~valid_mask] = -1.0
sim_series[target_idx] = -1.0  # 자기 자신 제외

top5_idx = sim_series.sort_values(ascending=False).head(5).index
top5_df = df.loc[top5_idx, ["지역명"]].copy()
top5_df["유사도"] = sim_series.loc[top5_idx].values

st.dataframe(
    top5_df.reset_index(drop=True).style.format({"유사도": "{:.4f}"}),
    use_container_width=True,
)

# ── Top5 + 선택 지역 비교 꺾은선 그래프 (구성비 기준) ──
fig2 = go.Figure()

fig2.add_trace(
    go.Scatter(
        x=ages,
        y=target_vec * 100,
        mode="lines+markers",
        name=f"★ {region} (선택 지역)",
        line=dict(color="#E45756", width=4),
    )
)

palette = ["#4C78A8", "#54A24B", "#F58518", "#B279A2", "#72B7B2"]
for i, idx in enumerate(top5_idx):
    name = df.loc[idx, "지역명"]
    sim = sim_series.loc[idx]
    fig2.add_trace(
        go.Scatter(
            x=ages,
            y=prop_matrix[idx] * 100,
            mode="lines",
            name=f"{name} (유사도 {sim:.3f})",
            line=dict(color=palette[i % len(palette)], width=1.5, dash="dot"),
        )
    )

fig2.update_layout(
    title=f"{region} vs 인구 구조 유사 지역 Top 5 (연령별 구성비 %)",
    xaxis_title="연령(세)",
    yaxis_title="해당 연령 인구 비율(%)",
    hovermode="x unified",
    template="plotly_white",
    height=550,
)

st.plotly_chart(fig2, use_container_width=True)

st.caption(
    "※ 유사도는 지역별 총인구 대비 연령별 인구 비율(구성비)의 코사인 유사도로 계산했습니다. "
    "절대 인구수가 아닌 '인구 구조의 모양'이 얼마나 비슷한지를 나타냅니다."
)
