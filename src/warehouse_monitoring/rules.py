"""Detectors consume source records only; ground truth is never an input."""
from datetime import datetime, timedelta
from statistics import fmean

ALLOWED_STATE_TRANSITIONS={
    'ALARM': {'':{'OPEN'},'OPEN':{'ACKNOWLEDGED','RESOLVED'},'ACKNOWLEDGED':{'RESOLVED'},'RESOLVED':{'CLOSED'}},
    'INSPECTION': {'':{'OPEN'},'OPEN':{'IN_PROGRESS','COMPLETED'},'IN_PROGRESS':{'COMPLETED'}},
    'REMEDIATION': {'':{'OPEN'},'OPEN':{'IN_PROGRESS','CANCELLED'},'IN_PROGRESS':{'COMPLETED','CANCELLED'}},
}

def record_lifecycle(t, entity_type, entity_id, start_time, states, reason):
    """Append an initial state and each later transition without rewriting prior events."""
    previous=''
    for index,(new_state,offset_seconds) in enumerate(states,1):
        at=(datetime.fromisoformat(start_time)+timedelta(seconds=offset_seconds)).isoformat()
        t['state_history'].append(dict(history_id=f"HIST-{entity_type}-{entity_id}-{index:02d}",entity_type=entity_type,entity_id=entity_id,previous_state=previous,new_state=new_state,event_timestamp=at,reason=reason if index==1 else f"Synthetic {new_state.lower()} transition"))
        previous=new_state

def alarm_for_reading(reading, requirement):
    """Classify a source observation using its zone's configured bounds."""
    if reading['unit']=='C' and not requirement['min_temp_c']<=reading['value']<=requirement['max_temp_c']:
        return {"rule_id":"TEMP_RANGE","severity":"HIGH"}
    if reading['unit']=='PCT' and not requirement['min_humidity_pct']<=reading['value']<=requirement['max_humidity_pct']:
        return {"rule_id":"HUMIDITY_RANGE","severity":"MEDIUM"}
    return None

def occupancy_alert_for_reading(reading, zone):
    limit=zone['occupancy_capacity_persons']
    if reading['people_count']>limit:
        return {'rule_id':'OCCUPANCY_THRESHOLD','severity':'HIGH','inventory_impact_expected':False,'explanation':f"{reading['people_count']} people exceed the zone limit of {limit}."}
    return None

def record_alarm(t, reading, classification):
    """Persist a derived alarm and only the inventory overlapping its zone/time."""
    source_id=classification.get('source_record_id',reading.get('reading_id',reading.get('occupancy_reading_id','')))
    risk_type=classification.get('risk_type') or classification.get('rule_id') or classification.get('issue_type','UNCLASSIFIED_RISK')
    existing=next((a for a in t['alarms'] if a.get('risk_type')==risk_type and a.get('source_record_id')==source_id),None)
    if existing: return existing['alarm_id']
    aid=classification.get('alarm_id',f"ALM-{len(t['alarms'])+1:06d}")
    incident=classification.get('detection_timestamp',reading.get('timestamp',reading.get('incident_at','')))
    warehouse=next(z['warehouse_id'] for z in t['zones'] if z['zone_id']==reading['zone_id'])
    sensor_id=reading.get('sensor_id',reading.get('source_sensor_id',''))
    inventory_expected=classification.get('inventory_impact_expected',True)
    severity=classification.get('severity','MEDIUM')
    rule_id=classification.get('rule_id',risk_type)
    t['alarms'].append(dict(alarm_id=aid,zone_id=reading['zone_id'],warehouse_id=classification.get('warehouse_id',warehouse),source_sensor_id=sensor_id,source_record_id=source_id,incident_at=incident,detection_timestamp=incident,rule_id=rule_id,risk_type=risk_type,severity=severity,explanation=classification.get('explanation',f"{risk_type} detected from {source_id}."),inventory_impact_expected=inventory_expected,status="ACKNOWLEDGED"))
    if inventory_expected and not classification.get('skip_inventory_link',False):
      affected_ids=set(classification.get('affected_lot_ids',[]))
      for lot in t['inventory_lots']:
        if (not affected_ids or lot['lot_id'] in affected_ids) and lot['zone_id']==reading['zone_id'] and lot['received_at']<=incident<=lot['expires_at']:
            t['alarm_lots'].append(dict(alarm_id=aid,lot_id=lot['lot_id']))
    t['inspections'].append(dict(inspection_id=f"INSP-{aid}",alarm_id=aid,inspected_at=(datetime.fromisoformat(incident)+timedelta(hours=1)).isoformat(),outcome="REVIEW_REQUIRED",status="IN_PROGRESS"))
    t['remediations'].append(dict(remediation_id=f"REM-{aid}",inspection_id=f"INSP-{aid}",created_at=(datetime.fromisoformat(incident)+timedelta(hours=1)).isoformat(),action="Investigate excursion",status="IN_PROGRESS"))
    record_lifecycle(t,'ALARM',aid,incident,[('OPEN',0),('ACKNOWLEDGED',300)],classification.get('explanation','Risk alert created'))
    record_lifecycle(t,'INSPECTION',f"INSP-{aid}",incident,[('OPEN',0),('IN_PROGRESS',3600)],'Inspection opened for alarm')
    record_lifecycle(t,'REMEDIATION',f"REM-{aid}",incident,[('OPEN',3600),('IN_PROGRESS',7200)],'Remediation opened for inspection')
    return aid

