"""Streamlit entry point for the Winner Tilt AI read-only dashboard."""
from __future__ import annotations

import streamlit as st
from winner_tilt.dashboard import build_dashboard_view_model, load_dashboard_inputs

st.set_page_config(page_title="Winner Tilt AI Dashboard", layout="wide")
st.title("Winner Tilt AI — Dashboard Foundation")
st.caption("Read-only presentation layer. Research context is informational and never alters scoring, portfolio, or backtest decisions.")

try:
    vm = build_dashboard_view_model(load_dashboard_inputs())
except Exception as exc:  # fail closed for local UI users
    st.error(f"Dashboard failed closed: {exc}")
    st.stop()

for warning in vm["status"]["warnings"]:
    st.warning(warning)

c1, c2, c3 = st.columns(3)
c1.metric("Mode", vm["status"]["dashboard_mode"])
c2.metric("Portfolio as of", vm["status"]["portfolio_as_of_date"])
c3.metric("Backtest status", vm["status"]["backtest_validation_status"])

st.subheader("Top 15 holdings")
st.dataframe(vm["holdings"], use_container_width=True)
st.subheader("15 reserves")
st.dataframe(vm["reserves"], use_container_width=True)
st.subheader("Scores and ranks")
st.dataframe(vm["scores"], use_container_width=True)
st.subheader("Concentration summary")
st.json(vm["concentration"])
st.subheader("Backtest summary metrics")
st.json(vm["backtest"])
st.subheader("Research events — informational context only")
st.json(vm["research"])
st.subheader("Decision Journal — audit entries only")
st.caption("Journal entries are read-only, may be synthetic/prototype validation records, and are not investment evidence.")
st.dataframe(vm["journal"]["recent_entries"], use_container_width=True)
st.subheader("Decision Journal integrity")
st.json(vm["journal"]["integrity"])
st.subheader("Data freshness, source timestamps, and validation status")
st.dataframe(vm["freshness"], use_container_width=True)
