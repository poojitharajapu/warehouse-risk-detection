# Business rules and assumptions

## Synthetic generation

Dates are ISO-8601 with UTC offsets. The default start is `2026-01-01T00:00:00+00:00`; sensor readings are 15 minutes apart. The fixed seed is `20261022`; Python `random.Random(seed)` controls sensor noise and a separate derived seed controls occupancy noise. Same code, config, and seed produce the same logical rows, IDs, and hashes. The generation timestamp in the manifest is intentionally variable and excluded from comparisons.

Sensor values use a repeating eight-sample time pattern around 5 °C for cold temperature sensors, 22 °C for ambient temperature sensors, or 50% RH for humidity, plus Gaussian noise with standard deviation 0.12. Door events have deterministic varied hours and one to four minute durations. Inventory records are assigned to zones in a capacity-respecting pattern.

## Occupancy

Occupancy means the number of people physically present in a zone at a timestamp. It is recorded hourly in `occupancy_readings` as `people_count`; it is not derived from or compared with stock quantity. Cold zones have a default limit of 20 people; ambient zones have a default limit of 50. These limits are configurable through `Config`. Counts below or equal to the limit are allowed; counts above it create HIGH severity `OCCUPANCY_THRESHOLD` alerts. The generator creates normal measurements throughout the day and one labeled over-limit reading at the final timestamp of the first zone. The controlled case is `NEG-05`; the original four challenge scenarios are retained.

## Risk rules

| Risk | Rule and severity |
|---|---|
| Temperature | Values outside the zone's inclusive min/max °C range create HIGH severity alerts. Boundary values are allowed. |
| Humidity | Values outside the zone's inclusive min/max %RH range create MEDIUM severity alerts. |
| Monitoring gap | A gap over 22.5 minutes between readings is an unknown coverage condition, never proof of normal conditions; MEDIUM review alert. |
| Sensor drift | For at least 16 readings, compare the mean of the first and last eight-reading cycles; absolute change over 2 units flags MEDIUM calibration review. Matching cycle phases prevents the normal repeating pattern from creating false drift. This is still a simple heuristic, not calibration-grade analysis. |
| Door open | Duration over configurable `door_open_limit_seconds` (default 300 seconds) creates a HIGH alert. |
| Storage compatibility | A lot whose `product_class` differs from its zone requirement creates a HIGH inventory alert. |
| Sensor-zone mapping | Multiple active zones require an `assignment_reason` on each active assignment; otherwise create a HIGH integrity alert. |
| Alarm-lot traceability | An inventory-impacting alarm with no affected-lot bridge row creates a HIGH integrity alert. Affected lots are selected by zone and receipt-to-expiry time overlap. |
| Inventory capacity | Sum of lot quantities must not exceed `capacity_units`; this is stock volume, not people occupancy. |
| Occupancy | Person count above `occupancy_capacity_persons` creates HIGH severity; exactly the limit is allowed. |

Every alert records warehouse, zone, source record, risk type, severity, detection time, and explanation. Inventory is linked only when the risk represents inventory impact. The NEG-04 unlinked alarm is an intentional challenge fixture and is reported separately.

## Alarm, inspection, remediation lifecycles

Legal state changes are:

| Entity | Allowed transitions |
|---|---|
| Alarm | initial → OPEN → ACKNOWLEDGED → RESOLVED → CLOSED; OPEN may also resolve directly. |
| Inspection | initial → OPEN → IN_PROGRESS → COMPLETED; OPEN may also complete directly. |
| Remediation | initial → OPEN → IN_PROGRESS → COMPLETED or CANCELLED; OPEN may be cancelled. |

`state_history` stores an initial event and each transition with a timestamp, previous/new state, typed entity reference, and reason. Generated risk records are currently ACKNOWLEDGED; inspections and remediations are IN_PROGRESS. These are synthetic lifecycle examples, not claims that a real person performed the work. Historical rows are retained; current status must equal the latest event.

## Negative fixtures and uncertainty

Five labeled test cases exist: incompatible lot (`NEG-01`), undocumented multiple-zone sensor mapping (`NEG-02`), omitted reading (`NEG-03`), unlinked inventory alarm (`NEG-04`), and over-limit occupancy (`NEG-05`). Ground truth is never passed to detection. Expected fixture defects are reported as `EXPECTED_ANOMALY`; accidental integrity failures remain `FAIL` and determine overall validation status. Missing data remains unknown rather than normal.
