# Data dictionary

All keys are strings. Timestamps are ISO-8601 strings with UTC offsets. Numeric environmental values use °C or percent relative humidity (`%RH`); people counts are integer persons; inventory quantities are integer stock units. Empty strings are used only for documented optional fields. Every CSV is UTF-8 and uses the column schemas in `manifest.json`.

## Entities and tables

| Entity / CSV | Fields, keys, constraints and meaning |
|---|---|
| Warehouse / `warehouses` | `warehouse_id` PK; `name` required string; `region` North/South/East/West; `capacity_units` positive integer inventory units. One warehouse has many zones and inventory lots. |
| Zone / `zones` | `zone_id` PK; `warehouse_id` FK; `name`; `zone_type` COLD/AMBIENT; `capacity_units` positive inventory units; `occupancy_capacity_persons` positive integer human capacity, a separate concept. One zone has one storage requirement and many sensors, readings, events, and lots. |
| Sensor / `sensors` | `sensor_id` PK; `zone_id` FK; `sensor_type` TEMPERATURE/HUMIDITY; `unit` C/PCT; `status` ACTIVE. A sensor has many readings and effective dated zone assignments. |
| SensorReading / `sensor_readings` | `reading_id` PK; `sensor_id`,`zone_id` FKs; `timestamp`; numeric `value`; `unit` C/PCT; `quality` GOOD/SUSPECT/MISSING. `(sensor_id,timestamp)` is unique. |
| OccupancyReading / `occupancy_readings` | `occupancy_reading_id` PK; `zone_id` FK; `timestamp`; `people_count` nonnegative integer persons; `measurement_method` SYNTHETIC_COUNT; `quality` GOOD/SUSPECT. `(zone_id,timestamp)` is unique. This measures people, never inventory. |
| DoorEvent / `door_events` | `event_id` PK; `zone_id` FK; `opened_at`,`closed_at`; `duration_seconds` nonnegative integer equal to the timestamp difference. |
| InventoryLot / `inventory_lots` | `lot_id` PK; `warehouse_id`,`zone_id` FKs that must agree; `product_class` CHILLED/AMBIENT; `quantity` positive integer stock units; `received_at`,`expires_at` with receipt before expiry. |
| StorageRequirement / `storage_requirements` | `requirement_id` PK; unique `zone_id` FK; `product_class`; min/max temperature °C and humidity %RH with minimum ≤ maximum. |
| Alarm / `alarms` | `alarm_id` PK; `warehouse_id`,`zone_id` FKs; optional `source_sensor_id` FK; `source_record_id` stable source identifier; `incident_at`,`detection_timestamp`; `rule_id`,`risk_type`,`severity` LOW/MEDIUM/HIGH, `explanation`; `inventory_impact_expected` boolean; `status` OPEN/ACKNOWLEDGED/RESOLVED/CLOSED. A repeated `(risk_type,source_record_id)` is idempotent. |
| Inspection / `inspections` | `inspection_id` PK; `alarm_id` FK; `inspected_at`; `outcome` REVIEW_REQUIRED/CONFIRMED/CLEARED; lifecycle `status` OPEN/IN_PROGRESS/COMPLETED. |
| Remediation / `remediations` | `remediation_id` PK; `inspection_id` FK; `created_at`; `action`; lifecycle `status` OPEN/IN_PROGRESS/COMPLETED/CANCELLED. |
| AlarmLot / `alarm_lots` | Composite PK (`alarm_id`,`lot_id`); both FKs. Many-to-many link to lots whose zone and dwell interval overlap an inventory-impacting alert. No link is fabricated for occupancy counts. |
| SensorZoneAssignment / `sensor_zone_assignments` | Logical unique key (`sensor_id`,`zone_id`,`valid_from`); sensor and zone FKs; `valid_from`,`valid_to`; optional `assignment_reason`. Multiple active zones require a documented reason. |
| StateHistory / `state_history` | `history_id` PK; `entity_type` ALARM/INSPECTION/REMEDIATION; polymorphic `entity_id` FK resolved by type; `previous_state`,`new_state`; `event_timestamp`; `reason`. Rows are append-only and chronologically chained per entity. |
| GroundTruth / `ground_truth` | Composite logical key (`scenario_id`,`entity_id`); `expected_issue`,`expected_label`,`details`. Evaluation metadata only; detector code does not read it. |

## Relationships

- Warehouse 1:N Zone and InventoryLot.
- Zone 1:N Sensor, SensorReading, OccupancyReading, DoorEvent, and InventoryLot; Zone 1:1 StorageRequirement.
- Sensor 1:N SensorReading and SensorZoneAssignment.
- Alarm M:N InventoryLot through `alarm_lots`.
- Alarm 1:N Inspection; Inspection 1:N Remediation.
- Alarm, Inspection, and Remediation each 1:N StateHistory events. The typed history relation is polymorphic and validated against the corresponding table.
- Ground truth is separate from operational entity relationships and from detector inputs.

`capacity_units` is stock capacity. `occupancy_capacity_persons` is a human safety limit. These values and their validation rules are never compared or substituted for one another.
