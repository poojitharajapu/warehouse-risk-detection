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
cols=st.columns(6)
for col,label,key in zip(cols,["Warehouses","Zones","Sensors","Inventory lots","Sensor readings","Occupancy readings"],["warehouses","zones","sensors","inventory_lots","sensor_readings","occupancy_readings"]):
    col.metric(label, f"{counts.get(key,0):,}")
st.subheader("Validation")
st.metric("Overall status",report["overall_status"],delta=f"{report['failed_checks']} failed checks")
st.dataframe(report["checks"],width="stretch",hide_index=True)

def read_rows(name, limit=None):
    path=folder/f"{name}.csv"
    if not path.exists(): return []
    with path.open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f); return [r for _,r in zip(range(limit),reader)] if limit else list(reader)

alarms=read_rows("alarms")
st.subheader("Alarms")
st.dataframe(alarms,width="stretch",hide_index=True)
active=[a for a in alarms if a.get('status') in ('OPEN','ACKNOWLEDGED')]
severity_counts={severity:sum(a.get('severity')==severity for a in active) for severity in ('HIGH','MEDIUM','LOW')}
st.write("Active alert counts by severity")
st.bar_chart(severity_counts)
st.write("Current alerts grouped by risk type")
for risk in sorted({a.get('risk_type','UNKNOWN') for a in active}):
    with st.expander(risk):
        st.dataframe([a for a in active if a.get('risk_type')==risk],width="stretch",hide_index=True)
links=read_rows("alarm_lots")
lots={x["lot_id"]:x for x in read_rows("inventory_lots")}
if links:
    st.subheader("Affected inventory links")
    st.dataframe([dict(alarm_id=x["alarm_id"],**lots.get(x["lot_id"],{"lot_id":x["lot_id"]})) for x in links],width="stretch",hide_index=True)

st.subheader("Human occupancy and zone capacity")
zones=read_rows("zones")
occupancy=read_rows("occupancy_readings")
if zones and occupancy:
    zone_info={z['zone_id']:z for z in zones}
    latest={}
    for row in occupancy:
        if row['zone_id'] not in latest or row['timestamp']>latest[row['zone_id']]['timestamp']:
            latest[row['zone_id']]=row
    occupancy_view=[]
    for zid,row in latest.items():
        zone=zone_info[zid]; limit=int(zone['occupancy_capacity_persons']); people=int(row['people_count'])
        occupancy_view.append({'warehouse_id':zone['warehouse_id'],'zone_id':zid,'timestamp':row['timestamp'],'people_present':people,'occupancy_limit_persons':limit,'status':'OVER CAPACITY' if people>limit else 'WITHIN CAPACITY'})
    st.dataframe(occupancy_view,width="stretch",hide_index=True)
    st.line_chart(pd.DataFrame(occupancy_view).set_index('zone_id')[['people_present','occupancy_limit_persons']])
else:
    st.info("Occupancy files are missing. Generate a dataset that includes occupancy_readings.csv.")

st.subheader("Alarm, inspection, and remediation history")
history=read_rows("state_history")
if history:
    st.dataframe(history,width="stretch",hide_index=True)
else:
    st.info("No lifecycle history was found. Generate a dataset with state_history.csv.")

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
