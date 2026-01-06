import math
from typing import Optional, Tuple

import pandas as pd
import streamlit as st


# ------------------------
# Utility functions
# ------------------------

def time_str_to_minutes(s: str) -> Optional[float]:
    """
    Convert a time string like '2:39:59' or '39:30' into minutes (float).
    Returns None if empty or invalid.
    """
    if not s or str(s).strip() == "":
        return None
    s = s.strip()
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = map(float, parts)
            return h * 60.0 + m + sec / 60.0
        elif len(parts) == 2:
            m, sec = map(float, parts)
            return m + sec / 60.0
        else:
            # treat as pure minutes
            return float(parts[0])
    except ValueError:
        return None


def minutes_to_hms(mins: float) -> str:
    if not math.isfinite(mins):
        return "—"
    total_seconds = int(round(mins * 60))
    if total_seconds < 0:
        total_seconds = 0
    h = total_seconds // 3600
    rem = total_seconds % 3600
    m = rem // 60
    s = rem % 60
    return f"{h:d}:{m:02d}:{s:02d}"


def riegel_predict(t1_min: float, d1_km: float, d2_km: float, exponent: float = 1.06) -> float:
    """
    Riegel prediction: T2 = T1 * (D2/D1)^exponent
    Time in minutes, distances in km.
    """
    return t1_min * (d2_km / d1_km) ** exponent


# ------------------------
# DF estimation from races
# ------------------------

def estimate_df_from_races(
    t10_min: Optional[float],
    thm_min: Optional[float],
    tmar_min: Optional[float],
) -> float:
    """
    Estimate durability factor DF from 10K + Half Marathon vs Marathon.

    Steps:
      1) Predict marathon time from 10K via Riegel (if 10K available).
      2) Predict marathon time from Half Marathon via Riegel (if HM available).
      3) Take the average predicted marathon time.
      4) DF = (avg_predicted_Marathon_time) / (actual_Marathon_time)

    Interpretation:
      - DF > 1.0  -> more durable marathoner than typical prediction
      - DF ~ 1.0  -> typical durability
      - DF < 1.0  -> underperforms over marathon vs shorter races
    """
    if tmar_min is None or tmar_min <= 0:
        return 1.0

    predictions = []
    MAR_KM = 42.195
    TEN_KM = 10.0
    HM_KM = 21.0975

    if t10_min is not None and t10_min > 0:
        tmar_from_10k = riegel_predict(t10_min, TEN_KM, MAR_KM)
        predictions.append(tmar_from_10k)

    if thm_min is not None and thm_min > 0:
        tmar_from_hm = riegel_predict(thm_min, HM_KM, MAR_KM)
        predictions.append(tmar_from_hm)

    if not predictions:
        return 1.0

    avg_pred = sum(predictions) / len(predictions)
    df = avg_pred / tmar_min

    # Basic sanity: keep DF in a reasonable window
    df = max(0.80, min(1.20, df))
    return df


# ------------------------
# Marathon prediction from ATS & DF
# ------------------------

def compute_mpt_minutes(ats_kmh: float, df: float) -> float:
    """
    Your updated Marathon Prediction Time (MPT) model:

        MPT (min) = 4666 * ATS^(-1.33) / DF + 8

    - ATS in km/h
    - DF dimensionless durability factor
    """
    if ats_kmh <= 0 or df <= 0:
        return float("inf")
    base = 4666.0 * (ats_kmh ** -1.33) / df
    return base + 8.0


# ------------------------
# Zone mapping relative to MP
# ------------------------

def classify_zone_by_mp(pace_min_per_km: float, mp_pace_min_per_km: Optional[float]) -> str:
    """
    Classify a pace into zones relative to target marathon pace (MP) using speed % of MP.

    Zones (as % of MP speed):
      Z1: < 70%
      Z2: 70–80%
      Z3: 80–90%
      Z4: 90–95%
      Z5: 95–102%
      Z6: 102–110%
      Z7: > 110%
    """
    if mp_pace_min_per_km is None or mp_pace_min_per_km <= 0 or pace_min_per_km <= 0:
        return "N/A"

    v = 60.0 / pace_min_per_km
    v_mp = 60.0 / mp_pace_min_per_km
    pct = v / v_mp  # % of MP speed

    if pct < 0.70:
        return "Z1 <70% MP"
    elif pct < 0.80:
        return "Z2 70–80% MP"
    elif pct < 0.90:
        return "Z3 80–90% MP"
    elif pct < 0.95:
        return "Z4 90–95% MP"
    elif pct < 1.02:
        return "Z5 95–102% MP"
    elif pct < 1.10:
        return "Z6 102–110% MP"
    else:
        return "Z7 >110% MP"


# ------------------------
# Streamlit App
# ------------------------

st.set_page_config(page_title="ATS–DF Marathon Model", layout="wide")

st.title("ATS · Durability · Marathon Time Playground")

st.markdown(
    """
This app lets you **play with segment-based training weeks** and see how they affect:

- **ATS (Average Training Speed, km/h)**
- **DF (Durability Factor)** — estimated from 10K + Half Marathon vs Marathon
- **Predicted Marathon Time** using your calibrated model:

\\[
\\text{MPT (min)} = \\frac{4666 \\cdot \\text{ATS}^{-1.33}}{DF} + 8
\\]
"""
)

