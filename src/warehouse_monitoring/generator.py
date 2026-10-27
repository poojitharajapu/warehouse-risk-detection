"""Deterministic synthetic records, with a streaming sensor-reading path."""
from __future__ import annotations
import random
from datetime import datetime, timedelta
from .config import Config

TABLE_NAMES=("warehouses", "zones", "sensors", "sensor_readings", "occupancy_readings", "door_events", "inventory_lots", "storage_requirements", "alarms", "inspections", "remediations", "alarm_lots", "sensor_zone_assignments", "state_history", "ground_truth")
def _dt(s): return datetime.fromisoformat(s)

def generate_core(config: Config):
    """Build small parent/reference tables; readings are generated separately."""
    now=_dt(config.start)
    t={k:[] for k in TABLE_NAMES}
    for wi in range(1,config.warehouses+1):
        wid=f"WH-{wi:03d}"
        t["warehouses"].append(dict(warehouse_id=wid,name=f"Warehouse {wi:03d}",region=("North","South","East","West")[(wi-1)%4],capacity_units=10000))
        for zi in range(1,config.zones_per_warehouse+1):
            zid=f"ZONE-{wid}-{zi:03d}"; cold=zi%2==1
            t["zones"].append(dict(zone_id=zid,warehouse_id=wid,name=f"Zone {zi:03d}",zone_type="COLD" if cold else "AMBIENT",capacity_units=1000,occupancy_capacity_persons=config.cold_zone_occupancy_limit if cold else config.ambient_zone_occupancy_limit))
            t["storage_requirements"].append(dict(requirement_id=f"REQ-{zid}",zone_id=zid,product_class="CHILLED" if cold else "AMBIENT",min_temp_c=2.0 if cold else 15.0,max_temp_c=8.0 if cold else 30.0,min_humidity_pct=20.0,max_humidity_pct=80.0))
            for si in range(1,config.sensors_per_zone+1):
                kind="TEMPERATURE" if si%2==1 else "HUMIDITY"; unit="C" if kind=="TEMPERATURE" else "PCT"
                sid=f"SNS-{zid}-{'TEMP' if unit=='C' else 'HUM'}-{si:02d}"
                t["sensors"].append(dict(sensor_id=sid,zone_id=zid,sensor_type=kind,unit=unit,status="ACTIVE"))
                t["sensor_zone_assignments"].append(dict(sensor_id=sid,zone_id=zid,valid_from=now.isoformat(),valid_to="",assignment_reason="Primary zone assignment"))
            door_open=now+timedelta(hours=1+((wi+zi)%12))
            door_seconds=60*(1+((wi*3+zi)%4))
            t["door_events"].append(dict(event_id=f"DOOR-{zid}-0001",zone_id=zid,opened_at=door_open.isoformat(),closed_at=(door_open+timedelta(seconds=door_seconds)).isoformat(),duration_seconds=door_seconds))
        for li in range(1,config.lots_per_warehouse+1):
            zone_num=(li-1)%config.zones_per_warehouse+1
            zid=f"ZONE-{wid}-{zone_num:03d}"
            cold=zone_num%2==1
            t["inventory_lots"].append(dict(lot_id=f"LOT-2026-{(wi-1)*config.lots_per_warehouse+li:06d}",warehouse_id=wid,zone_id=zid,product_class="CHILLED" if cold else "AMBIENT",quantity=config.lot_quantity,received_at=now.isoformat(),expires_at=(now+timedelta(days=60)).isoformat()))
    if config.inject_anomalies and t["inventory_lots"]:
        lot=t["inventory_lots"][0]
        ambient=next(z["zone_id"] for z in t["zones"] if z["warehouse_id"]==lot["warehouse_id"] and z["zone_type"]=="AMBIENT")
        lot["zone_id"]=ambient
        t["ground_truth"].append(dict(scenario_id="NEG-01",entity_id=lot["lot_id"],expected_issue="STORAGE_INCOMPATIBILITY",expected_label="DETECTED",details="Chilled lot placed in an ambient zone."))
        if len(t["sensors"])>1:
            sensor=t["sensors"][0]; other=next(z["zone_id"] for z in t["zones"] if z["zone_id"]!=sensor["zone_id"])
            t["sensor_zone_assignments"].append(dict(sensor_id=sensor["sensor_id"],zone_id=other,valid_from=now.isoformat(),valid_to="",assignment_reason=""))
            t["ground_truth"].append(dict(scenario_id="NEG-02",entity_id=sensor["sensor_id"],expected_issue="MULTIPLE_ZONE_MAPPING",expected_label="DETECTED",details="Sensor has two overlapping active zone mappings."))
    return t

