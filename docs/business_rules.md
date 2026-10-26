# Business rules and assumptions

All dates are ISO-8601 with UTC offsets. Synthetic start defaults to 2026-01-01 UTC; sensor interval defaults to 15 minutes. Random values use Python `random.Random(seed)`; seed default is `20261022`. Each sensor follows a repeating eight-sample time pattern around a zone/type baseline, plus Gaussian noise with standard deviation 0.12; cold temperature centers on 5 °C, ambient on 22 °C, and humidity on 50% RH. Door events occur at deterministic varied hours and have 1–4 minute durations.

| Rule | Decision |
|---|---|
| Cold storage | Cold zones require CHILLED stock and 2–8 °C; ambient zones require AMBIENT stock and 15–30 °C. |
| Humidity | Requirement defaults are 20–80 percent relative humidity. Values outside that inclusive band generate medium severity alarms. |
| Temperature excursion | A temperature observation below/above its zone requirement creates a high severity derived alarm. Boundary values are in range. |
| Missing data | A gap greater than 22.5 minutes between consecutive observations from one sensor is a coverage issue. A gap is unknown, never normal. |
| Drift | For five or more records, absolute first-to-last movement over 2 °C or percentage points flags review. This simple endpoint rule is not calibration-grade. |
| Affected inventory | Link only lots in the same zone whose receipt-to-expiry interval includes the incident time. `alarm_lots` is the bridge. |
| Door events | Events store open, close, and duration. Duration above configurable `door_open_limit_seconds` (default 300 seconds) is an abnormal-open issue. |
| Capacity | Zone capacity is 1,000 units; warehouse capacity is 10,000. The small configuration uses 100-unit lots; baseline uses 9-unit lots (900 units per zone) to preserve headroom for the single incompatible-lot fixture. |
| Lifecycle | Generated alerts start OPEN, inspections REVIEW_REQUIRED, and remediation OPEN. This records proposed work, not a claimed completion. |
| Negative fixtures | Four single-purpose, reproducible defects are in ground truth and are separately reported as expected anomalies. |

Uncertainty is retained: absence of a reading is an outage/gap signal, not a normal environmental value. Detector inputs exclude the ground-truth table.
