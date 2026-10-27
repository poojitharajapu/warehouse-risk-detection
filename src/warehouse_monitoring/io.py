"""CSV/JSON export with canonical hashes and read-back checks."""
import csv, hashlib, json
from collections import deque
from pathlib import Path
from datetime import datetime, timezone
from statistics import fmean

READING_COLUMNS=["reading_id","sensor_id","zone_id","timestamp","value","unit","quality"]
TABLE_SCHEMAS={
    'warehouses':['warehouse_id','name','region','capacity_units'],
    'zones':['zone_id','warehouse_id','name','zone_type','capacity_units','occupancy_capacity_persons'],
    'sensors':['sensor_id','zone_id','sensor_type','unit','status'],
    'sensor_readings':READING_COLUMNS,
    'occupancy_readings':['occupancy_reading_id','zone_id','timestamp','people_count','measurement_method','quality'],
    'door_events':['event_id','zone_id','opened_at','closed_at','duration_seconds'],
    'inventory_lots':['lot_id','warehouse_id','zone_id','product_class','quantity','received_at','expires_at'],
    'storage_requirements':['requirement_id','zone_id','product_class','min_temp_c','max_temp_c','min_humidity_pct','max_humidity_pct'],
    'alarms':['alarm_id','zone_id','warehouse_id','source_sensor_id','source_record_id','incident_at','detection_timestamp','rule_id','risk_type','severity','explanation','inventory_impact_expected','status'],
    'inspections':['inspection_id','alarm_id','inspected_at','outcome','status'],
    'remediations':['remediation_id','inspection_id','created_at','action','status'],
    'alarm_lots':['alarm_id','lot_id'],
    'sensor_zone_assignments':['sensor_id','zone_id','valid_from','valid_to','assignment_reason'],
    'state_history':['history_id','entity_type','entity_id','previous_state','new_state','event_timestamp','reason'],
    'ground_truth':['scenario_id','entity_id','expected_issue','expected_label','details'],
}

