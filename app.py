import math
from typing import Optional, List, Dict

import streamlit as st
import pandas as pd


# ---------- Utility functions ----------

def parse_time_to_min(time_str: str) -> Optional[float]:
    """
    Parse 'mm:ss' or 'h:mm:ss' into minutes (float).
    Returns None if empty or invalid.
    """
    if not time_str:
        return None
    try:
        parts = [int(p) for p in time_str.strip().split(":")]
        if len(parts) == 2:
            m, s = parts
            h = 0
        elif len(parts) == 3:
            h, m, s = parts
        else:
            return None
        return h * 60 + m + s / 60.0
    except Exception:
        return None


def format_min_to_hms(minutes: float) -> str:
    total_seconds = int(round(minutes * 60))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def speed_from_time(distance_km: float, time_min: float) -> float:
    """km/h given km and minutes."""
    return distance_km / (time_min / 60.0)


def pace_from_speed(speed_kmh: float) -> float:
    """Return pace in min/km from speed (km/h)."""
    return 60.0 / speed_kmh


def format_pace(pace_min_per_km: float) -> str:
    m = int(pace_min_per_km)
    s = int(round((pace_min_per_km - m) * 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m:d}:{s:02d} /km"


# ---------- Durability & marathon model ----------

def estimate_df_from_decay_and_volume(
    ten_k_min: Optional[float],
    marathon_min: Optional[float],
    annual_km: float,
) -> float:
    """
    DF combines:
    1) 10K -> Marathon decay (base durability)
    2) Annual volume effect around an 'ideal' 6000 km/year

    - DF ~ 1.0 is 'typical'
    - DF > 1.0 = more durable (less slowdown, higher chance of negative split)
    - DF < 1.0 = less durable (bigger fade)

    We clamp to [0.75, 1.30] to avoid wild values.
    """
    # 1. Base from 10K→marathon decay, if both are available
    if ten_k_min is not None and marathon_min is not None:
        # Riegel-style prediction of marathon from 10K
        riegel_exp = 1.06
        dist_ratio = 42.195 / 10.0
        predicted_mar_min = ten_k_min * (dist_ratio ** riegel_exp)

        decay_ratio = marathon_min / predicted_mar_min  # >1 means slower than Riegel
        # Assume a "typical" good marathoner has decay_ratio ≈ 1.08
        typical_decay = 1.08

        # Map decay_ratio to DF_base: 1.08 -> 1.00
        # If decay is 0.10 worse (1.18), DF ≈ 0.85, if 0.10 better (0.98), DF ≈ 1.15
        k = 1.5
        df_base = 1.0 + (typical_decay - decay_ratio) * k
    else:
        # If we don't know the decay, start neutral
        df_base = 1.0

    # 2. Volume factor around 6000 km/year
    ideal_km = 6000.0
    vol_ratio = annual_km / ideal_km
    # For most runners:
    #   ~3000 km -> ~-7.5% DF
    #   ~6000 km -> neutral
    #   ~9000–10000 km (Kelvin-esque) -> +7–10% DF
    vol_factor = 1.0 + 0.15 * (vol_ratio - 1.0)

    df = df_base * vol_factor

    # Clamp
    df = max(0.75, min(1.30, df))
    return df


def marathon_time_from_ats_df(ats_kmh: float, df: float) -> float:
    """
    Marathon prediction in MINUTES from ATS (km/h) and DF.

    ATS is ~70% of performance,
    DF (durability) explains the remaining ~30%.

    MPT (min) = (4666 * ATS^-1.33) / DF + 8
    """
    base = 4666.0 * (ats_kmh ** -1.33)
    return base / df + 8.0


# ---------- Plan templates ----------

PLAN_TEMPLATES: Dict[str, List[Dict]] = {
    # Distances are percentages of weekly_km
    # zone: Z1 (easy), Z2 (steady), Z3 (MP/sub-threshold),
    #       Z4 (threshold), Z5 (intervals)
    "Pfitzinger": [
        {"day": "Mon", "name": "Recovery", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Tue", "name": "LT / Tempo", "zone": "Z4", "dist_pct": 0.15},
        {"day": "Wed", "name": "Medium Long", "zone": "Z2", "dist_pct": 0.18},
        {"day": "Thu", "name": "Recovery", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Fri", "name": "General Aerobic", "zone": "Z2", "dist_pct": 0.12},
        {"day": "Sat", "name": "VO₂ / Intervals", "zone": "Z5", "dist_pct": 0.10},
        {"day": "Sun", "name": "Long Run (with MP finish)", "zone": "Z2_Z3", "dist_pct": 0.25},
    ],
    "Daniels": [
        {"day": "Mon", "name": "Easy + strides", "zone": "Z1", "dist_pct": 0.12},
        {"day": "Tue", "name": "Threshold (T) session", "zone": "Z4", "dist_pct": 0.16},
        {"day": "Wed", "name": "Medium Long", "zone": "Z2", "dist_pct": 0.18},
        {"day": "Thu", "name": "Easy", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Fri", "name": "Intervals (I) / VO₂", "zone": "Z5", "dist_pct": 0.14},
        {"day": "Sat", "name": "Easy", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Sun", "name": "Long Run", "zone": "Z2_Z3", "dist_pct": 0.20},
    ],
    "Canova": [
        {"day": "Mon", "name": "Easy regeneration", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Tue", "name": "Specific Marathon (MP + fast finish)", "zone": "Z3_Z4", "dist_pct": 0.20},
        {"day": "Wed", "name": "Medium Long easy", "zone": "Z2", "dist_pct": 0.18},
        {"day": "Thu", "name": "Easy", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Fri", "name": "Special Block / Alternations", "zone": "Z3_Z4", "dist_pct": 0.17},
        {"day": "Sat", "name": "Easy", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Sun", "name": "Long Run with segments at MP", "zone": "Z2_Z3", "dist_pct": 0.15},
    ],
    "Tinman": [
        {"day": "Mon", "name": "Easy", "zone": "Z1", "dist_pct": 0.14},
        {"day": "Tue", "name": "Cruise Intervals (CV)", "zone": "Z4", "dist_pct": 0.16},
        {"day": "Wed", "name": "Easy", "zone": "Z1", "dist_pct": 0.14},
        {"day": "Thu", "name": "Tempo / Steady", "zone": "Z3", "dist_pct": 0.16},
        {"day": "Fri", "name": "Easy", "zone": "Z1", "dist_pct": 0.10},
        {"day": "Sat", "name": "Short Intervals / Speed", "zone": "Z5", "dist_pct": 0.10},
        {"day": "Sun", "name": "Long Run", "zone": "Z2_Z3", "dist_pct": 0.20},
    ],
}


def zone_speed_from_mp(mp_speed: float, zone: str) -> float:
    """
    Return target speed in km/h for a given zone,
    as a percentage of marathon-pace speed.
    """
    if zone == "Z1":
        factor = 0.78   # easy / recovery
    elif zone == "Z2":
        factor = 0.88   # steady aerobic
    elif zone == "Z3":
        factor = 0.98   # MP / slightly faster
    elif zone == "Z4":
        factor = 1.08   # threshold / CV
    elif zone == "Z5":
        factor = 1.18   # faster than threshold
    elif zone == "Z2_Z3":
        factor = 0.93   # blend of Z2 & Z3
    elif zone == "Z3_Z4":
        factor = 1.03   # blend of Z3 & Z4
    else:
        factor = 0.88
    return mp_speed * factor


def expand_plan(
    plan_name: str,
    weekly_km: float,
    mp_speed: float,
) -> pd.DataFrame:
    rows = []
    template = PLAN_TEMPLATES[plan_name]

    for block in template:
        dist_km = weekly_km * block["dist_pct"]
        # If it's a mixed zone, we still assign one "headline" pace
        z = block["zone"]
        spd = zone_speed_from_mp(mp_speed, z)
        pace = pace_from_speed(spd)
        rows.append(
            {
                "Day": block["day"],
                "Workout": block["name"],
                "Zone": z,
                "Distance_km": round(dist_km, 1),
                "Target_pace": format_pace(pace),
                "Target_speed_kmh": round(spd, 2),
            }
        )
    return pd.DataFrame(rows)


def compute_weekly_ats(df: pd.DataFrame) -> float:
    """Distance-weighted ATS for the generated week."""
    total_km = df["Distance_km"].sum()
    if total_km == 0:
        return 0.0
    # Use 60 / pace_min_per_km via parsing 'm:ss /km'
    speeds = []
    for _, row in df.iterrows():
        pace_str = row["Target_pace"].split()[0]  # 'm:ss'
        pace_min = parse_time_to_min(pace_str)
        if pace_min is None or pace_min <= 0:
            continue
        speeds.append(speed_from_time(row["Distance_km"], row["Distance_km"] * pace_min))
    # If everything went fine, weighted speed is just sum(distance)/sum(time)
    total_time_h = 0.0
    for _, row in df.iterrows():
        pace_str = row["Target_pace"].split()[0]
        pace_min = parse_time_to_min(pace_str)
        if pace_min is None or pace_min <= 0:
            continue
        time_h = row["Distance_km"] * pace_min / 60.0
        total_time_h += time_h
    if total_time_h == 0:
        return 0.0
    ats = df["Distance_km"].sum() / total_time_h
    return ats


def summarize_zones(df: pd.DataFrame) -> pd.DataFrame:
    zone_km = {}
    for _, row in df.iterrows():
        z = row["Zone"]
        km = row["Distance_km"]
        # Split mixed zones evenly
        if z in ("Z2_Z3", "Z3_Z4"):
            parts = z.split("_")
            for part in parts:
                zone_km[part] = zone_km.get(part, 0.0) + km * 0.5
        else:
            zone_km[z] = zone_km.get(z, 0.0) + km

    rows = []
    total = sum(zone_km.values())
    for z in sorted(zone_km.keys()):
        pct = 100.0 * zone_km[z] / total if total > 0 else 0
        desc = {
            "Z1": "Easy / Recovery",
            "Z2": "Steady Aerobic",
            "Z3": "Marathon / Sub-threshold",
            "Z4": "Threshold / CV",
            "Z5": "Intervals / Speed",
        }.get(z, "")
        rows.append(
            {
                "Zone": z,
                "Description": desc,
                "km": round(zone_km[z], 1),
                "% of week": round(pct, 1),
            }
        )
    return pd.DataFrame(rows)


# ---------- Streamlit UI ----------

st.title("Marathon ATS + Durability Planner (Simplified)")

st.markdown(
    """
This tool builds a **weekly marathon training template** for you from a classic program
(**Pfitzinger, Daniels, Canova, Tinman**) and your own metrics.

We treat:
- **ATS (Average Training Speed)** as ~**70%** of marathon performance  
- **DF (Durability Factor)** as the remaining **30%**: how well you *hold* your speed into the marathon  
"""
)

st.sidebar.header("1. Recent Performances & Volume")

ten_k_str = st.sidebar.text_input("Recent 10K time (mm:ss or h:mm:ss)", value="41:32")
marathon_str = st.sidebar.text_input(
    "Recent marathon time (optional, mm:ss or h:mm:ss)", value=""
)
annual_km = st.sidebar.number_input("Annual volume (km/year)", min_value=500, max_value=12000, value=4300, step=100)

ten_k_min = parse_time_to_min(ten_k_str)
marathon_min = parse_time_to_min(marathon_str) if marathon_str else None

if ten_k_min is None:
    st.error("Please enter a valid 10K time (mm:ss or h:mm:ss).")
    st.stop()

ten_k_speed = speed_from_time(10.0, ten_k_min)
ten_k_pace = pace_from_speed(ten_k_speed)

st.sidebar.markdown(
    f"**10K pace**: `{format_pace(ten_k_pace)}`  \n"
    f"**10K speed**: `{ten_k_speed:.2f} km/h`"
)

st.sidebar.header("2. Target Training Level")

plan_name = st.sidebar.selectbox(
    "Select training program",
    ["Pfitzinger", "Daniels", "Canova", "Tinman"],
)

weekly_km = st.sidebar.slider(
    "Target weekly distance (km)",
    min_value=60,
    max_value=180,
    value=112,
    step=2,
)

target_ats = st.sidebar.slider(
    "Target ATS for this phase (km/h)",
    min_value=10.0,
    max_value=16.0,
    value=13.2,
    step=0.1,
)

# Durability from decay + volume
df_est = estimate_df_from_decay_and_volume(ten_k_min, marathon_min, annual_km)

st.sidebar.header("3. ATS + DF Model")

st.sidebar.markdown(
    f"""
- **Estimated DF**: `{df_est:.3f}`  
- **Interpretation**:  
  - `~1.00` = typical durability  
  - `>1.00` = very durable, likely to **hold pace / negative split**  
  - `<1.00` = more fade risk, marathon time drifts slower  
"""
)

predicted_mar_min = marathon_time_from_ats_df(target_ats, df_est)
predicted_mar_pace = pace_from_speed(42.195 / (predicted_mar_min / 60.0))

st.subheader("Model Summary")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Target ATS", f"{target_ats:.2f} km/h")
with col2:
    st.metric("Estimated DF", f"{df_est:.3f}")
with col3:
    st.metric("Marathon Prediction", format_min_to_hms(predicted_mar_min))

st.markdown(
    f"- **Marathon pace (MP)**: `{predicted_mar_pace}`  \n"
    f"- We treat **ATS** as the main engine (~70% of your time), and **DF** as how well your training lets you *keep* that speed (~30%)."
)

# Compute MP speed and build weekly plan
mp_speed = 42.195 / (predicted_mar_min / 60.0)
week_df = expand_plan(plan_name, weekly_km, mp_speed)
week_ats = compute_weekly_ats(week_df)
zone_summary = summarize_zones(week_df)

st.subheader(f"Weekly Plan – {plan_name}")

st.markdown(
    f"""
**Weekly distance**: `{weekly_km:.1f} km`  
**Plan ATS (from these workouts)**: `{week_ats:.2f} km/h`  

If the plan ATS is below your target ATS of `{target_ats:.2f} km/h`,
you can either **raise weekly km** slightly or **bump the ATS slider** and re-generate.
"""
)

st.dataframe(week_df, hide_index=True)

st.subheader("Zone Breakdown (relative to MP)")

st.dataframe(zone_summary, hide_index=True)

st.markdown(
    """
**Zone definitions (approx. as a % of MP speed):**

- `Z1` – Easy / Recovery: **70–80%** of MP speed  
- `Z2` – Steady Aerobic: **80–90%** of MP speed  
- `Z3` – Marathon / Sub-threshold: **95–105%** of MP speed  
- `Z4` – Threshold / CV: **105–115%** of MP speed  
- `Z5` – Intervals / Speed: **>115%** of MP speed  
"""
)

st.subheader("How the Durability (DF) Piece Works")

st.markdown(
    f"""
We estimate **DF** using two ingredients:

1. **10K → Marathon decay**  
   - Compare your **real marathon time** to a Riegel-style prediction from your 10K.  
   - If you slow down **less** than typical, DF > 1.0 (super durable).  
   - If you slow down **more**, DF < 1.0 (fade risk).

2. **Annual volume effect (around ~6000 km/year)**  
   - ~6000 km/year → neutral volume effect  
   - Much higher volume (e.g. **Kelvin Kiptum level**) → DF nudged **up**  
   - Much lower volume (e.g. **4k/year Adam-style**) → DF nudged **down**  

Finally, marathon time is modeled as a power law of Average Training speed adjusted for durability.

So:
- Raise **ATS** → faster marathon (bigger effect, ~70%)  
- Improve **DF** (better decay + smarter volume) → more time shaved off (~30%)  
"""
)