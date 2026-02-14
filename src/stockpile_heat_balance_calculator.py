"""
Stockpile Heat Balance Calculator
====================================
Model the thermal heat balance of a coal stockpile to predict internal
temperature rise and time-to-critical conditions for spontaneous combustion
management.

This module complements the SpontaneousCombustionRiskAssessor by providing
a time-domain simulation of stockpile temperature based on:
  1. Oxidation heat generation (function of rank, surface area, temperature)
  2. Convective heat dissipation (wind, surface area)
  3. Evaporative cooling (moisture loss)
  4. Conductive heat exchange with ground

Suitable for: stockpile monitoring planning, insurance risk reports, mine
safety permit applications.

References
----------
- Carras & Young (1994) Self-heating of coal and related materials. Progress in Energy
  and Combustion Science 20(1):1–15.
- Nugroho et al. (2000) Thermal analysis of Indonesian and Australian coals.
  Fuel 79(14):1951–1961.
- DNRME (2017) Guidance Note: Spontaneous Combustion Management. Queensland Government.

Example
-------
>>> from src.stockpile_heat_balance_calculator import StockpileHeatBalanceCalculator
>>> calc = StockpileHeatBalanceCalculator(
...     coal_rank="subbituminous",
...     stockpile_volume_m3=5000.0,
...     stockpile_height_m=8.0,
...     initial_temperature_c=25.0,
... )
>>> result = calc.simulate(days=30)
>>> print(f"Day 30 temperature: {result.daily_records[-1].temperature_c:.1f}°C")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Literal, Optional

CoalRank = Literal["lignite", "subbituminous", "bituminous", "anthracite"]
VALID_RANKS = frozenset(["lignite", "subbituminous", "bituminous", "anthracite"])

# ---------------------------------------------------------------------------
# Coal rank thermodynamic parameters (Carras & Young 1994; Nugroho et al. 2000)
# ---------------------------------------------------------------------------

# Oxidation heat generation rate constant Q0 (W/kg) at T_ref = 25°C
_Q0: dict = {
    "lignite":       0.020,
    "subbituminous": 0.015,
    "bituminous":    0.008,
    "anthracite":    0.002,
}

# Activation energy Ea (kJ/mol) — Arrhenius temperature dependence
_EA_kJ_MOL: dict = {
    "lignite":       40.0,
    "subbituminous": 45.0,
    "bituminous":    55.0,
    "anthracite":    70.0,
}

# Bulk density (kg/m³)
_BULK_DENSITY: dict = {
    "lignite":       700.0,
    "subbituminous": 800.0,
    "bituminous":    900.0,
    "anthracite":    1000.0,
}

# Specific heat capacity Cp (J/kg·K)
_CP: dict = {
    "lignite":       1300.0,
    "subbituminous": 1200.0,
    "bituminous":    1100.0,
    "anthracite":    900.0,
}

_R_GAS: float = 8.314e-3   # kJ/mol·K (universal gas constant)
_T_REF_K: float = 298.15   # Reference temperature (25°C in Kelvin)

# Convective heat transfer coefficient h (W/m²·K)
_H_CONV: float = 5.0       # natural convection; 10–15 W/m²·K for forced (wind)


@dataclass
class DailyRecord:
    """Single-day result in the heat balance simulation."""
    day: int
    temperature_c: float
    heat_generation_w: float     # oxidation heat (W)
    heat_loss_w: float           # convective + evaporative loss (W)
    net_heat_w: float            # heat_generation - heat_loss
    risk_flag: str               # OK / WATCH / WARNING / CRITICAL
    cumulative_temp_rise_c: float


@dataclass
class SimulationResult:
    """Full result of a stockpile heat balance simulation."""
    coal_rank: str
    stockpile_volume_m3: float
    initial_temperature_c: float
    days_simulated: int
    daily_records: List[DailyRecord] = field(default_factory=list)
    critical_day: Optional[int] = None     # first day reaching ≥150°C (pre-ignition threshold)
    peak_temperature_c: float = 0.0
    time_to_watch_days: Optional[int] = None    # ≥70°C
    time_to_warning_days: Optional[int] = None  # ≥100°C

    def summary(self) -> dict:
        return {
            "coal_rank": self.coal_rank,
            "stockpile_volume_m3": self.stockpile_volume_m3,
            "initial_temperature_c": self.initial_temperature_c,
            "days_simulated": self.days_simulated,
            "peak_temperature_c": round(self.peak_temperature_c, 2),
            "critical_day": self.critical_day,
            "time_to_watch_days": self.time_to_watch_days,
            "time_to_warning_days": self.time_to_warning_days,
        }


class StockpileHeatBalanceCalculator:
    """
    Simulate thermal heat balance of a coal stockpile over time.

    Parameters
    ----------
    coal_rank : CoalRank
        Coal rank class (lignite, subbituminous, bituminous, anthracite).
    stockpile_volume_m3 : float
        Total stockpile volume in m³ (> 0).
    stockpile_height_m : float
        Mean stockpile height in metres (> 0; used to estimate surface area).
    initial_temperature_c : float
        Starting core temperature in °C (−10 to 60).
    ambient_temperature_c : float
        Ambient air temperature in °C (−20 to 55).
    wind_speed_m_s : float
        Mean wind speed over stockpile in m/s (0–30). Increases convective cooling.
    moisture_content_pct : float
        Surface moisture content (%). Higher moisture → more evaporative cooling.
    volatile_matter_pct : float, optional
        VM on dry ash-free basis. If provided, adjusts Q0 scaling.
    """

    def __init__(
        self,
        coal_rank: CoalRank,
        stockpile_volume_m3: float,
        stockpile_height_m: float,
        initial_temperature_c: float = 25.0,
        ambient_temperature_c: float = 28.0,
        wind_speed_m_s: float = 2.0,
        moisture_content_pct: float = 12.0,
        volatile_matter_pct: Optional[float] = None,
    ) -> None:
        if coal_rank not in VALID_RANKS:
            raise ValueError(f"coal_rank must be one of {sorted(VALID_RANKS)}")
        if stockpile_volume_m3 <= 0:
            raise ValueError("stockpile_volume_m3 must be > 0")
        if stockpile_height_m <= 0:
            raise ValueError("stockpile_height_m must be > 0")
        if not (-10.0 <= initial_temperature_c <= 60.0):
            raise ValueError("initial_temperature_c must be between -10 and 60")
        if not (-20.0 <= ambient_temperature_c <= 55.0):
            raise ValueError("ambient_temperature_c must be between -20 and 55")
        if not (0.0 <= wind_speed_m_s <= 30.0):
            raise ValueError("wind_speed_m_s must be between 0 and 30")
        if not (0.0 <= moisture_content_pct <= 60.0):
            raise ValueError("moisture_content_pct must be between 0 and 60")
        if volatile_matter_pct is not None and not (0.0 <= volatile_matter_pct <= 100.0):
            raise ValueError("volatile_matter_pct must be between 0 and 100")

        self.coal_rank = coal_rank
        self.stockpile_volume_m3 = stockpile_volume_m3
        self.stockpile_height_m = stockpile_height_m
        self.initial_temperature_c = initial_temperature_c
        self.ambient_temperature_c = ambient_temperature_c
        self.wind_speed_m_s = wind_speed_m_s
        self.moisture_content_pct = moisture_content_pct
        self.volatile_matter_pct = volatile_matter_pct

        # Derived quantities
        self._mass_kg = stockpile_volume_m3 * _BULK_DENSITY[coal_rank]
        self._surface_area_m2 = self._estimate_surface_area()
        self._h_eff = self._effective_heat_transfer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(self, days: int = 60, time_step_hours: float = 1.0) -> SimulationResult:
        """
        Run the heat balance simulation over a given number of days.

        Parameters
        ----------
        days : int
            Simulation horizon in days (1–365).
        time_step_hours : float
            Time step size in hours (0.1–24). Smaller = more accurate.

        Returns
        -------
        SimulationResult
        """
        if days < 1:
            raise ValueError("days must be >= 1")
        if days > 365:
            raise ValueError("days must be <= 365")
        if not (0.1 <= time_step_hours <= 24.0):
            raise ValueError("time_step_hours must be between 0.1 and 24")

        dt_seconds = time_step_hours * 3600.0
        steps_per_day = max(1, round(24.0 / time_step_hours))
        T = self.initial_temperature_c
        result = SimulationResult(
            coal_rank=self.coal_rank,
            stockpile_volume_m3=self.stockpile_volume_m3,
            initial_temperature_c=self.initial_temperature_c,
            days_simulated=days,
        )

        for day in range(1, days + 1):
            for _ in range(steps_per_day):
                T = self._step(T, dt_seconds)

            # End-of-day record
            Q_gen = self._heat_generation_w(T)
            Q_loss = self._heat_loss_w(T)
            net = Q_gen - Q_loss
            flag = self._risk_flag(T)
            record = DailyRecord(
                day=day,
                temperature_c=round(T, 3),
                heat_generation_w=round(Q_gen, 2),
                heat_loss_w=round(Q_loss, 2),
                net_heat_w=round(net, 2),
                risk_flag=flag,
                cumulative_temp_rise_c=round(T - self.initial_temperature_c, 3),
            )
            result.daily_records.append(record)

            if result.time_to_watch_days is None and T >= 70.0:
                result.time_to_watch_days = day
            if result.time_to_warning_days is None and T >= 100.0:
                result.time_to_warning_days = day
            if result.critical_day is None and T >= 150.0:
                result.critical_day = day

        result.peak_temperature_c = round(max(r.temperature_c for r in result.daily_records), 3)
        return result

    def equilibrium_temperature_c(self) -> float:
        """
        Estimate the steady-state equilibrium temperature where heat generation = heat loss.
        Uses a bisection search.
        """
        lo, hi = self.ambient_temperature_c, 300.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if self._heat_generation_w(mid) > self._heat_loss_w(mid):
                lo = mid
            else:
                hi = mid
        return round((lo + hi) / 2, 2)

    # ------------------------------------------------------------------
    # Internal: thermodynamics
    # ------------------------------------------------------------------

    def _step(self, T: float, dt_s: float) -> float:
        """Forward Euler temperature update."""
        Q_gen = self._heat_generation_w(T)
        Q_loss = self._heat_loss_w(T)
        dT = (Q_gen - Q_loss) / (self._mass_kg * _CP[self.coal_rank])
        return T + dT * dt_s

    def _heat_generation_w(self, T_c: float) -> float:
        """Arrhenius oxidation heat generation (W)."""
        T_k = T_c + 273.15
        Q0 = _Q0[self.coal_rank]
        if self.volatile_matter_pct is not None:
            Q0 *= max(0.5, self.volatile_matter_pct / 35.0)  # normalise to 35% VM baseline
        Ea = _EA_kJ_MOL[self.coal_rank]
        try:
            arrhenius = math.exp(-Ea / (_R_GAS * T_k) + Ea / (_R_GAS * _T_REF_K))
        except OverflowError:
            arrhenius = 1e10
        return Q0 * self._mass_kg * arrhenius

    def _heat_loss_w(self, T_c: float) -> float:
        """Convective + evaporative heat loss (W)."""
        conv = self._h_eff * self._surface_area_m2 * max(0.0, T_c - self.ambient_temperature_c)
        # Evaporative cooling: latent heat of vaporisation × moisture evaporation rate
        evap = 0.0
        if self.moisture_content_pct > 0 and T_c > self.ambient_temperature_c:
            evap_rate_kg_s = max(0.0, (T_c - self.ambient_temperature_c) * 1e-6 * self.moisture_content_pct)
            evap = evap_rate_kg_s * 2_450_000.0  # L_v = 2.45 MJ/kg
        return conv + evap

    def _effective_heat_transfer(self) -> float:
        """Effective convective h accounting for wind speed."""
        # h_eff = h_conv + 3*wind (simplified forced convection correction)
        return _H_CONV + 3.0 * self.wind_speed_m_s

    def _estimate_surface_area_m2(self) -> float:
        return self._estimate_surface_area()

    def _estimate_surface_area(self) -> float:
        """
        Estimate surface area of a cone-shaped stockpile given volume and height.
        V_cone = (1/3)*π*r²*h → r = sqrt(3V/(πh))
        Lateral area = π*r*slant = π*r*sqrt(r²+h²)
        """
        h = self.stockpile_height_m
        V = self.stockpile_volume_m3
        r = math.sqrt(3.0 * V / (math.pi * h))
        slant = math.sqrt(r ** 2 + h ** 2)
        lateral = math.pi * r * slant
        base = math.pi * r ** 2
        return lateral + base  # total surface

    @staticmethod
    def _risk_flag(T_c: float) -> str:
        if T_c >= 150.0:
            return "CRITICAL"
        elif T_c >= 100.0:
            return "WARNING"
        elif T_c >= 70.0:
            return "WATCH"
        return "OK"
