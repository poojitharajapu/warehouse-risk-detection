"""Compare deterministic manifests from two generated output directories."""
import json, sys
from pathlib import Path

def main():
    if len(sys.argv)!=3: raise SystemExit("Usage: python scripts/compare_runs.py outputs/run-a outputs/run-b")
    a=json.loads((Path(sys.argv[1])/'manifest.json').read_text(encoding='utf-8'))
    b=json.loads((Path(sys.argv[2])/'manifest.json').read_text(encoding='utf-8'))
    keys=('seed','configuration','row_counts','canonical_sha256','schemas')
    mismatches=[k for k in keys if a.get(k)!=b.get(k)]
    ra=json.loads((Path(sys.argv[1])/'validation_report.json').read_text(encoding='utf-8'))
    rb=json.loads((Path(sys.argv[2])/'validation_report.json').read_text(encoding='utf-8'))
    if (ra['overall_status'],ra['passed_checks'],ra['failed_checks']) != (rb['overall_status'],rb['passed_checks'],rb['failed_checks']): mismatches.append('validation_summary')
    if mismatches: raise SystemExit('MISMATCH: '+', '.join(mismatches))
    print('MATCH: seed, configuration, schemas, row counts, canonical hashes, and validation summary')

if __name__=='__main__': main()
