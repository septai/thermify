"""Interactive tuner for temperature control domain logic with 2D and 3D plots.

Run with:
    streamlit run scripts/tune_temperature_control.py

Adjust sliders to modify TemperatureControlConstants and see real-time updates
to 2D plots (price vs target, indoor temp vs target) and a 3D surface plot
(price and indoor temp vs target temperature).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import plotly.subplots
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from domain.how_much_to_heat import (  # noqa: E402
    TemperatureControlConstants,
    compute_target_temperature,
)

st.set_page_config(
    page_title="Temperature Control Tuner",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Temperature Control Tuner")
st.markdown(
    "Adjust the constants below to see real-time changes in target temperature "
    "across different price and indoor temperature ranges."
)

# Sidebar sliders for all constants
st.sidebar.header("Constants")

nominal_indoor_temperature = st.sidebar.slider(
    "Nominal Indoor Temperature (°C)",
    min_value=10.0,
    max_value=25.0,
    value=14.5,
    step=0.1,
)

nominal_target_temperature = st.sidebar.slider(
    "Nominal Target Temperature (°C)",
    min_value=15.0,
    max_value=21.0,
    value=17.0,
    step=0.1,
)

min_target_temperature = st.sidebar.slider(
    "Min Target Temperature (°C)",
    min_value=12.0,
    max_value=18.0,
    value=14.0,
    step=0.1,
)

max_target_temperature = st.sidebar.slider(
    "Max Target Temperature (°C)",
    min_value=19.0,
    max_value=22.0,
    value=20.0,
    step=0.1,
)

reference_price = st.sidebar.slider(
    "Reference Price (snt/kWh)",
    min_value=1.0,
    max_value=20.0,
    value=5.0,
    step=0.1,
)

low_temperature_protection_margin = st.sidebar.slider(
    "Low Temperature Protection Margin (°C)",
    min_value=0.1,
    max_value=3.0,
    value=1.5,
    step=0.1,
)

price_gain = st.sidebar.slider(
    "Price Gain",
    min_value=0.5,
    max_value=3.0,
    value=1.2,
    step=0.1,
)

indoor_temperature_gain = st.sidebar.slider(
    "Indoor Temperature Gain",
    min_value=0.5,
    max_value=4.0,
    value=1.5,
    step=0.1,
)

low_temperature_boost = st.sidebar.slider(
    "Low Temperature Boost",
    min_value=1.0,
    max_value=6.0,
    value=3.0,
    step=0.1,
)

st.sidebar.divider()
st.sidebar.header("Plot Anchors")

price_plot_indoor_temperature = st.sidebar.slider(
    "Indoor Temperature for Price Plot (°C)",
    min_value=10.0,
    max_value=25.0,
    value=nominal_indoor_temperature,
    step=0.1,
)

indoor_plot_price = st.sidebar.slider(
    "Price for Indoor Plot (snt/kWh)",
    min_value=1.0,
    max_value=100.0,
    value=reference_price,
    step=0.1,
)

# Build constants from sliders
constants = TemperatureControlConstants(
    nominal_target_temperature=nominal_target_temperature,
    nominal_indoor_temperature=nominal_indoor_temperature,
    min_target_temperature=min_target_temperature,
    max_target_temperature=max_target_temperature,
    reference_price=reference_price,
    low_temperature_protection_margin=low_temperature_protection_margin,
    price_gain=price_gain,
    indoor_temperature_gain=indoor_temperature_gain,
    low_temperature_boost=low_temperature_boost,
)

# Display current constants as JSON
with st.sidebar.expander("Current Constants (JSON)"):
    const_dict = {
        "nominal_target_temperature": round(constants.nominal_target_temperature, 3),
        "nominal_indoor_temperature": round(constants.nominal_indoor_temperature, 3),
        "min_target_temperature": round(constants.min_target_temperature, 3),
        "max_target_temperature": round(constants.max_target_temperature, 3),
        "reference_price": round(constants.reference_price, 3),
        "low_temperature_protection_margin": round(constants.low_temperature_protection_margin, 3),
        "price_gain": round(constants.price_gain, 3),
        "indoor_temperature_gain": round(constants.indoor_temperature_gain, 3),
        "low_temperature_boost": round(constants.low_temperature_boost, 3),
    }
    st.json(const_dict)

# Generate plot data
price_range = np.linspace(-1.0, 100.0, 100)
indoor_temp_range = np.linspace(10.0, 25.0, 100)
price_grid, indoor_grid = np.meshgrid(price_range, indoor_temp_range)
target_grid = np.zeros_like(price_grid)

for i in range(price_grid.shape[0]):
    for j in range(price_grid.shape[1]):
        target_grid[i, j] = compute_target_temperature(
            price=price_grid[i, j],
            indoor_temperature=indoor_grid[i, j],
            constants=constants,
        )

# Fixed values for 2D plots
fixed_price = indoor_plot_price
fixed_indoor_temp = price_plot_indoor_temperature

target_vs_price = np.array(
    [
        compute_target_temperature(
            price=p, indoor_temperature=fixed_indoor_temp, constants=constants
        )
        for p in price_range
    ]
)

target_vs_indoor = np.array(
    [
        compute_target_temperature(price=fixed_price, indoor_temperature=t, constants=constants)
        for t in indoor_temp_range
    ]
)

# Create subplots
fig = plotly.subplots.make_subplots(
    rows=1,
    cols=3,
    subplot_titles=(
        f"Target vs Price (Indoor={fixed_indoor_temp:.1f}°C)",
        f"Target vs Indoor Temp (Price={fixed_price:.1f} snt/kWh)",
        "Target vs Price & Indoor Temperature (3D)",
    ),
    specs=[[{"type": "scatter"}, {"type": "scatter"}, {"type": "surface"}]],
    row_heights=[1],
)

# 3D Surface plot
fig.add_trace(
    go.Surface(
        x=price_range,
        y=indoor_temp_range,
        z=target_grid,
        colorscale="Viridis",
        name="Target Temperature",
    ),
    row=1,
    col=3,
)

# 2D: Price vs Target
fig.add_trace(
    go.Scatter(
        x=price_range,
        y=target_vs_price,
        mode="lines",
        name="Target Temp",
        line=dict(color="#7dd3fc", width=3),
    ),
    row=1,
    col=1,
)
fig.update_xaxes(title_text="Price (snt/kWh)", row=1, col=1)
fig.update_yaxes(title_text="Target Temp (°C)", row=1, col=1)

# 2D: Indoor Temp vs Target
fig.add_trace(
    go.Scatter(
        x=indoor_temp_range,
        y=target_vs_indoor,
        mode="lines",
        name="Target Temp",
        line=dict(color="#fbbf24", width=3),
        showlegend=False,
    ),
    row=1,
    col=2,
)
fig.update_xaxes(title_text="Indoor Temperature (°C)", row=1, col=2)
fig.update_yaxes(title_text="Target Temp (°C)", row=1, col=2)

# Update layout
fig.update_layout(
    height=1000,
    showlegend=True,
    title_text="Temperature Control Analysis",
    hovermode="closest",
)

# Update 3D scene
fig.update_scenes(
    xaxis_title="Price (snt/kWh)",
    yaxis_title="Indoor Temp (°C)",
    zaxis_title="Target Temp (°C)",
    camera=dict(eye=dict(x=1.5, y=1.5, z=1.3)),
)

st.plotly_chart(fig, use_container_width=True)

# Info section
st.markdown("---")
st.markdown(
    """
**How to use:**
- Adjust sliders on the left to modify constants
 - Top-left chart: See how target temperature changes with electricity price
  (indoor temp fixed by slider)
- Top-right chart: 3D surface showing target temperature as a function of both
  price and indoor temperature
 - Bottom-left chart: See how target temperature changes with indoor
  temperature (price fixed by slider)

**Interpretation:**
- Steeper curves = more price/temperature sensitivity
- Flat regions = target temperature hitting min/max bounds
"""
)

