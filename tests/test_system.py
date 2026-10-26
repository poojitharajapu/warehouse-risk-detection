import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from warehouse_monitoring.config import Config
from warehouse_monitoring.generator import generate
from warehouse_monitoring.rules import detect, alarm_for_reading, record_alarm
from warehouse_monitoring.validation import validate
from warehouse_monitoring.io import export
from warehouse_monitoring.generator import generate_core, iter_readings, finalize
from warehouse_monitoring.io import write_reading_stream
import json

class SystemTests(unittest.TestCase):
  def test_small_scenario_detection_and_validation(self):
    t=generate(Config.small()); d=detect(t); report=validate(t,d)
    self.assertEqual(report['overall_status'],'PASS'); self.assertEqual(report['failed_checks'],0)
    expected={x['scenario_id']:x for x in t['ground_truth']}
    detected={(x['issue_type'],x['entity_id']) for x in d['issues']}
    for scenario, issue in [('NEG-01','STORAGE_INCOMPATIBILITY'),('NEG-02','MULTIPLE_ZONE_MAPPING'),('NEG-03','MISSING_READING_GAP'),('NEG-04','ALARM_MISSING_INVENTORY_LINK')]:
        self.assertIn((issue,expected[scenario]['entity_id']),detected)

  def test_seed_reproducibility(self):
    a=generate(Config.small(77)); b=generate(Config.small(77))
    self.assertEqual(a,b)

  def test_unexpected_fk_failure_is_reported(self):
    t=generate(Config.small()); t['sensor_readings'][0]['sensor_id']='MISSING'
    report=validate(t,detect(t))
    self.assertEqual(report['overall_status'],'FAIL')
    self.assertTrue(any(x['check']=='readings.sensor_fk' and x['status']=='FAIL' for x in report['checks']))

  def test_temperature_and_humidity_boundary_values(self):
    cold={'min_temp_c':2.0,'max_temp_c':8.0,'min_humidity_pct':20.0,'max_humidity_pct':80.0}
    def row(value,unit): return {'value':value,'unit':unit}
    self.assertIsNone(alarm_for_reading(row(2.0,'C'),cold))
    self.assertIsNone(alarm_for_reading(row(8.0,'C'),cold))
    self.assertEqual(alarm_for_reading(row(1.999,'C'),cold)['severity'],'HIGH')
    self.assertEqual(alarm_for_reading(row(8.001,'C'),cold)['rule_id'],'TEMP_RANGE')
    self.assertIsNone(alarm_for_reading(row(20.0,'PCT'),cold))
    self.assertIsNone(alarm_for_reading(row(80.0,'PCT'),cold))
    self.assertEqual(alarm_for_reading(row(80.1,'PCT'),cold)['rule_id'],'HUMIDITY_RANGE')

  def test_abnormal_door_duration_and_sensor_drift_are_signaled(self):
    t=generate(Config.small())
    door=t['door_events'][0]; door['duration_seconds']=420
    from datetime import datetime, timedelta
    door['closed_at']=(datetime.fromisoformat(door['opened_at'])+timedelta(seconds=420)).isoformat()
    sid=t['sensors'][0]['sensor_id']
    rows=[x for x in t['sensor_readings'] if x['sensor_id']==sid]
    rows[-1]['value']=rows[0]['value']+3.0
    issues=detect(t)['issues']
    self.assertTrue(any(x['issue_type']=='ABNORMAL_DOOR_OPEN' and x['entity_id']==door['event_id'] for x in issues))
    self.assertTrue(any(x['issue_type']=='SENSOR_DRIFT_REVIEW' and x['entity_id']==sid for x in issues))

  def test_affected_inventory_is_zone_and_time_scoped(self):
    t=generate(Config.small()); self.assertEqual(len(t['alarms']),2)
    links=[x for x in t['alarm_lots'] if x['alarm_id']=='ALM-000001']
    self.assertEqual([x['lot_id'] for x in links],['LOT-2026-000003'])
    self.assertEqual(t['inspections'][0]['alarm_id'],'ALM-000001')
    self.assertEqual(t['remediations'][0]['inspection_id'],'INSP-ALM-000001')

  def test_duplicate_primary_key_and_unexpected_orphan_fail_validation(self):
    t=generate(Config.small()); t['warehouses'].append(dict(t['warehouses'][0]))
    t['alarms'].append(dict(alarm_id='ALM-UNEXPECTED',zone_id=t['zones'][0]['zone_id'],source_sensor_id=t['sensors'][0]['sensor_id'],incident_at=t['inventory_lots'][0]['received_at'],rule_id='BAD_FIXTURE',severity='MEDIUM',status='OPEN'))
    r=validate(t,detect(t))
    self.assertEqual(r['overall_status'],'FAIL')
    self.assertTrue(any(x['check']=='warehouses.primary_key_unique' and x['status']=='FAIL' for x in r['checks']))
    self.assertTrue(any(x['check']=='alarms.affected_inventory_link' and x['status']=='FAIL' for x in r['checks']))

  def test_export_round_trip(self):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
      cfg=Config.small(); t=generate(cfg); report=validate(t,detect(t)); result=export(t,report,cfg,tmp)
      with open(tmp+'/manifest.json',encoding='utf-8') as stream: manifest=json.load(stream)
      self.assertEqual(result['row_counts'],manifest['row_counts'])
      self.assertTrue(__import__('os').path.exists(tmp+'/ground_truth.csv'))

  def test_streamed_small_output_matches_in_memory(self):
    import tempfile
    cfg=Config.small(); memory=generate(cfg)
    with tempfile.TemporaryDirectory() as tmp:
      core=generate_core(cfg); requirements={x['zone_id']:x for x in core['storage_requirements']}
      def derive(row):
        rule=alarm_for_reading(row,requirements[row['zone_id']])
        if rule: record_alarm(core,row,rule)
      streamed=write_reading_stream(core,iter_readings(core,cfg),tmp,on_row=derive); finalize(core,cfg)
      self.assertEqual(streamed['count'],len(memory['sensor_readings']))
      self.assertEqual(streamed['sha256'],__import__('hashlib').sha256(__import__('json').dumps(memory['sensor_readings'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())
      self.assertEqual(core['alarms'],memory['alarms'])

  def test_baseline_config_volumes(self):
    cfg=Config.baseline()
    self.assertEqual((cfg.warehouses,cfg.zones,cfg.sensors,cfg.readings,cfg.lots),(10,100,500,1_000_000,10_000))
    core=generate_core(cfg)
    self.assertEqual((len(core['warehouses']),len(core['zones']),len(core['sensors']),len(core['inventory_lots'])),(10,100,500,10_000))

if __name__=='__main__': unittest.main()
