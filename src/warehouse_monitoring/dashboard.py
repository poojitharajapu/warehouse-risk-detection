"""Optional, read-only Streamlit view over an already generated output folder."""
import csv, json
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Warehouse Risk Monitor", layout="wide")
st.title("Warehouse Monitoring and Risk Alerts")
st.caption("Read-only view of generated CSVs and their validation report.")
folder=Path(st.sidebar.text_input("Output folder", "outputs/baseline"))
manifest_path=folder/"manifest.json"
report_path=folder/"validation_report.json"
if not manifest_path.exists() or not report_path.exists():
    st.info("Generate and validate a dataset first, then enter its output folder above.")
    st.stop()
manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
report=json.loads(report_path.read_text(encoding="utf-8"))
counts=manifest["row_counts"]
cols=st.columns(4)
for col,label,key in zip(cols,["Warehouses","Zones","Sensors","Inventory lots"],["warehouses","zones","sensors","inventory_lots"]):
    col.metric(label, f"{counts.get(key,0):,}")
st.subheader("Validation")
st.metric("Overall status",report["overall_status"],delta=f"{report['failed_checks']} failed checks")
st.dataframe(report["checks"],use_container_width=True,hide_index=True)

def read_rows(name, limit=None):
    path=folder/f"{name}.csv"
    if not path.exists(): return []
    with path.open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f); return [r for _,r in zip(range(limit),reader)] if limit else list(reader)

alarms=read_rows("alarms")
st.subheader("Alarms")
st.dataframe(alarms,use_container_width=True,hide_index=True)
links=read_rows("alarm_lots")
lots={x["lot_id"]:x for x in read_rows("inventory_lots")}
if links:
    st.subheader("Affected inventory links")
    st.dataframe([dict(alarm_id=x["alarm_id"],**lots.get(x["lot_id"],{"lot_id":x["lot_id"]})) for x in links],use_container_width=True,hide_index=True)

st.subheader("Sensor trend")
sensors=read_rows("sensors")
if sensors:
    sid=st.selectbox("Sensor",[s["sensor_id"] for s in sensors])
    points=[]
    with (folder/"sensor_readings.csv").open(newline="",encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["sensor_id"]==sid:
                points.append({"timestamp":row["timestamp"],"value":float(row["value"])})
                if len(points)>=2000: break
    st.line_chart(pd.DataFrame(points),x="timestamp",y="value")
    st.caption("The chart shows up to the first 2,000 stored observations for the selected sensor.")
else:
    st.info("No sensor table is available in this output folder.")
