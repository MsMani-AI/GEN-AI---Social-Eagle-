import math
import streamlit as st


def calculate_arc_energy(voltage, current, speed_mm_min):
    return voltage * current * 60 / (1000 * speed_mm_min)


st.set_page_config(page_title="Welding Heat Input Calculator")
st.title("Welding Heat Input Calculator")
st.caption("Conventional V × A calculation for steady arc welding. Results in kJ/mm.")

processes = {
    "MAG / GMAW — 135": 0.8,
    "MIG / GMAW — 131": 0.8,
    "TIG / GTAW — 141": 0.6,
    "MMA / SMAW — 111": 0.8,
    "FCAW — flux cored arc welding": 0.8,
    "SAW — submerged arc welding": 1.0,
    "Plasma arc welding": 0.6,
}
process = st.selectbox("Welding process", list(processes))
method = st.radio("Travel speed entry", ["Direct speed", "Weld length and arc time"])

with st.form("heat_input"):
    voltage = st.number_input("Arc voltage (V)", min_value=0.0, value=20.0, step=0.1)
    current = st.number_input("Welding current (A)", min_value=0.0, value=200.0, step=1.0)
    if method == "Direct speed":
        speed = st.number_input("Travel speed", min_value=0.0, value=200.0, step=1.0)
        unit = st.selectbox("Travel speed unit", ["mm/min", "mm/s", "cm/min", "in/min"])
    else:
        length = st.number_input("Weld length (mm)", min_value=0.0, value=100.0, step=1.0)
        seconds = st.number_input("Arc-on time (seconds)", min_value=0.0, value=30.0, step=1.0)
    k = st.number_input("EN/ISO thermal efficiency factor (k)", min_value=0.01,
                        max_value=1.0, value=processes[process], step=0.01)
    reference = st.text_input("WPS / weld / pass reference (optional)")
    submitted = st.form_submit_button("Calculate")

if "heat_records" not in st.session_state:
    st.session_state.heat_records = []

if submitted:
    valid = voltage > 0 and current > 0 and math.isfinite(voltage) and math.isfinite(current)
    if method == "Direct speed":
        speed_mm_min = speed * {"mm/min": 1, "mm/s": 60, "cm/min": 10, "in/min": 25.4}[unit]
        valid = valid and speed_mm_min > 0 and math.isfinite(speed_mm_min)
    else:
        valid = valid and length > 0 and seconds > 0 and math.isfinite(length) and math.isfinite(seconds)
        speed_mm_min = length * 60 / seconds if valid else 0
    if not valid:
        st.error("Enter positive, finite voltage, current, and speed (or length and time).")
    else:
        arc_energy = calculate_arc_energy(voltage, current, speed_mm_min)
        st.session_state.heat_records.append({
            "Reference": reference.strip(), "Process": process,
            "Voltage (V)": voltage, "Current (A)": current,
            "Speed (mm/min)": speed_mm_min, "EN/ISO k": k,
            "ASME conventional (kJ/mm)": arc_energy,
            "EN/ISO heat input (kJ/mm)": k * arc_energy,
        })

if st.session_state.heat_records:
    latest = st.session_state.heat_records[-1]
    st.subheader("Last calculated result")
    c1, c2 = st.columns(2)
    c1.metric("ASME conventional heat input", f"{latest['ASME conventional (kJ/mm)']:.3f} kJ/mm")
    c2.metric("EN/ISO heat input", f"{latest['EN/ISO heat input (kJ/mm)']:.3f} kJ/mm")
    st.caption(f"Result process: {latest['Process']} | Speed: {latest['Speed (mm/min)']:.2f} mm/min | k: {latest['EN/ISO k']:.2f}")
    st.subheader("Calculation history — current session")
    st.dataframe(st.session_state.heat_records)

with st.expander("Formula and method"):
    st.write("Arc energy / conventional ASME value = V × A × 60 ÷ (1000 × travel speed in mm/min).")
    st.write("EN/ISO heat input = k × arc energy. No efficiency multiplier is applied to the conventional ASME value; this does not mean physical efficiency is 100%.")
    st.write("ISO 15614-1 permits either arc energy or heat input when the calculation method is documented. Use the method required by your approved WPS/WPQR.")
    st.write("Use measured energy or appropriate measured power for pulsed or complex waveform welding; multiplying average voltage and current can be inaccurate. This app implements only the conventional calculation.")
    st.write("Typical k factors: MIG/MAG, SMAW and FCAW 0.8; TIG and plasma 0.6; SAW 1.0. Confirm the applicable factor for your procedure.")
    st.write("History is temporary session storage. Results calculate energy only; they do not establish WPS compliance or qualification limits.")
    st.markdown("[Heat input and arc energy — TWI](https://www.twi-global.com/technical-knowledge/faqs/faq-what-is-the-difference-between-heat-input-and-arc-energy)")
    st.markdown("[ISO 15614-1:2017 — reference copy](https://weldcalc.ssab.com/sisStandards/ISO%2015614-1.pdf)")
