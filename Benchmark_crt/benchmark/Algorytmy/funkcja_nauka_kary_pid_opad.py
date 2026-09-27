# Algorytmy/funkcja_nauka_kary_pid_opad.py
#
# Jak funkcja_nauka_kary_pid.py, ale DOKŁADA prognozę OPADU
# (przewidywanie_opadow.py, ten sam mechanizm co w funkcja_ryzyka_wspolne.
# KontrolerRyzykaOpadBazowy) jako DWIE dodatkowe rzeczy:
#   1) Wyprzedzający, PRZEJŚCIOWY bonus do celu, gdy prognoza pokazuje
#      INTENSYFIKACJĘ opadu w najbliższych ~30 min (front dopiero nadchodzi).
#   2) Dodatkową (UJEMNĄ) karę do mechanizmu uczenia, gdy front WŁAŚNIE
#      KOŃCZY SIĘ a pokrywa jest cienka - pozwala nauczonemu czynnikowi szybciej
#      OPAŚĆ w takich warunkach (nie ma sensu utrzymywać wysokiego czynnika,
#      skoro opad i tak ustaje).

import os
import sys

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from funkcja_nauka_kary_wspolna import KontrolerNaukaKaryBazowy
from przewidywanie_opadow import przewidywanie_opadow as PrzewidywanieOpadow

PID_KC_PERCENT = 2.9262
PID_TI_S = 3571.88
PID_KD_PERCENT = 0.0

PROGNOZA_BLISKI_TERMIN_KROKOW = 2
PROGNOZA_BONUS_WYPRZEDZAJACY_C = 1.0
PROGNOZA_CIENKA_POKRYWA_MM = 10.0   # Jak RISK_OPAD_PROGNOZA_CIENKA_MM w funkcja_ryzyka_wspolne.py.


class KontrolerNaukaKaryPIDOpad(KontrolerNaukaKaryBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day
        self._opad_forecaster = PrzewidywanieOpadow(persistence_steps=1)

        self._pid_integral = 0.0
        self._pid_prev_error = 0.0
        self._pid_prev_time = None

    def nauka_kary(self, row_data):
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        snow_depth_mm = float(row_data.get('SNIEG_GRUBOSC_MM', 0.0))
        precip_total_mm = float(row_data['PRECIP_opad']) + float(row_data['SNOW_snieg'])

        bonus_chwilowy = 0.0
        dodatkowa_kara = 0.0
        forecast_at = self.temperature_prediction()
        if forecast_at:
            current_dp = float(row_data.get('PUNKT_ROSY_C', row_data['AT_temp_powietrza']))
            current_wind = float(row_data.get('WIATR_M_S', 3.0))
            prognoza = self._opad_forecaster.predict_winter_precipitation(
                [precip_total_mm], forecast_at, current_dp, current_wind)
            self._dodaj_flopy(160)
            near_term = [int(v) for v in prognoza[:PROGNOZA_BLISKI_TERMIN_KROKOW]]
            front_nadchodzi = precip_total_mm <= 0.0001 and any(v > 0 for v in near_term)
            front_konczy_sie = precip_total_mm > 0.0001 and all(v == 0 for v in near_term)
            if front_nadchodzi:
                bonus_chwilowy = PROGNOZA_BONUS_WYPRZEDZAJACY_C
                dodatkowa_kara = 1.0
            elif front_konczy_sie and snow_depth_mm <= PROGNOZA_CIENKA_POKRYWA_MM:
                dodatkowa_kara = -1.0

        target_temperature, need_heat, reason = self._evaluate_nauczony_setpoint(
            row_data, dodatkowa_kara=dodatkowa_kara, dodatkowy_offset_chwilowy=bonus_chwilowy)

        if not need_heat:
            self._pid_integral = 0.0
            self._pid_prev_error = 0.0
            self._pid_prev_time = timestamp
            power_percent = 0.0
        else:
            error = target_temperature - hrt_temp
            dt = (timestamp - self._pid_prev_time).total_seconds() if self._pid_prev_time else 1.0
            dt = max(dt, 1e-6)

            proportional = PID_KC_PERCENT * error
            derivative = PID_KD_PERCENT * (error - self._pid_prev_error) / dt

            unclamped_estimate = proportional + PID_KC_PERCENT / PID_TI_S * self._pid_integral + derivative
            if 0.0 < unclamped_estimate < 100.0 or (unclamped_estimate <= 0.0 and error > 0) \
                    or (unclamped_estimate >= 100.0 and error < 0):
                self._pid_integral += error * dt

            integral_term = (PID_KC_PERCENT / PID_TI_S) * self._pid_integral
            power_percent = proportional + integral_term + derivative
            power_percent = min(max(power_percent, 0.0), 100.0)

            self._pid_prev_error = error
            self._pid_prev_time = timestamp

        self._dodaj_flopy(15)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'czynnik_nauczony': self._czynnik_nauczony,
            'pid_error': target_temperature - hrt_temp,
            'pid_integral': self._pid_integral,
        }
        return power_percent, diagnostics
