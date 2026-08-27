# Algorytmy/funkcja_nauka_kary_pid_ryzyko.py
#
# Najbardziej zaawansowany wariant rodziny "uczenia z kar" - ŁĄCZY WSZYSTKIE
# TRZY źródła prognozy z pozostałych wariantów (temperatura z Kalmana, opad z
# przewidywanie_opadow.py, cyfrowy bliźniak grzałki z autotestu) w JEDNĄ
# złożoną ocenę ryzyka, i UCZY SIĘ na jej podstawie (zamiast na trzech
# osobnych, niezależnych karach jak w wariantach _temp/_opad/_blizniak).
# Adaptacyjny (autotest startowy, jak _blizniak.py).

from rdzen_kontrolera import HORIZON_STEPS, STEP_SECONDS, TEMP_FORECAST_REFRESH_S
from funkcja_nauka_kary_wspolna import KontrolerNaukaKaryBazowy, KARA_PRZEGRZANIE_HRT_C

import os
import sys

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from przewidywanie_opadow import przewidywanie_opadow as PrzewidywanieOpadow

PID_KC_PERCENT_DOMYSLNE = 2.9262
PID_TI_S_DOMYSLNE = 3571.88
PID_KD_PERCENT_DOMYSLNE = 0.0

PROGNOZA_BLISKI_TERMIN_KROKOW = 2
PROGNOZA_GLEBOKI_MROZ_C = -12.0
PROGNOZA_CIENKA_POKRYWA_MM = 10.0


