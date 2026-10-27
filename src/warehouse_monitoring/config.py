"""Configuration and documented defaults for synthetic data."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    warehouses: int = 10
    zones_per_warehouse: int = 10
    sensors_per_zone: int = 5
    readings_per_sensor: int = 20
    lots_per_warehouse: int = 10
    lot_quantity: int = 100
    seed: int = 20261022
    start: str = "2026-01-01T00:00:00+00:00"
    interval_minutes: int = 15
    door_open_limit_seconds: int = 300
    occupancy_samples_per_zone: int = 24
    cold_zone_occupancy_limit: int = 20
    ambient_zone_occupancy_limit: int = 50
    occupancy_anomaly_excess_people: int = 5
    inject_anomalies: bool = True

    @property
    def zones(self): return self.warehouses * self.zones_per_warehouse
    @property
    def sensors(self): return self.zones * self.sensors_per_zone
    @property
    def readings(self): return self.sensors * self.readings_per_sensor
    @property
    def occupancy_readings(self): return self.zones * self.occupancy_samples_per_zone
    @property
    def lots(self): return self.warehouses * self.lots_per_warehouse

    @classmethod
    def small(cls, seed=20261022):
        return cls(warehouses=2, zones_per_warehouse=2, sensors_per_zone=2,
                   readings_per_sensor=8, lots_per_warehouse=3, seed=seed)

    @classmethod
    def baseline(cls, seed=20261022):
        return cls(readings_per_sensor=2000, lots_per_warehouse=1000, lot_quantity=9, seed=seed)
