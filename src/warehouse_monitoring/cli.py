import argparse, json
from .config import Config
from .generator import generate, generate_core, iter_readings, finalize
from .rules import detect, alarm_for_reading, record_alarm
from .validation import validate
from .io import export, write_reading_stream

def main():
    p=argparse.ArgumentParser(description="Generate and validate synthetic warehouse monitoring data")
    sub=p.add_subparsers(dest="command",required=True)
    g=sub.add_parser("generate"); g.add_argument("--size",choices=["small","baseline"],default="small"); g.add_argument("--seed",type=int,default=20261022); g.add_argument("--out",default="outputs/run")
    args=p.parse_args(); cfg=Config.small(args.seed) if args.size=="small" else Config.baseline(args.seed)
    if args.size=="baseline":
        tables=generate_core(cfg)
        requirements={x['zone_id']:x for x in tables['storage_requirements']}
        def derive_alarm(row):
            classification=alarm_for_reading(row,requirements[row['zone_id']])
            if classification: record_alarm(tables,row,classification)
        streamed=write_reading_stream(tables,iter_readings(tables,cfg),args.out,on_row=derive_alarm)
        finalize(tables,cfg)
        detections=detect(tables); detections['issues'].extend(streamed['gaps'])
        report=validate(tables,detections)
        report['record_counts']['sensor_readings']=streamed['count']
        report['checks']=[dict(x,details=f"Verified across {streamed['count']} streamed rows") if x['check'].startswith('readings.') or x['check']=='sensor_readings.primary_key_unique' else x for x in report['checks']]
        result=export(tables,report,cfg,args.out,prewritten={'sensor_readings':streamed})
    else:
        tables=generate(cfg); detections=detect(tables); report=validate(tables,detections); result=export(tables,report,cfg,args.out)
    result["validation_status"]=report["overall_status"]; result["detected_issue_count"]=len(detections['issues']); result["failed_checks"]=report["failed_checks"]
    print(json.dumps(result,indent=2))
    if report["overall_status"]!="PASS": raise SystemExit(1)

if __name__=="__main__": main()
