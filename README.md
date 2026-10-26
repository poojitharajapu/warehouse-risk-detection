# Warehouse Monitoring and Risk Alert System

A locally runnable, deterministic synthetic-data project for warehouse environments. It generates relational CSV exports, derives risk alerts from source records, and separates expected challenge fixtures from accidental integrity failures. Core code uses the Python standard library; pytest is an optional development dependency.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m warehouse_monitoring.cli generate --size small --out outputs/small
python -m pytest -q
```

For the challenge baseline (10 warehouses, 100 zones, 500 sensors, 1,000,000 readings, 10,000 lots):

```powershell
python -m warehouse_monitoring.cli generate --size baseline --out outputs/baseline
```

The baseline uses a streaming path for sensor readings: it generates, validates, hashes, and writes rows incrementally, then reads the CSV back in a streaming pass. The smaller development mode remains convenient for in-memory testing. Use `--seed` to choose another seed; default is `20261022`. Install pytest with the `dev` extra if you prefer `python -m pytest`.

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
4. `validate()` checks uniqueness, key relationships, deliberate negative fixtures, and distinguishes expected fixture failures from unexpected errors.
5. `export()` writes each entity and bridge table as CSV, plus validation JSON and a manifest with canonical hashes. It reads each CSV back and checks row counts.

Ground truth includes the four required controlled scenarios: incompatible product storage, overlapping sensor zone mapping, an omitted sensor sample (unknown coverage), and an unlinked alarm. The validator reports the intentionally malformed records as `EXPECTED_ANOMALY`; the overall status is PASS only when no unexpected check fails. Generator completion alone is not validation evidence.

## Entities

The ten core entities are Warehouse, Zone, Sensor, SensorReading, DoorEvent, InventoryLot, StorageRequirement, Alarm, Inspection, and Remediation. Supporting tables are `alarm_lots` (many-to-many alarm/affected lot), `sensor_zone_assignments` (effective-dated mapping), and `ground_truth` (separate evaluation metadata). Exact field definitions are in [the data dictionary](docs/data_dictionary.md). Assumptions and thresholds are in [business rules](docs/business_rules.md).

## Reproducibility

Generate twice with the same seed into separate folders and run the comparator:

```powershell
python -m warehouse_monitoring.cli generate --size small --seed 20261022 --out outputs/repro-a
python -m warehouse_monitoring.cli generate --size small --seed 20261022 --out outputs/repro-b
python scripts/compare_runs.py outputs/repro-a outputs/repro-b
```

It compares seed, configuration, schemas, row counts, canonical content hashes, and validation summary. `generated_at` intentionally differs and is excluded. CSV outputs are UTF-8.

## Limits

## Optional dashboard

After generating data, install the dashboard extra and run:

```powershell
python -m pip install -e ".[dashboard]"
streamlit run src/warehouse_monitoring/dashboard.py
```

Enter `outputs/baseline` (or another run directory) in the sidebar. The dashboard reads generated files and does not alter them.

## Verified results

The current baseline and reproducibility evidence is in [docs/verification_results.md](docs/verification_results.md); the detailed report is [docs/validation_report.json](docs/validation_report.json). The full baseline was generated twice using seed `20261022`; the comparator reported matching row counts, schemas, hashes, and validation summary. Ten automated checks passed with `python -m pytest -q`.

## Limits

This is a challenge-oriented synthetic reference implementation, not a production alarm service. Detection covers temperature and humidity range excursions, missing sample gaps, storage incompatibility, active mapping multiplicity, unlinked alarms, abnormal door duration, and a basic endpoint drift review. Advanced event state transitions and real sensor calibration remain future extensions.

## AI prompt history

See [prompts/README.md](prompts/README.md). The supplied master prompt is recorded as a user-provided prompt, with the implementation review note clearly separated from claims about personal testing.
