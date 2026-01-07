import streamlit as st
import math

# ---------- Helpers ----------

def parse_time_to_minutes(time_str: str) -> float:
    """
    Parse a time string into minutes.
    Accepts: "mm:ss", "hh:mm:ss", or "mm".
    Returns None if parsing fails.
    """
    if not time_str:
        return None

    time_str = time_str.strip()
    parts = time_str.split(":")

    try:
        if len(parts) == 3:
            h, m, s = map(int, parts)
        elif len(parts) == 2:
            h = 0
            m, s = map(int, parts)
        elif len(parts) == 1:
            h = 0
            m = int(parts[0])
            s = 0
        else:
            return None
    except ValueError:
        return None

    total_minutes = h * 60 + m + s / 60.0
    return total_minutes


def minutes_to_hms_str(minutes: float) -> str:
    """
    Convert minutes (float) to "h:mm:ss".
    """
    if minutes is None or math.isnan(minutes):
        return "—"
    total_seconds = int(round(minutes * 60))
    h = total_seconds // 3600
    rem = total_seconds % 3600
    m = rem // 60
    s = rem % 60
    return f"{h}:{m:02d}:{s:02d}"


def minutes_per_km_to_pace_str(min_per_km: float) -> str:
    """
    Convert minutes/km to "m:ss /km".
    """
    if min_per_km is None or min_per_km <= 0:
        return "—"
    total_seconds = int(round(min_per_km * 60))
    m = total_seconds // 60
    s = total_seconds % 60
    return f"{m}:{s:02d} /km"


# ---------- Core models ----------

def estimate_df_personal(ats: float,
                         t10k_actual_min: float,
                         t10k_pred_min: float,
                         annual_elev_m: float) -> float:
    """
    Personal durability factor (DF) model:

    DF = 1.768 - 0.049 * ATS - 0.0000069 * Elev_year + 0.118 * Gap_10k

    where Gap_10k = (T10_actual - T10_pred) / T10_pred
    """
    if ats is None or ats <= 0:
        return None
    if t10k_actual_min is None or t10k_pred_min is None or t10k_pred_min <= 0:
        return None
    if annual_elev_m is None:
        annual_elev_m = 0.0

    gap_10k = (t10k_actual_min - t10k_pred_min) / t10k_pred_min

    df = (
        1.768
        - 0.049 * ats
        - 0.0000069 * annual_elev_m
        + 0.118 * gap_10k
    )

    # Clamp DF into a plausible range
    df = max(0.80, min(1.20, df))
    return df


def predict_marathon_time_minutes(ats: float, df: float) -> float:
    """
    Your marathon prediction model:

    MPT (min) = (4666 * ATS^(-1.33) / DF) + 8
    """
    if ats is None or ats <= 0 or df is None or df <= 0:
        return None
    base = 4666.0 * (ats ** -1.33)
    mpt = base / df + 8.0
    return mpt


# ---------- Zone classification ----------

def classify_zone(pace_min_per_km: float,
                  mp_pace_min_per_km: float) -> str:
    """
    Classify a pace into Z1–Z5 based on % of marathon-pace speed.

    - Z1: < 85% MP speed (easy / recovery)
    - Z2: 85–95% MP speed (steady / aerobic)
    - Z3: 95–105% MP speed (MP / sub-threshold)
    - Z4: 105–115% MP speed (threshold / CV band)
    - Z5: > 115% MP speed (faster than threshold)
    """
    if pace_min_per_km is None or pace_min_per_km <= 0:
        return None
    if mp_pace_min_per_km is None or mp_pace_min_per_km <= 0:
        return None

    # Convert paces to speeds
    v_mp = 60.0 / mp_pace_min_per_km
    v = 60.0 / pace_min_per_km
    ratio = v / v_mp  # 1.0 = MP, >1 faster than MP, <1 slower than MP

    if ratio < 0.85:
        return "Z1"
    elif ratio < 0.95:
        return "Z2"
    elif ratio < 1.05:
        return "Z3"
    elif ratio < 1.15:
        return "Z4"
    else:
        return "Z5"


# ---------- Streamlit UI ----------

