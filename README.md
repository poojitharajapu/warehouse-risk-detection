# Warehouse Monitoring and Risk Alert System

A locally runnable, deterministic warehouse monitoring project. It generates relational CSV exports, detects environmental, inventory, mapping, and human occupancy risks, records lifecycle transitions, and distinguishes expected fixtures from accidental integrity failures. Core logic uses the Python standard library; pytest and Streamlit are optional extras.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m warehouse_monitoring.cli generate --size small --out outputs/small
python -m pytest -q
```

For the challenge baseline (10 warehouses, 100 zones, 500 sensors, 1,000,000 readings, 10,000 lots, and 2,400 hourly occupancy snapshots):

```powershell
python -m warehouse_monitoring.cli generate --size baseline --out outputs/baseline
```

The baseline streams sensor readings through generation, hashing, CSV writing, and read-back. Occupancy and reference tables are much smaller and are generated in memory. Use `--seed` to choose another seed; default is `20261022`.

## Layout

```text
src/warehouse_monitoring/  configuration, generator, rules, validation, exports, CLI
docs/                      data dictionary, business rules, source manifest
prompts/                   actual prompt history and authorship notes
tests/                     automated correctness and integrity checks
outputs/                   generated artifacts (ignored by Git)
```

## Workflow

1. `Config` sets volumes, seed, start time, and interval.
2. `generate()` builds parent entities before dependent records and records explicit, deterministic fixtures in ground truth.
3. `detect()` reads operational records only. It does not read ground truth.
4. `record_alarm()` writes traceable, idempotent alerts and state changes.
5. `validate()` checks key integrity, occupancy limits, lifecycle transitions, expected fixtures, and accidental failures.
6. `export()` writes entities, bridge/history tables, validation JSON, and a deterministic manifest. It reads each CSV back and checks schemas, row counts, IDs, and relationships.

Ground truth includes the four original controlled scenarios plus one over-limit occupancy case. The detector never reads labels. The validator reports intentional defects as `EXPECTED_ANOMALY`; overall status is PASS only when no unexpected check fails. Missing readings mean unknown coverage, not normal conditions.

## Entities

The original ten core entities remain. `OccupancyReading` models human counts separately from inventory quantities. `state_history` captures timestamped Alarm, Inspection, and Remediation transitions. Bridge tables are `alarm_lots` and `sensor_zone_assignments`; `ground_truth` remains separate detector input. Fields and cardinalities are documented in [the data dictionary](docs/data_dictionary.md), with assumptions and thresholds in [business rules](docs/business_rules.md).

## Reproducibility

Generate twice with the same seed into separate folders and run the comparator:

```powershell
python -m warehouse_monitoring.cli generate --size small --seed 20261022 --out outputs/repro-a
python -m warehouse_monitoring.cli generate --size small --seed 20261022 --out outputs/repro-b
python scripts/compare_runs.py outputs/repro-a outputs/repro-b
```

It compares seed, configuration, schemas, row counts, canonical content hashes, and validation summary. `generated_at` intentionally differs and is excluded. CSV outputs are UTF-8.

For a full-scale reproducibility comparison, replace the `small` output paths with these two baseline commands:

```powershell
python -m warehouse_monitoring.cli generate --size baseline --seed 20261022 --out outputs/baseline-a
python -m warehouse_monitoring.cli generate --size baseline --seed 20261022 --out outputs/baseline-b
python scripts/compare_runs.py outputs/baseline-a outputs/baseline-b
```

The million-reading CSV is about 125 MB and remains ignored by Git; the manifest records its hash.

## Optional dashboard

After generating data, install the dashboard extra and run:

```powershell
python -m pip install -e ".[dashboard]"
streamlit run src/warehouse_monitoring/dashboard.py
```

Enter `outputs/baseline` (or another run directory) in the sidebar. It reads occupancy, alerts, affected inventory, lifecycle events, and validation output without modifying source data. It has no external API dependency.

## Verified results

The current baseline and reproducibility evidence is in [docs/verification_results.md](docs/verification_results.md); the detailed report and manifest are [docs/validation_report.json](docs/validation_report.json) and [docs/baseline_manifest.json](docs/baseline_manifest.json). The full baseline was generated twice using seed `20261022`; hashes, schemas, counts, and validation summary matched. Fourteen tests passed with `.venv\Scripts\python.exe -m pytest -q`. The dashboard smoke test rendered with zero exceptions.

## Limits

This is a synthetic challenge implementation, not a production alarm service. Occupancy uses simulated person counts rather than access-control data. Drift uses phase-aligned eight-observation averages, not calibration-grade analysis. Lifecycle actors and transitions are synthetic. The optional dashboard dependency must be installed separately.

## AI prompt history

See [prompts/README.md](prompts/README.md). The supplied master prompt is recorded as a user-provided prompt, with the implementation review note clearly separated from claims about personal testing.
