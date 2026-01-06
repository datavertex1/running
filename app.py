# app.py
import math
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Segment-Based ATS • Zones • DF Planner", layout="wide")

# -----------------------------
# Helpers
# -----------------------------
def pace_str_to_min_per_km(p: str) -> float:
    """
    Converts 'm:ss' (e.g., '4:30') to minutes per km as float.
    Accepts also '4.5' as 4.5 minutes.
    """
    p = str(p).strip()
    if p == "" or p.lower() in {"nan", "none"}:
        return float("nan")
    if ":" in p:
        mm, ss = p.split(":")
        return float(mm) + float(ss) / 60.0
    return float(p)

def min_per_km_to_kmh(mpk: float) -> float:
    return 60.0 / mpk

def format_hms(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"

def marathon_pred_seconds(ats_kmh: float, df: float) -> float:
    # Your formula: MPT = 4666 × (ATS)^-1.33 / DF
    if ats_kmh <= 0 or df <= 0:
        return float("nan")
    return 4666.0 * (ats_kmh ** (-1.33)) / df

ZONE_ORDER = ["Z1", "Z2", "Z3", "Z4", "Z5"]
ZONE_LABELS = {
    "Z1": "Z1 (Very easy)",
    "Z2": "Z2 (Easy aerobic)",
    "Z3": "Z3 (Moderate / steady)",
    "Z4": "Z4 (Threshold / marathon+)",
    "Z5": "Z5 (VO2 / fast)"
}

# -----------------------------
# Default week (segments)
# -----------------------------
default_segments = pd.DataFrame([
    # Example: 8×1k reps w/ 2' jog — expressed as segments
    {"Day": "Mon", "Workout": "Intervals", "Segment": "Warmup", "Distance_km": 3.0, "Pace": "5:10", "Zone": "Z2", "Notes": ""},
    {"Day": "Mon", "Workout": "Intervals", "Segment": "Reps total", "Distance_km": 8.0, "Pace": "4:05", "Zone": "Z4", "Notes": "8×1k"},
    {"Day": "Mon", "Workout": "Intervals", "Segment": "Jog recoveries", "Distance_km": 2.4, "Pace": "5:40", "Zone": "Z1", "Notes": "8×300m jog equiv"},
    {"Day": "Mon", "Workout": "Intervals", "Segment": "Cooldown", "Distance_km": 3.0, "Pace": "5:15", "Zone": "Z2", "Notes": ""},

    {"Day": "Tue", "Workout": "Easy", "Segment": "Easy run", "Distance_km": 12.0, "Pace": "5:10", "Zone": "Z2", "Notes": ""},

    {"Day": "Wed", "Workout": "Steady + strides", "Segment": "Easy", "Distance_km": 12.0, "Pace": "5:05", "Zone": "Z2", "Notes": ""},
    {"Day": "Wed", "Workout": "Steady + strides", "Segment": "Strides (tiny)", "Distance_km": 0.6, "Pace": "3:30", "Zone": "Z5", "Notes": "6×100m"},
    {"Day": "Wed", "Workout": "Steady + strides", "Segment": "Jog between strides", "Distance_km": 0.6, "Pace": "5:30", "Zone": "Z1", "Notes": ""},

    {"Day": "Thu", "Workout": "Cruise", "Segment": "Warmup", "Distance_km": 3.0, "Pace": "5:10", "Zone": "Z2", "Notes": ""},
    {"Day": "Thu", "Workout": "Cruise", "Segment": "Cruise reps", "Distance_km": 8.0, "Pace": "4:20", "Zone": "Z4", "Notes": "e.g., 4×2k"},
    {"Day": "Thu", "Workout": "Cruise", "Segment": "Easy between reps", "Distance_km": 2.0, "Pace": "5:15", "Zone": "Z1", "Notes": ""},
    {"Day": "Thu", "Workout": "Cruise", "Segment": "Cooldown", "Distance_km": 2.0, "Pace": "5:15", "Zone": "Z2", "Notes": ""},

    {"Day": "Sat", "Workout": "Long run", "Segment": "Long aerobic", "Distance_km": 22.0, "Pace": "4:55", "Zone": "Z2", "Notes": ""},
    {"Day": "Sat", "Workout": "Long run", "Segment": "Finish steady", "Distance_km": 4.0, "Pace": "4:25", "Zone": "Z3", "Notes": ""},

    {"Day": "Sun", "Workout": "Very easy", "Segment": "Very easy", "Distance_km": 8.0, "Pace": "5:35", "Zone": "Z1", "Notes": ""},
])

# -----------------------------
# UI
# -----------------------------
st.title("Segment-Based ATS • Zone Balance • DF Planner")
st.caption("Enter sessions as segments (distance + pace + zone). The app computes weekly ATS, zone distribution, DF, and predicted marathon time.")

if "segments" not in st.session_state:
    st.session_state.segments = default_segments

left, right = st.columns([1.35, 1])

with left:
    st.subheader("1) Build your week (segments table)")
    st.session_state.segments = st.data_editor(
        st.session_state.segments,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Distance_km": st.column_config.NumberColumn(min_value=0.0, step=0.1, format="%.1f"),
            "Pace": st.column_config.TextColumn(help="m:ss per km (e.g., 4:30) or decimal minutes (e.g., 4.5)"),
            "Zone": st.column_config.SelectboxColumn(options=ZONE_ORDER),
        }
    )

    st.markdown(
        "**Tip:** For intervals, you can enter totals (e.g., “Reps total 8.0 km @ 4:05 Z4”) and a separate recovery segment. "
        "You don’t need every split — just enough to represent time in zones."
    )