st.set_page_config(page_title="Marathon ATS + Durability Planner", layout="centered")

st.title("🏃‍♂️ Marathon ATS + Durability Planner (with Zones)")

st.markdown(
    """
This app lets you **play with training inputs** and see their impact on:

- **ATS** (Average Training Speed, km/h)  
- **DF** (Durability Factor, via your personal model)  
- **Predicted marathon time**  
- **km in each intensity zone (Z1–Z5)** relative to Marathon Pace

Marathon model:

> **MPT (min) = (4666 · ATS⁻¹·³³ / DF) + 8**
"""
)

# ---------- SIDEBAR: Weekly + global inputs ----------

st.sidebar.header("1️⃣ Weekly Training Inputs (Manual)")

col_km, col_hrs = st.sidebar.columns(2)
with col_km:
    weekly_km = st.number_input("Weekly km", min_value=0.0, value=80.0, step=1.0)
with col_hrs:
    weekly_hours = st.number_input("Weekly hours", min_value=0.1, value=6.0, step=0.25)

ats_from_week = weekly_km / weekly_hours if weekly_hours > 0 else None
st.sidebar.markdown(
    f"**ATS from week:** {ats_from_week:.2f} km/h"
    if ats_from_week
    else "**ATS from week:** —"
)

ats = st.sidebar.number_input(
    "ATS used in manual scenario (km/h)",
    min_value=5.0,
    max_value=20.0,
    value=float(round(ats_from_week or 12.0, 2)),
    step=0.1,
)

st.sidebar.header("2️⃣ Marathon Pace & Threshold")

mp_pace_str = st.sidebar.text_input(
    "Target marathon pace (min/km)",
    value="4:15",  # ~2:59:xx MP-ish
)
lt_pace_str = st.sidebar.text_input(
    "Threshold pace (min/km) (for reference)",
    value="3:55",
)

mp_pace_minpkm = parse_time_to_minutes(mp_pace_str)
lt_pace_minpkm = parse_time_to_minutes(lt_pace_str)

st.sidebar.markdown(
    f"- MP speed ≈ **{60/mp_pace_minpkm:.2f} km/h**" if mp_pace_minpkm else "- MP speed: —"
)
st.sidebar.markdown(
    f"- LT speed ≈ **{60/lt_pace_minpkm:.2f} km/h**" if lt_pace_minpkm else "- LT speed: —"
)

st.sidebar.header("3️⃣ Personal Durability (DF) Inputs")

st.sidebar.markdown(
    """
DF is estimated from:  
- **ATS**  
- **10K actual vs predicted**, and  
- **Annual elevation gain**
"""
)

t10k_actual_str = st.sidebar.text_input("Actual 10K time (mm:ss or hh:mm:ss)", value="41:32")
t10k_pred_str = st.sidebar.text_input("Predicted 10K time (e.g. VDOT)", value="37:48")
annual_elev_m = st.sidebar.number_input(
    "Annual elevation gain (m)",
    min_value=0.0,
    value=20000.0,
    step=500.0,
)

t10k_actual_min = parse_time_to_minutes(t10k_actual_str)
t10k_pred_min = parse_time_to_minutes(t10k_pred_str)

df_est_manual = estimate_df_personal(ats, t10k_actual_min, t10k_pred_min, annual_elev_m)

manual_df_override = st.sidebar.number_input(
    "Optional: override DF (manual)",
    min_value=0.80,
    max_value=1.20,
    value=float(df_est_manual if df_est_manual is not None else 1.03),
    step=0.01,
)

use_manual_df = st.sidebar.checkbox("Use manual DF override", value=False)

df_used_manual = manual_df_override if use_manual_df or df_est_manual is None else df_est_manual

st.sidebar.markdown(f"**DF (manual scenario):** {df_used_manual:.3f}")

# ---------- MAIN: Summary of manual scenario ----------

st.subheader("📊 Manual Scenario Summary")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("ATS (manual)", f"{ats:.2f} km/h")
with col2:
    if t10k_actual_min and t10k_pred_min and t10k_pred_min > 0:
        gap_10k_pct = (t10k_actual_min - t10k_pred_min) / t10k_pred_min * 100
        st.metric("10K Gap", f"{gap_10k_pct:.1f} %")
    else:
        st.metric("10K Gap", "—")
