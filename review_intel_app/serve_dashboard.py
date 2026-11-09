"""Launch the dashboard with protected report retrieval routes in the same process."""
import os
from pathlib import Path
import streamlit as st
from report_downloads import routes

app = st.App(Path(__file__).with_name("app.py"), routes=routes)

if __name__ == "__main__":
    app.run(config={
        "server.port": int(os.environ.get("PORT", "8000")),
        "server.address": "0.0.0.0",
        "server.headless": True,
        "server.baseUrlPath": "dashboard",
        "browser.gatherUsageStats": False,
    })
