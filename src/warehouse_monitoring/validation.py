"""Independent integrity checks. Expected injected defects are reported separately."""
from collections import Counter
from datetime import datetime

def validate(t, detected=None):
    detected=detected or {"alarms":[],"issues":[]}
    checks=[]
    expected_entities={x['entity_id'] for x in t['ground_truth']}
    expected_issues={x['expected_issue'] for x in t['ground_truth']}
    def add(name, passed, details="", deliberate=False): checks.append({"check":name,"status":"PASS" if passed else ("EXPECTED_ANOMALY" if deliberate else "FAIL"),"details":details})
    keys={"warehouses":"warehouse_id","zones":"zone_id","sensors":"sensor_id","sensor_readings":"reading_id","door_events":"event_id","inventory_lots":"lot_id","storage_requirements":"requirement_id","alarms":"alarm_id","inspections":"inspection_id","remediations":"remediation_id"}
    for table,key in keys.items():
        ids=[r[key] for r in t[table]]; add(f"{table}.primary_key_unique",len(ids)==len(set(ids)),f"{len(ids)} rows")
    wh={x['warehouse_id'] for x in t['warehouses']}; zone={x['zone_id'] for x in t['zones']}; sensors={x['sensor_id'] for x in t['sensors']}; lots={x['lot_id'] for x in t['inventory_lots']}; alarms={x['alarm_id'] for x in t['alarms']}; insps={x['inspection_id'] for x in t['inspections']}
    add("zones.warehouse_fk",all(x['warehouse_id'] in wh for x in t['zones']))
    add("zones.enumerated_type",all(x['zone_type'] in ('COLD','AMBIENT') for x in t['zones']))
    add("sensors.zone_fk",all(x['zone_id'] in zone for x in t['sensors']))
    add("sensors.enumerated_type",all(x['sensor_type'] in ('TEMPERATURE','HUMIDITY') and x['unit'] in ('C','PCT') for x in t['sensors']))
    add("readings.sensor_fk",all(x['sensor_id'] in sensors and x['zone_id'] in zone for x in t['sensor_readings']))
    sensor_zone={x['sensor_id']:x['zone_id'] for x in t['sensors']}
    add("readings.sensor_zone_consistency",all(sensor_zone.get(x['sensor_id'])==x['zone_id'] for x in t['sensor_readings']))
    add("readings.required_numeric",all(isinstance(x['value'],(int,float)) and x['unit'] in ('C','PCT') and x['quality'] in ('GOOD','SUSPECT','MISSING') for x in t['sensor_readings']))
    try:
        reading_times=[datetime.fromisoformat(x['timestamp']) for x in t['sensor_readings']]
        timestamps_valid=True
    except (ValueError,TypeError):
        reading_times=[]; timestamps_valid=False
    add("readings.timestamp_format",timestamps_valid)
    reading_keys=[(x['sensor_id'],x['timestamp']) for x in t['sensor_readings']]
    add("readings.sensor_timestamp_unique",len(reading_keys)==len(set(reading_keys)))
    add("lots.warehouse_zone_fk",all(x['warehouse_id'] in wh and x['zone_id'] in zone for x in t['inventory_lots']))
    add("lots.warehouse_zone_consistency",all(x['warehouse_id']==next((z['warehouse_id'] for z in t['zones'] if z['zone_id']==x['zone_id']),None) for x in t['inventory_lots']))
    add("lots.dwell_order",all(x['received_at']<x['expires_at'] for x in t['inventory_lots']))
    add("door.duration_reconciles",all((datetime.fromisoformat(x['closed_at'])-datetime.fromisoformat(x['opened_at'])).total_seconds()==x['duration_seconds'] for x in t['door_events']))
    add("door.chronological_order",all(x['closed_at']>=x['opened_at'] for x in t['door_events']))
    add("storage_requirement.bounds",all(x['min_temp_c']<=x['max_temp_c'] and x['min_humidity_pct']<=x['max_humidity_pct'] for x in t['storage_requirements']))
    add("storage_requirement.zone_cardinality",len({x['zone_id'] for x in t['storage_requirements']})==len(t['zones']) and all(x['zone_id'] in zone for x in t['storage_requirements']))
    add("alarm.enumerated_status",all(x['status'] in ('OPEN','ACKNOWLEDGED','RESOLVED') and x['severity'] in ('LOW','MEDIUM','HIGH') for x in t['alarms']))
    add("inspection.enumerated_outcome",all(x['outcome'] in ('REVIEW_REQUIRED','CONFIRMED','CLEARED') for x in t['inspections']))
    add("remediation.enumerated_status",all(x['status'] in ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED') for x in t['remediations']))
    add("alarm_lots.fks",all(x['alarm_id'] in alarms and x['lot_id'] in lots for x in t['alarm_lots']))
    add("lifecycle.fks",all(x['alarm_id'] in alarms for x in t['inspections']) and all(x['inspection_id'] in insps for x in t['remediations']))
    multi=[s for s in sensors if len({a['zone_id'] for a in t['sensor_zone_assignments'] if a['sensor_id']==s})>1]
    add("sensor_zone_mapping.unique",not multi,','.join(multi),bool(multi and set(multi)<=expected_entities and "MULTIPLE_ZONE_MAPPING" in expected_issues))
    req={x['zone_id']:x for x in t['storage_requirements']}
    zone_by_id={x['zone_id']:x for x in t['zones']}
    loads=Counter()
    for lot in t['inventory_lots']: loads[lot['zone_id']]+=lot['quantity']
    over_capacity=[z for z,total in loads.items() if z in zone_by_id and total>zone_by_id[z]['capacity_units']]
    add("zone.capacity",not over_capacity,','.join(over_capacity))
    incompatible=[x['lot_id'] for x in t['inventory_lots'] if x['zone_id'] in req and x['product_class']!=req[x['zone_id']]['product_class']]
    add("storage.compatibility",not incompatible,','.join(incompatible),bool(incompatible and set(incompatible)<=expected_entities and "STORAGE_INCOMPATIBILITY" in expected_issues))
    dangling=[x['alarm_id'] for x in t['alarms'] if not any(y['alarm_id']==x['alarm_id'] for y in t['alarm_lots'])]
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
    failures=[x for x in checks if x['status']=="FAIL"]
    expected=[x for x in checks if x['status']=="EXPECTED_ANOMALY"]
    return {"overall_status":"PASS" if not failures else "FAIL","record_counts":{k:len(v) for k,v in t.items()},"checks":checks,"passed_checks":sum(x['status']=="PASS" for x in checks),"expected_anomaly_checks":len(expected),"failed_checks":len(failures),"deliberate_anomaly_count":len(t['ground_truth']),"unexpected_errors":failures}
