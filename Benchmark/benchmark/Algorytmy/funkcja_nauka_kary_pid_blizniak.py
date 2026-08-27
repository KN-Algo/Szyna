# Algorytmy/funkcja_nauka_kary_pid_blizniak.py
#
# Jak funkcja_nauka_kary_pid.py, ale ADAPTACYJNY: wykonuje JEDNORAZOWY autotest
# startowy (patrz rdzen_kontrolera.KontrolerBazowy._autotest_startowy) i buduje
# "cyfrowy bliźniak" grzałki, którego używa do WYPRZEDZAJĄCEGO wykrywania kar -
# zamiast czekać, aż przegrzanie/niedogrzanie faktycznie się zdarzy (jak w
# wariancie bazowym), PRZEWIDUJE trajektorię HRT (prognoza CRT z Kalmana +
# zanikające ciepło z już wydanych komend mocy) i nalicza karę PRZEWIDYWANĄ,
# zanim jeszcze do niej dojdzie - to jest RÓŻNE źródło kary niż w wariancie
# _temp.py (tam tylko prognoza POGODY, tu fizyczny model REAKCJI OBIEKTU na
# już wydane komendy).

from rdzen_kontrolera import HORIZON_STEPS, STEP_SECONDS, TEMP_FORECAST_REFRESH_S
from funkcja_nauka_kary_wspolna import KontrolerNaukaKaryBazowy, KARA_PRZEGRZANIE_HRT_C

PID_KC_PERCENT_DOMYSLNE = 2.9262
PID_TI_S_DOMYSLNE = 3571.88
PID_KD_PERCENT_DOMYSLNE = 0.0


class KontrolerNaukaKaryPIDBlizniak(KontrolerNaukaKaryBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

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
        """
        Analogiczne do funkcja_ryzyka_wspolne._evaluate_risk_setpoint - prognoza
        CRT (Kalman) + zanikające ciepło z cyfrowego bliźniaka = prognoza HRT.
        Zwraca listę (może być pusta, jeśli model jeszcze nie zidentyfikowany)
        na siatce 15-minutowej (HORIZON_STEPS punktów).
        """
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

        forecast_hrt = self._prognoza_hrt_z_blizniaka(timestamp)
        dodatkowa_kara = 0.0
        if forecast_hrt:
            if max(forecast_hrt) > KARA_PRZEGRZANIE_HRT_C:
                dodatkowa_kara = -1.0  # przewidywane przegrzanie - ucz się grzać SŁABIEJ
            elif min(forecast_hrt) < -8.0:  # zapowiedź zbliżania się do floora - jak RISK_HRT_FLOOR_TRIGGER_C
                dodatkowa_kara = 1.0   # przewidywane niedogrzanie - ucz się grzać MOCNIEJ
            self._dodaj_flopy(2 * len(forecast_hrt))

        target_temperature, need_heat, reason = self._evaluate_nauczony_setpoint(
            row_data, dodatkowa_kara=dodatkowa_kara)

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
            'pid_error': target_temperature - hrt_temp,
            'pid_integral': self._pid_integral,
        }
        return power_percent, diagnostics