with col3:
    st.metric("DF (manual scenario)", f"{df_used_manual:.3f}")

mpt_manual_min = predict_marathon_time_minutes(ats, df_used_manual)
mpt_manual_str = minutes_to_hms_str(mpt_manual_min)
if mpt_manual_min:
    mp_pace_manual_minpkm = mpt_manual_min / 42.195
    mp_pace_manual_str = minutes_per_km_to_pace_str(mp_pace_manual_minpkm)
else:
    mp_pace_manual_minpkm = None
    mp_pace_manual_str = "—"

colA, colB = st.columns(2)
with colA:
    st.metric("Marathon Prediction (manual)", mpt_manual_str)
with colB:
    st.metric("Marathon Pace (manual)", mp_pace_manual_str)

st.divider()

# ---------- WEEKLY WORKOUT PLANNER (SEGMENT-BASED BY SESSION) ----------

st.subheader("🧩 Plan Weekly Workouts (Session-Based)")

st.markdown(
    """
Define your **weekly sessions** (distance + pace) and see:

- Weekly km & hours  
- ATS for the week  
- km in each zone (Z1–Z5, relative to MP)  
- DF + marathon prediction for the planned week
"""
)

num_workouts = st.number_input(
    "Number of planned workouts this week",
    min_value=1,
    max_value=14,
    value=5,
    step=1,
)

workouts = []
total_plan_km = 0.0
total_plan_min = 0.0

for i in range(int(num_workouts)):
    st.markdown(f"**Workout {i+1}**")
    c1, c2, c3, c4 = st.columns([2, 2, 3, 2])

    with c1:
        name = st.text_input(f"Name {i+1}", value=f"Session {i+1}", key=f"name_{i}")
    with c2:
        dist_km = st.number_input(
            f"Distance {i+1} (km)",
            min_value=0.0,
            value=10.0 if i == 0 else 8.0,
            step=0.5,
            key=f"dist_{i}",
        )
    with c3:
        pace_str = st.text_input(
            f"Pace {i+1} (m:ss or mm:ss /km)",
            value="4:30" if i == 0 else "5:00",
            key=f"pace_{i}",
        )

    pace_min = parse_time_to_minutes(pace_str)
    if dist_km > 0 and pace_min and pace_min > 0:
        dur_min = dist_km * pace_min  # minutes (pace is min/km)
        total_plan_km += dist_km
        total_plan_min += dur_min
    else:
        dur_min = None

    zone = classify_zone(pace_min, mp_pace_minpkm) if mp_pace_minpkm else None
    with c4:
        st.write(f"Zone: **{zone}**" if zone else "Zone: —")

    workouts.append(
        {
            "name": name,
            "dist_km": dist_km,
            "pace_str": pace_str,
            "pace_min_per_km": pace_min,
            "zone": zone,
        }
    )

if total_plan_min > 0:
    plan_hours = total_plan_min / 60.0
    ats_plan = total_plan_km / plan_hours
else:
    plan_hours = None
    ats_plan = None

st.markdown(
    f"""
**Planned week totals**

- Total distance: **{total_plan_km:.1f} km**  
- Total time: **{plan_hours:.2f} h** (if all paces parsed)  
- ATS (planned): **{ats_plan:.2f} km/h**  
""" if ats_plan else
    "_Enter valid distances and paces to see planned ATS._"
)

# ---------- Zone distribution for planned week ----------

st.markdown("### 🧱 Planned km by zone (relative to MP)")

zone_descriptions = {
    "Z1": "Easy / Recovery (<85% MP speed)",
    "Z2": "Steady / Aerobic (85–95% MP)",
    "Z3": "MP / Sub-threshold (95–105% MP)",
    "Z4": "Threshold / CV (105–115% MP)",
    "Z5": "Faster than threshold (>115% MP)",
}

zone_km = {z: 0.0 for z in zone_descriptions.keys()}

for w in workouts:
    z = w["zone"]
    if z in zone_km and w["dist_km"] is not None:
        zone_km[z] += w["dist_km"]

