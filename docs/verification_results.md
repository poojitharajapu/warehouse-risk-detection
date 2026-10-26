# Verification results

Verified on 2026-10-26 in the supplied Windows workspace.

## Automated tests

Commands: `.venv\Scripts\python.exe -m pytest -q` and `python -m unittest discover -s tests -v`.

Result: **10 tests passed** under pytest (`10 passed in 0.41s`) and **10 tests passed** under unittest. Coverage includes the four required negative scenarios, deterministic in-memory generation, streaming/in-memory reading equality, exact baseline dimensions, threshold boundary behavior for temperature and humidity, affected inventory selection, door-duration and sensor-drift signals, foreign-key and duplicate-key failures, unexpected orphan alarms, and export read-back.

## Full baseline generation

Command: `python -m warehouse_monitoring.cli generate --size baseline --seed 20261022 --out outputs/baseline`

| Entity/table | Rows |
|---|---:|
| warehouses | 10 |
| zones | 100 |
| sensors | 500 |
| sensor_readings | 1,000,000 |
| inventory_lots | 10,000 |
| door_events | 100 |
| storage_requirements | 100 |
| alarms | 2 |
| inspections | 1 |
| remediations | 1 |
| alarm_lots | 99 |
| sensor_zone_assignments | 501 |
| ground_truth | 4 |

Validation result: **PASS**, 0 unexpected failures. All four labeled challenge fixtures were detected. The one source excursion generated an alarm linked to the 99 same-zone lots overlapping the incident time; the intentionally unlinked alarm is separately labeled as a fixture.

## Full-scale reproducibility

Two full baseline runs used seed `20261022` in `outputs/baseline` and `outputs/baseline-repro`. Command: `python scripts/compare_runs.py outputs/baseline outputs/baseline-repro`.

Actual result: `MATCH: seed, configuration, schemas, row counts, canonical hashes, and validation summary`.

The run timestamps differ by design and are excluded. Output files are under the Git-ignored `outputs/` directory; the compact validation report and manifest evidence are retained in this repository.