def generate_occupancy(t, config: Config):
    """Generate hourly human counts; these counts are independent of stock quantities."""
    rng=random.Random(config.seed ^ 0x5F3759DF)
    now=_dt(config.start); zones={z['zone_id']:z for z in t['zones']}
    first_zone=t['zones'][0]['zone_id'] if t['zones'] else None
    for zone in t['zones']:
        limit=zone['occupancy_capacity_persons']
        for index in range(config.occupancy_samples_per_zone):
            # Normal occupancy fluctuates below the zone limit. One labeled case breaches it.
            people=max(0, round(limit*0.35)+((index*3+len(zone['zone_id']))%7)-3 + rng.randint(-1,1))
            if config.inject_anomalies and zone['zone_id']==first_zone and index==config.occupancy_samples_per_zone-1:
                people=limit+config.occupancy_anomaly_excess_people
                t['ground_truth'].append(dict(scenario_id='NEG-05',entity_id=f"OCC-{zone['zone_id']}-{index+1:04d}",expected_issue='OCCUPANCY_THRESHOLD',expected_label='DETECTED',details=f"People count {people} exceeds configured limit {limit}."))
            t['occupancy_readings'].append(dict(occupancy_reading_id=f"OCC-{zone['zone_id']}-{index+1:04d}",zone_id=zone['zone_id'],timestamp=(now+timedelta(hours=index)).isoformat(),people_count=people,measurement_method='SYNTHETIC_COUNT',quality='GOOD'))

def iter_readings(t, config: Config):
    """Yield observations in stable order; only the explicit outage enters ground truth."""
    rng=random.Random(config.seed); now=_dt(config.start)
    zones={z["zone_id"]:z for z in t["zones"]}; requirements={r["zone_id"]:r for r in t["storage_requirements"]}
    first_temp=next((s["sensor_id"] for s in t["sensors"] if s["sensor_type"]=="TEMPERATURE"),None)
    for sensor in t["sensors"]:
        zid=sensor["zone_id"]; zone=zones[zid]; kind=sensor["sensor_type"]; unit=sensor["unit"]
        is_cold=zone["zone_type"]=="COLD"; base=(5.0 if is_cold else 22.0) if kind=="TEMPERATURE" else 50.0
        extra=1 if config.inject_anomalies and sensor["sensor_id"]==first_temp else 0
        for ri in range(config.readings_per_sensor+extra):
            ts=now+timedelta(minutes=ri*config.interval_minutes)
            value=round(base+0.35*((ri%8)-3.5)+rng.gauss(0,0.12),3)
            if config.inject_anomalies and sensor["sensor_id"]==first_temp and ri==2: value=12.0
            if config.inject_anomalies and sensor["sensor_id"]==first_temp and ri==4:
                t["ground_truth"].append(dict(scenario_id="NEG-03",entity_id=sensor["sensor_id"],expected_issue="MISSING_READING_GAP",expected_label="DETECTED",details="Reading slot omitted; absence is unknown, never normal.")); continue
            row=dict(reading_id=f"READ-{sensor['sensor_id']}-{ri+1:06d}",sensor_id=sensor["sensor_id"],zone_id=zid,timestamp=ts.isoformat(),value=value,unit=unit,quality="GOOD")
            yield row

def finalize(t, config: Config):
    if config.inject_anomalies:
        from .rules import record_alarm
        aid="ALM-NEG-04"
        zone_id=t["zones"][0]["zone_id"]
        record_alarm(t,dict(zone_id=zone_id,sensor_id=t["sensors"][0]["sensor_id"],reading_id=aid,timestamp=_dt(config.start).isoformat()),dict(alarm_id=aid,source_record_id=aid,rule_id="FIXTURE_UNLINKED",risk_type="FIXTURE_UNLINKED",severity="MEDIUM",inventory_impact_expected=True,skip_inventory_link=True,explanation="Controlled negative fixture: alarm has no affected-inventory bridge row."))
        t["ground_truth"].append(dict(scenario_id="NEG-04",entity_id=aid,expected_issue="ALARM_MISSING_INVENTORY_LINK",expected_label="DETECTED",details="Controlled alarm intentionally has no alarm_lots bridge row."))

def generate(config: Config):
    """Convenience in-memory generator for small development/test datasets."""
    from .rules import alarm_for_reading, occupancy_alert_for_reading, record_alarm, detect
    t=generate_core(config); generate_occupancy(t,config); t["sensor_readings"]=list(iter_readings(t,config))
    requirements={r['zone_id']:r for r in t['storage_requirements']}; zones={z['zone_id']:z for z in t['zones']}
    for reading in t['sensor_readings']:
        classification=alarm_for_reading(reading,requirements[reading['zone_id']])
        if classification: record_alarm(t,reading,classification)
    for reading in t['occupancy_readings']:
        classification=occupancy_alert_for_reading(reading,zones[reading['zone_id']])
        if classification: record_alarm(t,reading,classification)
    finalize(t,config)
    detections=detect(t,config)
    for alert in detections['alarms']+detections['issues']: record_alarm(t,alert,alert)
    return t