if total_plan_km > 0:
    table_md = "| Zone | Description | km | % of week |\n|---|---|---|---|\n"
    for z in ["Z1", "Z2", "Z3", "Z4", "Z5"]:
        km = zone_km[z]
        pct = (km / total_plan_km * 100.0) if total_plan_km > 0 else 0.0
        table_md += f"| {z} | {zone_descriptions[z]} | {km:.1f} | {pct:.1f}% |\n"
    st.markdown(table_md)
else:
    st.info("Add distances and paces above to see km per zone.")

st.divider()

# ---------- DF & Marathon prediction for PLANNED scenario ----------

st.subheader("📈 Planned vs Manual Scenario")

df_plan = None
mpt_plan_min = None
mpt_plan_str = "—"
mp_pace_plan_str = "—"

if ats_plan:
    df_plan = estimate_df_personal(ats_plan, t10k_actual_min, t10k_pred_min, annual_elev_m)
    mpt_plan_min = predict_marathon_time_minutes(ats_plan, df_plan)
    mpt_plan_str = minutes_to_hms_str(mpt_plan_min)
    if mpt_plan_min:
        mp_pace_plan_str = minutes_per_km_to_pace_str(mpt_plan_min / 42.195)

colM, colP = st.columns(2)

with colM:
    st.markdown("### Manual scenario")
    st.markdown(f"- **ATS:** {ats:.2f} km/h")
    st.markdown(f"- **DF:** {df_used_manual:.3f}")
    st.markdown(f"- **Marathon:** {mpt_manual_str}")
    st.markdown(f"- **Pace:** {mp_pace_manual_str}")

with colP:
    st.markdown("### Planned-week scenario")
    if ats_plan and df_plan and mpt_plan_min:
        st.markdown(f"- **ATS:** {ats_plan:.2f} km/h")
        st.markdown(f"- **DF (est.):** {df_plan:.3f}")
        st.markdown(f"- **Marathon:** {mpt_plan_str}")
        st.markdown(f"- **Pace:** {mp_pace_plan_str}")
    else:
        st.markdown("_Enter valid workouts to compute planned scenario._")

st.divider()

st.subheader("🔍 How DF is being estimated")

if t10k_actual_min and t10k_pred_min and t10k_pred_min > 0:
    gap_10k = (t10k_actual_min - t10k_pred_min) / t10k_pred_min
    gap_10k_pct = gap_10k * 100

    if ats_plan and df_plan:
        st.markdown(
            f"""
**10K gap**

- Actual 10K: `{t10k_actual_str}`  
- Predicted 10K: `{t10k_pred_str}`  
- Gap = **{gap_10k_pct:.1f}% slower** than predicted  

**DF model**

> `DF = 1.768 - 0.049·ATS - 0.0000069·Elev_year + 0.118·Gap_10k`

(where `Gap_10k` is in fractional form, e.g. 0.10 = 10%)

- Annual elevation = `{annual_elev_m:,.0f}` m  

**Manual ATS scenario**

- ATS = `{ats:.2f}` km/h → DF ≈ **{df_est_manual:.3f}** (before any override)

**Planned-week scenario**

- ATS (planned) = `{ats_plan:.2f}` km/h → DF ≈ **{df_plan:.3f}**
"""
        )
    else:
        st.markdown(
            f"""
**10K gap**

- Actual 10K: `{t10k_actual_str}`  
- Predicted 10K: `{t10k_pred_str}`  
- Gap = **{gap_10k_pct:.1f}% slower** than predicted  

**DF model**

> `DF = 1.768 - 0.049·ATS - 0.0000069·Elev_year + 0.118·Gap_10k`

- Annual elevation = `{annual_elev_m:,.0f}` m  
- Manual ATS = `{ats:.2f}` km/h → DF ≈ **{df_est_manual:.3f}**
"""
        )
else:
    st.info("Enter valid 10K actual & predicted times in the sidebar to see DF details.")

st.caption(
    "Use the workout planner to experiment: more Z3–Z4 at a sustainable ATS should tighten your 10K gap over time, "
    "nudging DF toward ~0.95–1.00 and improving the marathon prediction."
)