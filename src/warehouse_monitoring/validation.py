"""Independent integrity checks. Expected injected defects are reported separately."""
from collections import Counter
from datetime import datetime
from .rules import ALLOWED_STATE_TRANSITIONS

def _timestamp(value):
    try:
        parsed=datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else None
    except (ValueError,TypeError):
        return None

def validate(t, detected=None):
    detected=detected or {"alarms":[],"issues":[]}
    checks=[]
    expected_entities={x['entity_id'] for x in t['ground_truth']}
    expected_issues={x['expected_issue'] for x in t['ground_truth']}
    def add(name, passed, details="", deliberate=False): checks.append({"check":name,"status":"PASS" if passed else ("EXPECTED_ANOMALY" if deliberate else "FAIL"),"details":details})
    keys={"warehouses":"warehouse_id","zones":"zone_id","sensors":"sensor_id","sensor_readings":"reading_id","occupancy_readings":"occupancy_reading_id","door_events":"event_id","inventory_lots":"lot_id","storage_requirements":"requirement_id","alarms":"alarm_id","inspections":"inspection_id","remediations":"remediation_id","state_history":"history_id"}
    for table,key in keys.items():
        ids=[r[key] for r in t[table]]; add(f"{table}.primary_key_unique",len(ids)==len(set(ids)),f"{len(ids)} rows")
    wh={x['warehouse_id'] for x in t['warehouses']}; zone={x['zone_id'] for x in t['zones']}; sensors={x['sensor_id'] for x in t['sensors']}; lots={x['lot_id'] for x in t['inventory_lots']}; alarms={x['alarm_id'] for x in t['alarms']}; insps={x['inspection_id'] for x in t['inspections']}
    add("zones.warehouse_fk",all(x['warehouse_id'] in wh for x in t['zones']))
    add("zones.enumerated_type",all(x['zone_type'] in ('COLD','AMBIENT') for x in t['zones']))
    add("zones.occupancy_capacity_positive",all(isinstance(x.get('occupancy_capacity_persons'),int) and x['occupancy_capacity_persons']>0 for x in t['zones']))
    add("sensors.zone_fk",all(x['zone_id'] in zone for x in t['sensors']))
    add("sensors.enumerated_type",all(x['sensor_type'] in ('TEMPERATURE','HUMIDITY') and x['unit'] in ('C','PCT') for x in t['sensors']))
    add("readings.sensor_fk",all(x['sensor_id'] in sensors and x['zone_id'] in zone for x in t['sensor_readings']))
    sensor_zone={x['sensor_id']:x['zone_id'] for x in t['sensors']}
    add("readings.sensor_zone_consistency",all(sensor_zone.get(x['sensor_id'])==x['zone_id'] for x in t['sensor_readings']))
    add("readings.required_numeric",all(isinstance(x['value'],(int,float)) and x['unit'] in ('C','PCT') and x['quality'] in ('GOOD','SUSPECT','MISSING') for x in t['sensor_readings']))
    reading_times=[_timestamp(x.get('timestamp')) for x in t['sensor_readings']]
    timestamps_valid=all(x is not None for x in reading_times)
    add("readings.timestamp_format",timestamps_valid)
    reading_keys=[(x['sensor_id'],x['timestamp']) for x in t['sensor_readings']]
    add("readings.sensor_timestamp_unique",len(reading_keys)==len(set(reading_keys)))
    add("occupancy.zone_fk",all(x['zone_id'] in zone for x in t['occupancy_readings']))
    occupancy_times=[_timestamp(x.get('timestamp')) for x in t['occupancy_readings']]
    occupancy_times_valid=all(x is not None for x in occupancy_times)
    add("occupancy.timestamp_format",occupancy_times_valid)
    occupancy_values_valid=all(isinstance(x['people_count'],int) and x['people_count']>=0 and x['quality'] in ('GOOD','SUSPECT') and x['measurement_method']=='SYNTHETIC_COUNT' for x in t['occupancy_readings'])
    add("occupancy.required_values",occupancy_values_valid)
    occupancy_keys=[(x['zone_id'],x['timestamp']) for x in t['occupancy_readings']]
    add("occupancy.zone_timestamp_unique",len(occupancy_keys)==len(set(occupancy_keys)))
    gt_keys=[(x['scenario_id'],x['entity_id']) for x in t['ground_truth']]
    add("ground_truth.composite_unique",len(gt_keys)==len(set(gt_keys)))
    add("lots.warehouse_zone_fk",all(x['warehouse_id'] in wh and x['zone_id'] in zone for x in t['inventory_lots']))
    add("lots.warehouse_zone_consistency",all(x['warehouse_id']==next((z['warehouse_id'] for z in t['zones'] if z['zone_id']==x['zone_id']),None) for x in t['inventory_lots']))
    add("lots.dwell_order",all(_timestamp(x.get('received_at')) is not None and _timestamp(x.get('expires_at')) is not None and _timestamp(x['received_at'])<_timestamp(x['expires_at']) for x in t['inventory_lots']))
    add("door.duration_reconciles",all(_timestamp(x.get('opened_at')) is not None and _timestamp(x.get('closed_at')) is not None and (_timestamp(x['closed_at'])-_timestamp(x['opened_at'])).total_seconds()==x['duration_seconds'] for x in t['door_events']))
    add("door.chronological_order",all(_timestamp(x.get('closed_at')) is not None and _timestamp(x.get('opened_at')) is not None and _timestamp(x['closed_at'])>=_timestamp(x['opened_at']) for x in t['door_events']))
    add("storage_requirement.bounds",all(x['min_temp_c']<=x['max_temp_c'] and x['min_humidity_pct']<=x['max_humidity_pct'] for x in t['storage_requirements']))
    add("storage_requirement.zone_cardinality",len({x['zone_id'] for x in t['storage_requirements']})==len(t['zones']) and all(x['zone_id'] in zone for x in t['storage_requirements']))
    add("alarm.enumerated_status",all(x['status'] in ('OPEN','ACKNOWLEDGED','RESOLVED','CLOSED') and x['severity'] in ('LOW','MEDIUM','HIGH') for x in t['alarms']))
    add("alarm.trace_fields",all(x.get('warehouse_id') in wh and x.get('zone_id') in zone and x.get('risk_type') and x.get('explanation') and x.get('detection_timestamp') for x in t['alarms']))
    zone_wh={x['zone_id']:x['warehouse_id'] for x in t['zones']}
    add("alarm.zone_warehouse_and_sensor_fks",all(x.get('warehouse_id')==zone_wh.get(x.get('zone_id')) and (not x.get('source_sensor_id') or x['source_sensor_id'] in sensors) for x in t['alarms']))
    add("alarm.timestamp_format",all(_timestamp(x.get('incident_at')) is not None and _timestamp(x.get('detection_timestamp')) is not None for x in t['alarms']))
    add("inspection.enumerated_outcome",all(x['outcome'] in ('REVIEW_REQUIRED','CONFIRMED','CLEARED') for x in t['inspections']))
    add("remediation.enumerated_status",all(x['status'] in ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED') for x in t['remediations']))
    add("remediation.creation_before_transition",all(any(h['entity_type']=='REMEDIATION' and h['entity_id']==x['remediation_id'] and h['event_timestamp']>=x['created_at'] for h in t['state_history']) for x in t['remediations']))
    inspections_by_id={x['inspection_id']:x for x in t['inspections']}; alarms_by_id={x['alarm_id']:x for x in t['alarms']}
    add("lifecycle.dates_ordered",all(_timestamp(x.get('inspected_at')) is not None and x['inspected_at']>=alarms_by_id[x['alarm_id']]['incident_at'] for x in t['inspections'] if x['alarm_id'] in alarms_by_id) and all(_timestamp(x.get('created_at')) is not None and x['created_at']>=inspections_by_id[x['inspection_id']]['inspected_at'] for x in t['remediations'] if x['inspection_id'] in inspections_by_id))
    add("alarm_lots.fks",all(x['alarm_id'] in alarms and x['lot_id'] in lots for x in t['alarm_lots']))
    bridge_keys=[(x['alarm_id'],x['lot_id']) for x in t['alarm_lots']]
    add("alarm_lots.unique_pair",len(bridge_keys)==len(set(bridge_keys)))
    mapping_keys=[(x['sensor_id'],x['zone_id'],x['valid_from']) for x in t['sensor_zone_assignments']]
    add("sensor_zone_assignments.fks_and_unique",all(x['sensor_id'] in sensors and x['zone_id'] in zone for x in t['sensor_zone_assignments']) and len(mapping_keys)==len(set(mapping_keys)))
    add("lifecycle.fks",all(x['alarm_id'] in alarms for x in t['inspections']) and all(x['inspection_id'] in insps for x in t['remediations']))
    multi=[]
    for sid in sensors:
        assignments=[a for a in t['sensor_zone_assignments'] if a['sensor_id']==sid]
        if len({a['zone_id'] for a in assignments})>1 and not all(a.get('assignment_reason','').strip() for a in assignments): multi.append(sid)
    add("sensor_zone_mapping.unique",not multi,','.join(multi),bool(multi and set(multi)<=expected_entities and "MULTIPLE_ZONE_MAPPING" in expected_issues))
    req={x['zone_id']:x for x in t['storage_requirements']}
    zone_by_id={x['zone_id']:x for x in t['zones']}
    loads=Counter()
    for lot in t['inventory_lots']: loads[lot['zone_id']]+=lot['quantity']
    over_capacity=[z for z,total in loads.items() if z in zone_by_id and total>zone_by_id[z]['capacity_units']]
    add("zone.capacity",not over_capacity,','.join(over_capacity))
    incompatible=[x['lot_id'] for x in t['inventory_lots'] if x['zone_id'] in req and x['product_class']!=req[x['zone_id']]['product_class']]
    add("storage.compatibility",not incompatible,','.join(incompatible),bool(incompatible and set(incompatible)<=expected_entities and "STORAGE_INCOMPATIBILITY" in expected_issues))
    dangling=[x['alarm_id'] for x in t['alarms'] if x.get('inventory_impact_expected',True) and not any(y['alarm_id']==x['alarm_id'] for y in t['alarm_lots'])]
    add("alarms.affected_inventory_link",not dangling,','.join(dangling),bool(dangling and set(dangling)<=expected_entities and "ALARM_MISSING_INVENTORY_LINK" in expected_issues))
    lots_by_id={x['lot_id']:x for x in t['inventory_lots']}; alarms_by_id={x['alarm_id']:x for x in t['alarms']}
    invalid_links=[]
    for link in t['alarm_lots']:
        alarm=alarms_by_id.get(link['alarm_id']); lot=lots_by_id.get(link['lot_id'])
        if alarm and lot and (alarm['zone_id']!=lot['zone_id'] or not lot['received_at']<=alarm['incident_at']<=lot['expires_at']): invalid_links.append(link['alarm_id'])
    add("alarms.affected_lots_match_zone_and_time",not invalid_links,','.join(invalid_links))
    assignment_issues=[i for i in detected['issues'] if i['issue_type'] in ('STORAGE_INCOMPATIBILITY','MULTIPLE_ZONE_MAPPING','MISSING_READING_GAP','ALARM_MISSING_INVENTORY_LINK')]
    expected={x['scenario_id']:x for x in t['ground_truth']}
    mapped={"NEG-01":"STORAGE_INCOMPATIBILITY","NEG-02":"MULTIPLE_ZONE_MAPPING","NEG-03":"MISSING_READING_GAP","NEG-04":"ALARM_MISSING_INVENTORY_LINK"}
    for sid,issue in mapped.items():
        fixture=expected.get(sid)
        add(f"{sid}.detected",bool(fixture and any(i['issue_type']==issue and i['entity_id']==fixture['entity_id'] for i in assignment_issues)),fixture['entity_id'] if fixture else "fixture missing")
    occupancy_fixture=expected.get('NEG-05')
    detected_occupancy=any(a.get('risk_type')=='OCCUPANCY_THRESHOLD' and a.get('source_record_id')==(occupancy_fixture or {}).get('entity_id') for a in detected['alarms'])
    add("NEG-05.detected",bool(occupancy_fixture and detected_occupancy),occupancy_fixture['entity_id'] if occupancy_fixture else "fixture missing")
    over=[x['occupancy_reading_id'] for x in t['occupancy_readings'] if x['zone_id'] in {z['zone_id'] for z in t['zones']} and x['people_count']>next(z['occupancy_capacity_persons'] for z in t['zones'] if z['zone_id']==x['zone_id'])]
    gt_occ={x['entity_id'] for x in t['ground_truth'] if x['scenario_id']=='NEG-05'}
    add("occupancy.capacity",not over,','.join(over),bool(over and set(over)<=gt_occ and all(any(a.get('risk_type')=='OCCUPANCY_THRESHOLD' and a.get('source_record_id')==oid for a in detected['alarms']) for oid in over)))
    history_by_entity={}
    history_ids=[x['history_id'] for x in t['state_history']]
    for event in t['state_history']: history_by_entity.setdefault((event['entity_type'],event['entity_id']),[]).append(event)
    history_fks=True; transition_valid=True; history_order=True; current_state=True
    entity_rows={'ALARM':{x['alarm_id']:x for x in t['alarms']},'INSPECTION':{x['inspection_id']:x for x in t['inspections']},'REMEDIATION':{x['remediation_id']:x for x in t['remediations']}}
    state_field={'ALARM':'status','INSPECTION':'status','REMEDIATION':'status'}
    for (kind,eid),events in history_by_entity.items():
        if kind not in entity_rows or eid not in entity_rows[kind]: history_fks=False; continue
        original_times=[e['event_timestamp'] for e in events]
        events.sort(key=lambda x:x['event_timestamp']); previous=''
        try: parsed=[datetime.fromisoformat(e['event_timestamp']) for e in events]
        except (ValueError,TypeError): history_order=False; continue
        if original_times!=sorted(original_times) or len(parsed)!=len(set(parsed)) or not all(x.tzinfo is not None for x in parsed): history_order=False
        for event in events:
            if event['previous_state']!=previous or event['new_state'] not in ALLOWED_STATE_TRANSITIONS.get(kind,{}).get(previous,set()): transition_valid=False
            previous=event['new_state']
        if events and entity_rows[kind][eid].get(state_field[kind])!=previous: current_state=False
    expected_entities_with_state={(kind,eid) for kind,rows in entity_rows.items() for eid in rows}
    add("state_history.entity_fks",history_fks and expected_entities_with_state<=set(history_by_entity))
    add("state_history.transitions_valid",transition_valid)
    add("state_history.timestamp_order",history_order)
    add("state_history.current_state_consistent",current_state)
    add("state_history.multiple_events_retained",all(len(v)>=2 for v in history_by_entity.values()) and bool(history_by_entity))
    failures=[x for x in checks if x['status']=="FAIL"]
    expected=[x for x in checks if x['status']=="EXPECTED_ANOMALY"]
    return {"overall_status":"PASS" if not failures else "FAIL","record_counts":{k:len(v) for k,v in t.items()},"checks":checks,"passed_checks":sum(x['status']=="PASS" for x in checks),"expected_anomaly_checks":len(expected),"failed_checks":len(failures),"deliberate_anomaly_count":len(t['ground_truth']),"unexpected_errors":failures}