def write_reading_stream(t, reading_iter, outdir, on_row=None):
    """Write the high-volume table incrementally and verify rows as they pass."""
    root=Path(outdir); root.mkdir(parents=True,exist_ok=True)
    sensors={x['sensor_id']:x for x in t['sensors']}; zones={x['zone_id']:x for x in t['zones']}
    digest=hashlib.sha256(); digest.update(b'['); count=0; prior={}; first_values={}; last_values={}; sensor_counts={}; last_slot={}; closed_sensors=set(); current_sensor=None; gaps=[]
    with (root/'sensor_readings.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=READING_COLUMNS); writer.writeheader()
        for row in reading_iter:
            if on_row: on_row(row)
            writer.writerow(row)
            if count: digest.update(b',')
            digest.update(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
            count+=1
            if current_sensor!=row['sensor_id']:
                if current_sensor is not None: closed_sensors.add(current_sensor)
                if row['sensor_id'] in closed_sensors: raise ValueError(f"Sensor rows are not grouped: {row['sensor_id']}")
                current_sensor=row['sensor_id']
            prefix=f"READ-{row['sensor_id']}-"
            if not row['reading_id'].startswith(prefix): raise ValueError(f"Malformed reading ID: {row['reading_id']}")
            try: slot=int(row['reading_id'][len(prefix):])
            except ValueError as e: raise ValueError(f"Malformed reading ID: {row['reading_id']}") from e
            if slot<=last_slot.get(row['sensor_id'],0): raise ValueError(f"Duplicate or out-of-order reading ID: {row['reading_id']}")
            last_slot[row['sensor_id']]=slot
            if row['sensor_id'] not in sensors or row['zone_id'] not in zones: raise ValueError(f"Invalid reading foreign key: {row['reading_id']}")
            if sensors[row['sensor_id']]['zone_id']!=row['zone_id']: raise ValueError(f"Reading sensor-zone mismatch: {row['reading_id']}")
            if row['unit'] not in ('C','PCT') or row['quality'] not in ('GOOD','SUSPECT','MISSING') or not isinstance(row['value'],(int,float)): raise ValueError(f"Invalid reading value: {row['reading_id']}")
            ts=datetime.fromisoformat(row['timestamp']); old=prior.get(row['sensor_id'])
            if old is not None:
                gap=(ts-old).total_seconds()/60
                if gap<=0: raise ValueError(f"Non-increasing reading timestamp: {row['reading_id']}")
                if gap>22.5:
                    z=sensors[row['sensor_id']]['zone_id']; gaps.append(dict(issue_type='MISSING_READING_GAP',entity_id=row['sensor_id'],source_record_id=f"{row['sensor_id']}:{row['timestamp']}",zone_id=z,warehouse_id=zones[z]['warehouse_id'],detection_timestamp=row['timestamp'],risk_type='MONITORING_GAP',severity='MEDIUM',inventory_impact_expected=False,explanation=f"No reading was observed for {gap:g} minutes; conditions are unknown.",details=f"Observed gap {gap:g} minutes"))
            prior[row['sensor_id']]=ts
            sid=row['sensor_id']; sensor_counts[sid]=sensor_counts.get(sid,0)+1
            if sid not in first_values: first_values[sid]=[]
            if len(first_values[sid])<8: first_values[sid].append(row['value'])
            if sid not in last_values: last_values[sid]=deque(maxlen=8)
            last_values[sid].append(row['value'])
    digest.update(b']')
    # Read back incrementally: schema and row count without loading the large table.
    read_count=0
    with (root/'sensor_readings.csv').open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=READING_COLUMNS: raise ValueError('SensorReading CSV read-back schema mismatch')
        for _ in reader: read_count+=1
    if read_count!=count: raise ValueError(f"SensorReading CSV read-back row mismatch: {read_count} != {count}")
    for sid,first in first_values.items():
        if sensor_counts[sid]<16: continue
        drift=fmean(last_values[sid])-fmean(first)
        if abs(drift)>2.0:
            z=sensors[sid]['zone_id']; gaps.append(dict(issue_type='SENSOR_DRIFT_REVIEW',entity_id=sid,source_record_id=f"{sid}:DRIFT",zone_id=z,warehouse_id=zones[z]['warehouse_id'],detection_timestamp=prior[sid].isoformat(),risk_type='SENSOR_DRIFT',severity='MEDIUM',inventory_impact_expected=False,explanation=f"Sensor endpoint change was {drift:.3f}; calibration review is required.",details=f"Endpoint change {drift:.3f}"))
    return {'count':count,'sha256':digest.hexdigest(),'columns':READING_COLUMNS,'gaps':gaps,'unique_ids':True}

def export(t, report, config, outdir, prewritten=None):
    prewritten=prewritten or {}
    root=Path(outdir); root.mkdir(parents=True,exist_ok=True)
    hashes={}; schemas={}
    primary_keys={"warehouses":"warehouse_id","zones":"zone_id","sensors":"sensor_id","sensor_readings":"reading_id","occupancy_readings":"occupancy_reading_id","door_events":"event_id","inventory_lots":"lot_id","storage_requirements":"requirement_id","alarms":"alarm_id","inspections":"inspection_id","remediations":"remediation_id","state_history":"history_id"}
    for name,rows in t.items():
        cols=prewritten[name]['columns'] if name in prewritten else (list(rows[0]) if rows else TABLE_SCHEMAS.get(name,[]))
        digest=hashlib.sha256(); digest.update(b'[')
        if name in prewritten:
            hashes[name]=prewritten[name]['sha256']
        else:
            with (root/f"{name}.csv").open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
                for i,row in enumerate(rows):
                    w.writerow(row)
                    if i: digest.update(b',')
                    digest.update(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
            digest.update(b']'); hashes[name]=digest.hexdigest()
        schemas[name]=cols
    (root/'validation_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    row_counts={k:len(v) for k,v in t.items()}
    for name,meta in prewritten.items(): row_counts[name]=meta['count']
    manifest={"generator_version":"0.1.0","seed":config.seed,"configuration":config.__dict__,"generated_at":datetime.now(timezone.utc).isoformat(),"row_counts":row_counts,"canonical_sha256":hashes,"schemas":schemas,"deterministic_comparison_excludes":["generated_at"]}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    # Verify CSV round-trip cardinality and IDs using stdlib reader.
    readback={}; id_sets={}
    for name,rows in t.items():
        count=0; key=primary_keys.get(name); seen=set() if key and name not in prewritten else None
        with (root/f"{name}.csv").open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames!=schemas[name]: raise ValueError(f"CSV read-back schema mismatch: {name}")
            for row in reader:
                count+=1
                if seen is not None:
                    if row[key] in seen: raise ValueError(f"CSV duplicate primary key in {name}: {row[key]}")
                    seen.add(row[key])
        expected=prewritten[name]['count'] if name in prewritten else len(rows)
        if count!=expected: raise ValueError(f"CSV read-back row mismatch: {name}")
        readback[name]=count
        if seen is not None: id_sets[name]=seen
    foreign_keys={"zones":[("warehouse_id","warehouses")],"sensors":[("zone_id","zones")],"sensor_readings":[("sensor_id","sensors"),("zone_id","zones")],"occupancy_readings":[("zone_id","zones")],"door_events":[("zone_id","zones")],"inventory_lots":[("warehouse_id","warehouses"),("zone_id","zones")],"storage_requirements":[("zone_id","zones")],"alarms":[("zone_id","zones"),("warehouse_id","warehouses")],"inspections":[("alarm_id","alarms")],"remediations":[("inspection_id","inspections")],"alarm_lots":[("alarm_id","alarms"),("lot_id","inventory_lots")],"sensor_zone_assignments":[("sensor_id","sensors"),("zone_id","zones")]}
    for name,refs in foreign_keys.items():
        with (root/f"{name}.csv").open(newline='',encoding='utf-8') as f:
            for row in csv.DictReader(f):
                for field,parent in refs:
                    if row[field] not in id_sets[parent]: raise ValueError(f"CSV read-back foreign key failure: {name}.{field}={row[field]}")
    with (root/'alarms.csv').open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['source_sensor_id'] and row['source_sensor_id'] not in id_sets['sensors']:
                raise ValueError(f"CSV read-back foreign key failure: alarms.source_sensor_id={row['source_sensor_id']}")
    state_targets={'ALARM':'alarms','INSPECTION':'inspections','REMEDIATION':'remediations'}
    with (root/'state_history.csv').open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            parent=state_targets.get(row['entity_type'])
            if not parent or row['entity_id'] not in id_sets[parent]: raise ValueError(f"CSV state history target failure: {row['entity_type']}:{row['entity_id']}")
    return {"directory":str(root),"row_counts":readback,"canonical_sha256":hashes}