class KontrolerNaukaKaryPIDRyzyko(KontrolerNaukaKaryBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day
        self._opad_forecaster = PrzewidywanieOpadow(persistence_steps=1)

        self._pid_kc = PID_KC_PERCENT_DOMYSLNE
        self._pid_ti = PID_TI_S_DOMYSLNE
        self._pid_kd = PID_KD_PERCENT_DOMYSLNE
        self._pid_integral = 0.0
        self._pid_prev_error = 0.0
        self._pid_prev_time = None
        self._nastawy_simc_przeliczone = False

    def _przelicz_nastawy_simc(self, K, T1, T2, L):
        tau = T1 + T2
        theta = L
        lam = theta
        self._pid_kc = (1.0 / K) * (tau / (theta + lam)) * 100.0
        self._pid_ti = min(tau, 4.0 * (theta + lam))
        self._pid_kd = 0.0

    def _prognoza_hrt_z_blizniaka(self, timestamp):
        forecast_crt = self.rail_temperature_prediction()
        if not (self._model_zidentyfikowany and forecast_crt):
            return []

        cached = self._model_forecast_cache
        cached_time = self._model_forecast_cache_time
        if (cached is not None and cached_time is not None
                and (timestamp - cached_time).total_seconds() < TEMP_FORECAST_REFRESH_S):
            zanikanie_na_siatce = cached
        else:
            krok_siatki_w_probkach = max(int(round(STEP_SECONDS / self._dt_sterowania)), 1)
            liczba_krokow_prognozy = int(round(HORIZON_STEPS * STEP_SECONDS / self._dt_sterowania))
            zanikanie = self._prognoza_zanikania_ciepla(liczba_krokow_prognozy)
            zanikanie_na_siatce = zanikanie[krok_siatki_w_probkach - 1::krok_siatki_w_probkach][:len(forecast_crt)]
            self._model_forecast_cache = zanikanie_na_siatce
            self._model_forecast_cache_time = timestamp

        return [c + h for c, h in zip(forecast_crt, zanikanie_na_siatce)]

    def _wylicz_ryzyko(self, row_data, timestamp, forecast_at, forecast_hrt):
        """
        Łączy 3 źródła w JEDEN wynik ryzyka (dodatni = trzeba grzać mocniej w
        przyszłości, ujemny = trzeba grzać słabiej/można poluzować):
          - prognoza temperatury powietrza (głęboki mróz nadchodzi),
          - prognoza opadu (front nadchodzi/kończy się),
          - prognoza HRT z cyfrowego bliźniaka (przewidywane przegrzanie/floor).
        Zwraca (ryzyko: float, bonus_chwilowy: float).
        """
        ryzyko = 0.0
        bonus_chwilowy = 0.0

        if forecast_at:
            if min(forecast_at) <= PROGNOZA_GLEBOKI_MROZ_C:
                ryzyko += 1.0
            if any(v <= self.at_low_freeze for v in forecast_at[:PROGNOZA_BLISKI_TERMIN_KROKOW]):
                bonus_chwilowy += 0.5
            self._dodaj_flopy(2 * len(forecast_at))

        snow_depth_mm = float(row_data.get('SNIEG_GRUBOSC_MM', 0.0))
        precip_total_mm = float(row_data['PRECIP_opad']) + float(row_data['SNOW_snieg'])
        if forecast_at:
            current_dp = float(row_data.get('PUNKT_ROSY_C', row_data['AT_temp_powietrza']))
            current_wind = float(row_data.get('WIATR_M_S', 3.0))
            prognoza_opad = self._opad_forecaster.predict_winter_precipitation(
                [precip_total_mm], forecast_at, current_dp, current_wind)
            self._dodaj_flopy(160)
            near_term = [int(v) for v in prognoza_opad[:PROGNOZA_BLISKI_TERMIN_KROKOW]]
            if precip_total_mm <= 0.0001 and any(v > 0 for v in near_term):
                ryzyko += 1.0
                bonus_chwilowy += 0.5
            elif precip_total_mm > 0.0001 and all(v == 0 for v in near_term) and snow_depth_mm <= PROGNOZA_CIENKA_POKRYWA_MM:
                ryzyko -= 1.0

        if forecast_hrt:
            if max(forecast_hrt) > KARA_PRZEGRZANIE_HRT_C:
                ryzyko -= 1.0
            elif min(forecast_hrt) < -8.0:
                ryzyko += 1.0
            self._dodaj_flopy(2 * len(forecast_hrt))

        return ryzyko, bonus_chwilowy

    def nauka_kary(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        if not self._nastawy_simc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._przelicz_nastawy_simc(wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
            self._nastawy_simc_przeliczone = True

        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])

        forecast_at = self.temperature_prediction()
        forecast_hrt = self._prognoza_hrt_z_blizniaka(timestamp)
        ryzyko, bonus_chwilowy = self._wylicz_ryzyko(row_data, timestamp, forecast_at, forecast_hrt)

        target_temperature, need_heat, reason = self._evaluate_nauczony_setpoint(
            row_data, dodatkowa_kara=ryzyko, dodatkowy_offset_chwilowy=bonus_chwilowy)

        if not need_heat:
            self._pid_integral = 0.0
            self._pid_prev_error = 0.0
            self._pid_prev_time = timestamp
            power_percent = 0.0
        else:
            error = target_temperature - hrt_temp
            dt = (timestamp - self._pid_prev_time).total_seconds() if self._pid_prev_time else 1.0
            dt = max(dt, 1e-6)

            proportional = self._pid_kc * error
            derivative = self._pid_kd * (error - self._pid_prev_error) / dt

            unclamped_estimate = proportional + self._pid_kc / self._pid_ti * self._pid_integral + derivative
            if 0.0 < unclamped_estimate < 100.0 or (unclamped_estimate <= 0.0 and error > 0) \
                    or (unclamped_estimate >= 100.0 and error < 0):
                self._pid_integral += error * dt

            integral_term = (self._pid_kc / self._pid_ti) * self._pid_integral
            power_percent = proportional + integral_term + derivative
            power_percent = min(max(power_percent, 0.0), 100.0)

            self._pid_prev_error = error
            self._pid_prev_time = timestamp

        self._krok_modelu(power_percent)
        self._dodaj_flopy(15)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'czynnik_nauczony': self._czynnik_nauczony,
            'ryzyko': ryzyko,
            'pid_error': target_temperature - hrt_temp,
            'pid_integral': self._pid_integral,
        }
        return power_percent, diagnostics
