"""CSV/JSON export with canonical hashes and read-back checks."""
import csv, hashlib, json
from pathlib import Path
from datetime import datetime, timezone

READING_COLUMNS=["reading_id","sensor_id","zone_id","timestamp","value","unit","quality"]

def write_reading_stream(t, reading_iter, outdir, on_row=None):
    """Write the high-volume table incrementally and verify rows as they pass."""
    root=Path(outdir); root.mkdir(parents=True,exist_ok=True)
    sensors={x['sensor_id']:x for x in t['sensors']}; zones={x['zone_id'] for x in t['zones']}
    digest=hashlib.sha256(); digest.update(b'['); count=0; prior={}; last_slot={}; closed_sensors=set(); current_sensor=None; gaps=[]
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
                if gap>22.5: gaps.append(dict(issue_type='MISSING_READING_GAP',entity_id=row['sensor_id'],details=f"Observed gap {gap:g} minutes"))
            prior[row['sensor_id']]=ts
    digest.update(b']')
    # Read back incrementally: schema and row count without loading the large table.
    read_count=0
    with (root/'sensor_readings.csv').open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=READING_COLUMNS: raise ValueError('SensorReading CSV read-back schema mismatch')
        for _ in reader: read_count+=1
    if read_count!=count: raise ValueError(f"SensorReading CSV read-back row mismatch: {read_count} != {count}")
    return {'count':count,'sha256':digest.hexdigest(),'columns':READING_COLUMNS,'gaps':gaps,'unique_ids':True}

def export(t, report, config, outdir, prewritten=None):
    prewritten=prewritten or {}
    root=Path(outdir); root.mkdir(parents=True,exist_ok=True)
    hashes={}; schemas={}
    primary_keys={"warehouses":"warehouse_id","zones":"zone_id","sensors":"sensor_id","sensor_readings":"reading_id","door_events":"event_id","inventory_lots":"lot_id","storage_requirements":"requirement_id","alarms":"alarm_id","inspections":"inspection_id","remediations":"remediation_id"}
    for name,rows in t.items():
        cols=prewritten[name]['columns'] if name in prewritten else (list(rows[0]) if rows else [])
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
    foreign_keys={"zones":[("warehouse_id","warehouses")],"sensors":[("zone_id","zones")],"sensor_readings":[("sensor_id","sensors"),("zone_id","zones")],"door_events":[("zone_id","zones")],"inventory_lots":[("warehouse_id","warehouses"),("zone_id","zones")],"storage_requirements":[("zone_id","zones")],"alarms":[("zone_id","zones"),("source_sensor_id","sensors")],"inspections":[("alarm_id","alarms")],"remediations":[("inspection_id","inspections")],"alarm_lots":[("alarm_id","alarms"),("lot_id","inventory_lots")],"sensor_zone_assignments":[("sensor_id","sensors"),("zone_id","zones")]}
    for name,refs in foreign_keys.items():
        with (root/f"{name}.csv").open(newline='',encoding='utf-8') as f:
            for row in csv.DictReader(f):
                for field,parent in refs:
                    if row[field] not in id_sets[parent]: raise ValueError(f"CSV read-back foreign key failure: {name}.{field}={row[field]}")
    return {"directory":str(root),"row_counts":readback,"canonical_sha256":hashes}
