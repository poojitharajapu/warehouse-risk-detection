# Source and artifact manifest

## Data provenance

All warehouse records in this project are generated locally by `src/warehouse_monitoring/generator.py`. The project does not use a customer database, live warehouse feed, external API, or downloaded dataset. The seeded generator creates warehouses, zones, sensors, sensor readings, occupancy readings, inventory lots, storage requirements, door events, controlled anomaly fixtures, and ground-truth labels.

The four original controlled fixtures are retained, and a fifth fixture demonstrates occupancy above a configured zone limit. Ground-truth labels are exported for validation and evaluation; the risk detector does not consume them. See [business rules](business_rules.md) for thresholds and [data dictionary](data_dictionary.md) for fields and relationships.

## Reproduction

The documented full baseline uses seed `20261022` and the configuration in [baseline_manifest.json](baseline_manifest.json). Run the commands in the [README](../README.md) to regenerate it. `generated_at` is set at run time and will differ; canonical data hashes, schemas, row counts, and validation results are deterministic for the same seed and configuration.

The checked baseline manifest records the output schema, row counts, and canonical hashes. The corresponding validation details are in [validation_report.json](validation_report.json), and the commands actually run are summarized in [verification_results.md](verification_results.md). Generated CSVs and local environments are ignored through `.gitignore`; no generated dataset is embedded in this source manifest.

## Limitations

Synthetic values are suitable for exercising project logic and reproducibility only. They do not establish real-world sensor performance, occupancy accuracy, warehouse safety, or production alarm readiness. No external sources or external assets were used.