with right:
    st.subheader("2) DF + marathon prediction")

    df_mode = st.radio("DF mode", ["Manual DF", "Estimated DF (editable model)"], horizontal=True)

    if df_mode == "Manual DF":
        df_value = st.number_input("DF", min_value=0.50, max_value=2.00, value=1.03, step=0.01)
        st.caption("Use your DF directly (e.g., 1.03).")
    else:
        st.caption("Tunable DF estimator. Adjust coefficients until it matches your real outcomes.")
        base_df = st.number_input("Base DF", min_value=0.50, max_value=2.00, value=1.00, step=0.01)

        c1, c2 = st.columns(2)
        with c1:
            a_easy = st.number_input("a_easy (per 10% Z1+Z2)", value=0.020, step=0.005)
            a_long = st.number_input("a_long (per 10 km long run)", value=0.015, step=0.005)
        with c2:
            a_z4 = st.number_input("a_z4 penalty (per 10% Z4+Z5)", value=0.010, step=0.005)
            cap_df = st.number_input("Max DF cap", value=1.15, step=0.01)

        df_value = None

# -----------------------------
# Compute
# -----------------------------
seg = st.session_state.segments.copy()

# Normalize / compute pace, speed, time
pace_mpk = []
speed_kmh = []
time_min = []

for _, r in seg.iterrows():
    d = float(r.get("Distance_km", 0) or 0)
    p = r.get("Pace", "")
    if d <= 0:
        pace_mpk.append(float("nan"))
        speed_kmh.append(float("nan"))
        time_min.append(0.0)
        continue

    mpk = pace_str_to_min_per_km(p)
    pace_mpk.append(mpk)
    speed_kmh.append(min_per_km_to_kmh(mpk) if not math.isnan(mpk) and mpk > 0 else float("nan"))
    time_min.append(d * mpk if not math.isnan(mpk) else 0.0)

seg["Pace_min_per_km"] = pace_mpk
seg["Speed_kmh"] = speed_kmh
seg["Time_min"] = time_min