# ------------------------
# Sidebar – Race-based DF inputs
# ------------------------

st.sidebar.header("Race Inputs (for DF estimation)")

col10, colhm = st.sidebar.columns(2)
t10_str = col10.text_input("10K time (h:mm:ss or mm:ss)", value="00:41:30")
thm_str = colhm.text_input("Half Marathon time", value="01:29:29")
tmar_str = st.sidebar.text_input("Marathon time (actual)", value="03:06:58")

t10_min = time_str_to_minutes(t10_str)
thm_min = time_str_to_minutes(thm_str)
tmar_min = time_str_to_minutes(tmar_str)

df_est = estimate_df_from_races(t10_min, thm_min, tmar_min)
st.sidebar.metric("Estimated DF (from races)", f"{df_est:.3f}")

mp_pace_min_per_km = None
if tmar_min is not None and tmar_min > 0:
    mp_pace_min_per_km = tmar_min / 42.195
    st.sidebar.write(f"Implied MP ≈ **{mp_pace_min_per_km:.2f} min/km**")


# ------------------------
# Main – Segment-based training week
# ------------------------

st.subheader("1. Define Your Weekly Training Segments")

st.markdown(
    """
Enter each **segment of your week** (not each individual rep!):

- Example rows:
  - 14 km easy at 4:50/km
  - 10 km steady at 4:10/km
  - 8 km intervals block (effective 4:00/km)
"""
)

default_data = [
    {"Segment": "Easy aerobic", "Distance_km": 40.0, "Pace_min_per_km": 5.0},
    {"Segment": "Steady / M-1", "Distance_km": 25.0, "Pace_min_per_km": 4.3},
    {"Segment": "MP block", "Distance_km": 15.0, "Pace_min_per_km": 4.1},
    {"Segment": "Sub-threshold / CV", "Distance_km": 10.0, "Pace_min_per_km": 3.9},
    {"Segment": "Fast reps", "Distance_km": 5.0, "Pace_min_per_km": 3.5},
]

seg_df = st.data_editor(
    pd.DataFrame(default_data),
    num_rows="dynamic",
    use_container_width=True,
    key="segments_table",
)

# Clean / compute
seg_df = seg_df.dropna(subset=["Distance_km", "Pace_min_per_km"])
seg_df = seg_df[seg_df["Distance_km"] > 0]
seg_df = seg_df[seg_df["Pace_min_per_km"] > 0]

if seg_df.empty:
    st.warning("Add at least one segment with positive distance and pace.")
else:
    # time (hours) per segment
    seg_df["Time_hours"] = seg_df["Distance_km"] * seg_df["Pace_min_per_km"] / 60.0
    total_km = seg_df["Distance_km"].sum()
    total_hours = seg_df["Time_hours"].sum()
    ats_kmh = total_km / total_hours if total_hours > 0 else 0.0

    # classify zones
    seg_df["Zone"] = seg_df["Pace_min_per_km"].apply(
        lambda p: classify_zone_by_mp(p, mp_pace_min_per_km)
    )

    # ------------------------
    # Summary
    # ------------------------
    st.subheader("2. Weekly Summary from Segments")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Distance (km)", f"{total_km:.1f}")
    c2.metric("Total Time (h)", f"{total_hours:.2f}")
    c3.metric("ATS (km/h)", f"{ats_kmh:.2f}")

    # Zone distribution
    st.markdown("**Zone distribution (by distance, relative to MP)**")
    zone_dist = (
        seg_df.groupby("Zone")["Distance_km"].sum().reset_index().sort_values("Distance_km", ascending=False)
    )
    zone_dist["% of total km"] = 100.0 * zone_dist["Distance_km"] / total_km
    st.dataframe(zone_dist, use_container_width=True)

    # ------------------------
    # Marathon prediction
    # ------------------------
    st.subheader("3. Marathon Prediction from ATS & DF")

    # Allow user to override DF if desired
    use_race_df = st.checkbox(
        "Use DF estimated from races (10K + HM vs Marathon)", value=True
    )
    if use_race_df:
        df_used = df_est
    else:
        df_used = st.number_input("Manual DF override", min_value=0.80, max_value=1.20, value=float(df_est), step=0.01)

    mpt_min = compute_mpt_minutes(ats_kmh, df_used)
    mpt_str = minutes_to_hms(mpt_min)

    c4, c5 = st.columns(2)
    c4.metric("DF used", f"{df_used:.3f}")
    c5.metric("Predicted Marathon Time", mpt_str)

    st.markdown(
        f"""
**Details**

- ATS = **{ats_kmh:.2f} km/h**  (equivalent pace ≈ {60/ats_kmh:.2f} min/km)
- DF = **{df_used:.3f}**
- MPT (model) = **{mpt_min:.1f} min** → **{mpt_str}**

_Model equation:_  
\\[
\\text{{MPT}}(\\text{{min}}) = \\frac{{4666 \\cdot \\text{{ATS}}^{{-1.33}}}}{{DF}} + 8
\\]
"""
    )
