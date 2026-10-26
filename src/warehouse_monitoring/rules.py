"""Detectors consume source records only; ground truth is never an input."""
from datetime import datetime

def alarm_for_reading(reading, requirement):
    """Classify a source observation using its zone's configured bounds."""
    if reading['unit']=='C' and not requirement['min_temp_c']<=reading['value']<=requirement['max_temp_c']:
        return {"rule_id":"TEMP_RANGE","severity":"HIGH"}
    if reading['unit']=='PCT' and not requirement['min_humidity_pct']<=reading['value']<=requirement['max_humidity_pct']:
        return {"rule_id":"HUMIDITY_RANGE","severity":"MEDIUM"}
    return None

def record_alarm(t, reading, classification):
    """Persist a derived alarm and only the inventory overlapping its zone/time."""
    aid=f"ALM-{len(t['alarms'])+1:06d}"
    t['alarms'].append(dict(alarm_id=aid,zone_id=reading['zone_id'],source_sensor_id=reading['sensor_id'],incident_at=reading['timestamp'],rule_id=classification['rule_id'],severity=classification['severity'],status="OPEN"))
    for lot in t['inventory_lots']:
        if lot['zone_id']==reading['zone_id'] and lot['received_at']<=reading['timestamp']<=lot['expires_at']:
            t['alarm_lots'].append(dict(alarm_id=aid,lot_id=lot['lot_id']))
    t['inspections'].append(dict(inspection_id=f"INSP-{aid}",alarm_id=aid,inspected_at=reading['timestamp'],outcome="REVIEW_REQUIRED"))
    t['remediations'].append(dict(remediation_id=f"REM-{aid}",inspection_id=f"INSP-{aid}",action="Investigate excursion",status="OPEN"))

def detect(t, config=None):
    alarms=[]; issues=[]
    req={r['zone_id']:r for r in t['storage_requirements']}
    zones={z['zone_id']:z for z in t['zones']}
    for r in t['sensor_readings']:
        q=req.get(r['zone_id'])
        classification=alarm_for_reading(r,q) if q else None
        if classification:
            alarms.append(dict(alarm_id=f"DET-{len(alarms)+1:06d}",zone_id=r['zone_id'],source_sensor_id=r['sensor_id'],incident_at=r['timestamp'],rule_id=classification['rule_id'],severity=classification['severity'],status="OPEN"))
    # A timestamp gap exceeding 1.5 expected intervals is unknown coverage, never a normal reading.
    by_sensor={}
    for r in t['sensor_readings']: by_sensor.setdefault(r['sensor_id'],[]).append(r)
    for sid, rows in by_sensor.items():
        rows.sort(key=lambda x:x['timestamp'])
        for a,b in zip(rows,rows[1:]):
            gap=(datetime.fromisoformat(b['timestamp'])-datetime.fromisoformat(a['timestamp'])).total_seconds()/60
            if gap>22.5: issues.append(dict(issue_type="MISSING_READING_GAP",entity_id=sid,details=f"Observed gap {gap:g} minutes"))
    for lot in t['inventory_lots']:
        q=req.get(lot['zone_id'])
        if q and lot['product_class'] not in (q['product_class'],"ANY"):
            issues.append(dict(issue_type="STORAGE_INCOMPATIBILITY",entity_id=lot['lot_id'],details=f"{lot['product_class']} in zone requiring {q['product_class']}"))
    assigned={}
    for a in t['sensor_zone_assignments']: assigned.setdefault(a['sensor_id'],set()).add(a['zone_id'])
    for sid,zs in assigned.items():
        if len(zs)>1: issues.append(dict(issue_type="MULTIPLE_ZONE_MAPPING",entity_id=sid,details=f"Active zones: {sorted(zs)}"))
    linked={a['alarm_id'] for a in t['alarm_lots']}
    for a in t['alarms']:
        if a['alarm_id'] not in linked: issues.append(dict(issue_type="ALARM_MISSING_INVENTORY_LINK",entity_id=a['alarm_id'],details="Alarm has no linked affected lot"))
    # Drift is a review signal: compare first/last readings against threshold, requiring >= 5 samples.
    for sid,rows in by_sensor.items():
        if len(rows)>=5:
            rows.sort(key=lambda x:x['timestamp'])
            drift=rows[-1]['value']-rows[0]['value']
            if abs(drift)>2.0: issues.append(dict(issue_type="SENSOR_DRIFT_REVIEW",entity_id=sid,details=f"Endpoint change {drift:.3f}"))
    limit=config.door_open_limit_seconds if config else 300
    for e in t['door_events']:
        if e['duration_seconds']>limit: issues.append(dict(issue_type="ABNORMAL_DOOR_OPEN",entity_id=e['event_id'],details=f"Open {e['duration_seconds']} seconds; limit {limit}"))
    return {"alarms":alarms,"issues":issues}