total_km = float(seg["Distance_km"].fillna(0).sum())
total_min = float(seg["Time_min"].fillna(0).sum())
total_hours = total_min / 60.0 if total_min > 0 else float("nan")
ats = (total_km / total_hours) if total_hours and total_hours > 0 else float("nan")

# Zone totals (km and time)
zone_km = seg.groupby("Zone")["Distance_km"].sum().reindex(ZONE_ORDER, fill_value=0.0)
zone_min = seg.groupby("Zone")["Time_min"].sum().reindex(ZONE_ORDER, fill_value=0.0)

z4_km = float(zone_km.get("Z4", 0.0))
z4_min = float(zone_min.get("Z4", 0.0))
z45_km = float(zone_km.get("Z4", 0.0) + zone_km.get("Z5", 0.0))
z12_km = float(zone_km.get("Z1", 0.0) + zone_km.get("Z2", 0.0))

z4_pct = (z4_km / total_km) if total_km > 0 else float("nan")
z45_pct = (z45_km / total_km) if total_km > 0 else float("nan")
easy_pct = (z12_km / total_km) if total_km > 0 else float("nan")

# Long run distance: max per (Day, Workout) group
if len(seg) > 0:
    workout_km = seg.groupby(["Day", "Workout"])["Distance_km"].sum()
    long_run_km = float(workout_km.max()) if len(workout_km) else 0.0
else:
    long_run_km = 0.0

# DF estimator (if used)
if df_mode == "Estimated DF (editable model)":
    df_est = base_df
    df_est += a_easy * ((easy_pct * 100.0) / 10.0)
    df_est += a_long * (long_run_km / 10.0)
    df_est -= a_z4 * ((z45_pct * 100.0) / 10.0)
    df_value = max(0.50, min(cap_df, df_est))

# Marathon prediction
mpt_sec = marathon_pred_seconds(ats, df_value)
mpt_str = format_hms(mpt_sec)

# -----------------------------
# Display summary
# -----------------------------
st.divider()
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total km", f"{total_km:.1f}")
m2.metric("Total time", f"{format_hms(total_min * 60)}")
m3.metric("ATS (km/h)", f"{ats:.2f}" if not math.isnan(ats) else "—")
m4.metric("Z4 volume", f"{z4_km:.1f} km ({z4_pct*100:.1f}%)" if total_km > 0 else "—")
m5.metric("Z1+Z2 (easy)", f"{z12_km:.1f} km ({easy_pct*100:.1f}%)" if total_km > 0 else "—")
m6.metric("DF", f"{df_value:.3f}" if df_value else "—")

st.subheader("Predicted marathon time (your formula)")
st.write(f"**MPT = 4666 × ATS^-1.33 / DF → {mpt_str}**")

# Zone distribution table
dist = pd.DataFrame({
    "Zone": [ZONE_LABELS[z] for z in ZONE_ORDER],
    "km": [float(zone_km.get(z, 0.0)) for z in ZONE_ORDER],
    "time": [format_hms(float(zone_min.get(z, 0.0)) * 60.0) for z in ZONE_ORDER],
})
dist["km_%"] = (dist["km"] / total_km * 100.0) if total_km > 0 else 0.0
st.subheader("Zone distribution (by distance)")
st.dataframe(dist, use_container_width=True)

with st.expander("Details / computed segment table"):
    show = seg[["Day","Workout","Segment","Distance_km","Pace","Zone","Time_min","Speed_kmh","Notes"]].copy()
    st.dataframe(show, use_container_width=True)

st.info(
    "How to raise ATS *and* Z4 volume without crushing DF:\n"
    "- Keep Z1/Z2 truly easy (protect DF).\n"
    "- Increase Z4 via **more frequent small doses** (e.g., 2×15' twice/week) before adding one huge Z4 day.\n"
    "- Make long run mostly Z2, add controlled Z3/Z4 finish only when recovered.\n"
    "- Avoid turning non-quality days into Z3 ‘gray zone’ unless it’s intentional."
)