def detect(t, config=None):
    alarms=[]; issues=[]
    req={r['zone_id']:r for r in t['storage_requirements']}
    zones={z['zone_id']:z for z in t['zones']}
    for r in t['sensor_readings']:
        q=req.get(r['zone_id'])
        classification=alarm_for_reading(r,q) if q else None
        if classification:
            zone=zones[r['zone_id']]
            alarms.append(dict(alarm_id=f"DET-{len(alarms)+1:06d}",zone_id=r['zone_id'],warehouse_id=zone['warehouse_id'],source_sensor_id=r['sensor_id'],source_record_id=r['reading_id'],incident_at=r['timestamp'],detection_timestamp=r['timestamp'],risk_type=classification['rule_id'],rule_id=classification['rule_id'],severity=classification['severity'],explanation=f"Observed {r['value']} {r['unit']} outside the permitted zone range.",inventory_impact_expected=True,status="OPEN"))
    for r in t.get('occupancy_readings',[]):
        zone=zones[r['zone_id']]; classification=occupancy_alert_for_reading(r,zone)
        if classification:
            alarms.append(dict(alarm_id=f"DET-OCC-{r['occupancy_reading_id']}",zone_id=r['zone_id'],warehouse_id=zone['warehouse_id'],source_sensor_id='',source_record_id=r['occupancy_reading_id'],incident_at=r['timestamp'],detection_timestamp=r['timestamp'],risk_type='OCCUPANCY_THRESHOLD',rule_id='OCCUPANCY_THRESHOLD',severity='HIGH',explanation=classification['explanation'],inventory_impact_expected=False,status='OPEN'))
    # A timestamp gap exceeding 1.5 expected intervals is unknown coverage, never a normal reading.
    by_sensor={}
    for r in t['sensor_readings']: by_sensor.setdefault(r['sensor_id'],[]).append(r)
    for sid, rows in by_sensor.items():
        rows.sort(key=lambda x:x['timestamp'])
        for a,b in zip(rows,rows[1:]):
            gap=(datetime.fromisoformat(b['timestamp'])-datetime.fromisoformat(a['timestamp'])).total_seconds()/60
            if gap>22.5:
                sensor=next(s for s in t['sensors'] if s['sensor_id']==sid); zone=zones[sensor['zone_id']]
                issues.append(dict(issue_type="MISSING_READING_GAP",entity_id=sid,source_record_id=f"{sid}:{b['timestamp']}",zone_id=sensor['zone_id'],warehouse_id=zone['warehouse_id'],detection_timestamp=b['timestamp'],risk_type="MONITORING_GAP",severity="MEDIUM",inventory_impact_expected=False,explanation=f"No reading was observed for {gap:g} minutes; conditions are unknown.",details=f"Observed gap {gap:g} minutes"))
    for lot in t['inventory_lots']:
        q=req.get(lot['zone_id'])
        if q and lot['product_class'] not in (q['product_class'],"ANY"):
            zone=zones[lot['zone_id']]
            issues.append(dict(issue_type="STORAGE_INCOMPATIBILITY",entity_id=lot['lot_id'],source_record_id=lot['lot_id'],zone_id=lot['zone_id'],warehouse_id=zone['warehouse_id'],detection_timestamp=lot['received_at'],risk_type="STORAGE_INCOMPATIBILITY",severity="HIGH",inventory_impact_expected=True,affected_lot_ids=[lot['lot_id']],explanation=f"{lot['product_class']} stock is incompatible with {q['product_class']} storage.",details=f"{lot['product_class']} in zone requiring {q['product_class']}"))
    assigned={}
    for a in t['sensor_zone_assignments']: assigned.setdefault(a['sensor_id'],[]).append(a)
    for sid,assignments in assigned.items():
        zs={a['zone_id'] for a in assignments}
        if len(zs)>1 and not all(a.get('assignment_reason','').strip() for a in assignments):
            sensor=next(s for s in t['sensors'] if s['sensor_id']==sid); zone=zones[sensor['zone_id']]
            issues.append(dict(issue_type="MULTIPLE_ZONE_MAPPING",entity_id=sid,source_record_id=sid,zone_id=sensor['zone_id'],warehouse_id=zone['warehouse_id'],detection_timestamp=next((a['valid_from'] for a in t['sensor_zone_assignments'] if a['sensor_id']==sid),''),risk_type="MULTIPLE_ZONE_MAPPING",severity="HIGH",inventory_impact_expected=False,explanation=f"Sensor is assigned to multiple active zones: {sorted(zs)}.",details=f"Active zones: {sorted(zs)}"))
    linked={a['alarm_id'] for a in t['alarm_lots']}
    for a in t['alarms']:
        if a['alarm_id'] not in linked and a.get('inventory_impact_expected',True):
            zone_id=a['zone_id']; warehouse_id=a.get('warehouse_id',zones[zone_id]['warehouse_id'])
            issues.append(dict(issue_type="ALARM_MISSING_INVENTORY_LINK",entity_id=a['alarm_id'],source_record_id=a['alarm_id'],zone_id=zone_id,warehouse_id=warehouse_id,detection_timestamp=a.get('incident_at',''),risk_type="ALARM_MISSING_INVENTORY_LINK",severity="HIGH",inventory_impact_expected=False,explanation="The source alarm expects affected inventory but has no alarm-to-lot link.",details="Alarm has no linked affected lot"))
    # Compare full eight-reading pattern cycles so periodic environmental changes do not look like drift.
    for sid,rows in by_sensor.items():
        if len(rows)>=16:
            rows.sort(key=lambda x:x['timestamp'])
            drift=fmean(x['value'] for x in rows[-8:])-fmean(x['value'] for x in rows[:8])
            if abs(drift)>2.0:
                sensor=next(s for s in t['sensors'] if s['sensor_id']==sid); zone=zones[sensor['zone_id']]
                issues.append(dict(issue_type="SENSOR_DRIFT_REVIEW",entity_id=sid,source_record_id=f"{sid}:DRIFT",zone_id=sensor['zone_id'],warehouse_id=zone['warehouse_id'],detection_timestamp=rows[-1]['timestamp'],risk_type="SENSOR_DRIFT",severity="MEDIUM",inventory_impact_expected=False,explanation=f"Sensor endpoint change was {drift:.3f}; calibration review is required.",details=f"Endpoint change {drift:.3f}"))
    limit=config.door_open_limit_seconds if config else 300
    for e in t['door_events']:
        if e['duration_seconds']>limit:
            zone=zones[e['zone_id']]
            issues.append(dict(issue_type="ABNORMAL_DOOR_OPEN",entity_id=e['event_id'],source_record_id=e['event_id'],zone_id=e['zone_id'],warehouse_id=zone['warehouse_id'],detection_timestamp=e['opened_at'],risk_type="DOOR_OPEN_DURATION",severity="HIGH",inventory_impact_expected=True,explanation=f"Door remained open for {e['duration_seconds']} seconds, over the {limit}-second limit.",details=f"Open {e['duration_seconds']} seconds; limit {limit}"))
    # Storage capacity is inventory units; human occupancy has its own people-count limit.
    loads={z['zone_id']:0 for z in t['zones']}
    for lot in t['inventory_lots']: loads[lot['zone_id']]=loads.get(lot['zone_id'],0)+lot['quantity']
    for zone_id,total in loads.items():
        zone=zones[zone_id]
        if total>zone['capacity_units']:
            seen=max((lot['received_at'] for lot in t['inventory_lots'] if lot['zone_id']==zone_id),default='')
            issues.append(dict(issue_type="INVENTORY_CAPACITY",entity_id=zone_id,source_record_id=f"{zone_id}:CAPACITY",zone_id=zone_id,warehouse_id=zone['warehouse_id'],detection_timestamp=seen,risk_type="INVENTORY_CAPACITY",severity="HIGH",inventory_impact_expected=False,explanation=f"Inventory load {total} exceeds {zone['capacity_units']} units.",details=f"{total} units"))
    return {"alarms":alarms,"issues":issues}
