# Verification results

Verified on 2026-10-27 in the supplied Windows workspace. These commands and results were executed by the coding agent.

## Automated tests

Command: `.venv\Scripts\python.exe -m pytest -q`

Actual result: `14 passed in 0.37s`.

Coverage includes occupancy below/at/above its limit, occupancy fixture detection, valid and invalid state transitions, history retention and chronology, timestamp and lifecycle date failures, temperature/humidity boundaries, reading gaps, drift, door duration, inventory compatibility, mapping integrity and documented reasons, alarm-to-lot traceability, deterministic generation, ground-truth separation, duplicate/FK failures, streamed export consistency, and configured baseline dimensions.

## Full baseline generation

Command: `.venv\Scripts\warehouse-monitor.exe generate --size baseline --seed 20261022 --out outputs/baseline`

| Entity/table | Rows |
|---|---:|
| warehouses | 10 |
| zones | 100 |
| sensors | 500 |
| sensor_readings | 1,000,000 |
| occupancy_readings | 2,400 |
| inventory_lots | 10,000 |
| door_events | 100 |
| storage_requirements | 100 |
| alarms | 7 |
| inspections | 7 |
| remediations | 7 |
| alarm_lots | 100 |
| sensor_zone_assignments | 501 |
| state_history | 42 |
| ground_truth | 5 |

Validation: **PASS**; 58 checks passed, 4 intentional integrity anomalies reported separately, 0 unexpected failures. All five ground-truth cases were detected. The missing-reading case is reported as unknown monitoring coverage, not normal conditions. Generated outputs are local under the ignored `outputs/` directory; the detailed report and manifest are retained as documentation artifacts.

## Full-scale reproducibility

Two baseline runs used seed `20261022` in `outputs/baseline` and `outputs/baseline-repro`. Command: `.venv\Scripts\python.exe scripts/compare_runs.py outputs/baseline outputs/baseline-repro`.

Actual result: `MATCH: seed, configuration, schemas, row counts, canonical hashes, and validation summary`.

`generated_at` differs by design and is excluded from deterministic comparisons. The full baseline manifest and validation report are retained in `docs/baseline_manifest.json` and `docs/validation_report.json`.

## Dashboard smoke test

Command: `.venv\Scripts\python.exe -c "from streamlit.testing.v1 import AppTest; a=AppTest.from_file('src/warehouse_monitoring/dashboard.py').run(timeout=30); assert not a.exception; print('dashboard exceptions:', len(a.exception))"`

Actual result: `dashboard exceptions: 0` against the generated full-baseline output.
