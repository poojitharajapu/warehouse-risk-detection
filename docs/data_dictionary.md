# Data dictionary

All identifiers are strings and primary keys are unique. `*_id` references are foreign keys unless noted. Timestamps are ISO-8601 strings with UTC offsets. Generated foreign keys are checked by the validator. Blank `valid_to` means the mapping is currently active.

| Entity / CSV | Fields (type, constraints, meaning) |
|---|---|
| Warehouse / `warehouses` | `warehouse_id` PK; `name` string; `region` enum North/South/East/West; `capacity_units` integer units. |
| Zone / `zones` | `zone_id` PK; `warehouse_id` FK; `name` string; `zone_type` COLD/AMBIENT; `capacity_units` integer units. |
| Sensor / `sensors` | `sensor_id` PK; `zone_id` FK; `sensor_type` TEMPERATURE/HUMIDITY; `unit` C/PCT; `status` ACTIVE. |
| SensorReading / `sensor_readings` | `reading_id` PK; `sensor_id`,`zone_id` FKs; `timestamp` ISO-8601; `value` numeric °C or %RH; `unit` C/PCT; `quality` GOOD. |
| DoorEvent / `door_events` | `event_id` PK; `zone_id` FK; `opened_at`,`closed_at` timestamps; `duration_seconds` nonnegative seconds, expected to reconcile with timestamps. |
| InventoryLot / `inventory_lots` | `lot_id` PK; `warehouse_id`,`zone_id` FKs; `product_class` CHILLED/AMBIENT; `quantity` integer units; `received_at`,`expires_at` timestamps. |
| StorageRequirement / `storage_requirements` | `requirement_id` PK; `zone_id` unique FK; `product_class`; min/max temperature °C; min/max humidity %RH. |
| Alarm / `alarms` | `alarm_id` PK; `zone_id`,`source_sensor_id` FKs; `incident_at`; `rule_id`; severity HIGH/MEDIUM; status OPEN. |
| Inspection / `inspections` | `inspection_id` PK; `alarm_id` FK; `inspected_at`; outcome REVIEW_REQUIRED. |
| Remediation / `remediations` | `remediation_id` PK; `inspection_id` FK; `action`; status OPEN. |
| AlarmLot / `alarm_lots` | Composite key (`alarm_id`,`lot_id`); both FKs; records affected inventory. |
| SensorZoneAssignment / `sensor_zone_assignments` | Composite logical key (`sensor_id`,`zone_id`,`valid_from`); FKs; `valid_from`,`valid_to` effective timestamps. Overlapping active distinct zones are invalid. |
| GroundTruth / `ground_truth` | `scenario_id`,`entity_id`,`expected_issue`,`expected_label`,`details`; evaluation metadata, never detector input. |

No nulls are emitted in required fields. Quantities are units, durations seconds, temperature degrees Celsius, humidity percent relative humidity. Sensor IDs use a stable zone/type/sequence pattern; reading IDs use sensor plus sequence. The deliberate mapping fixture intentionally violates active one-zone mapping.
