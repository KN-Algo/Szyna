# Algorytmy/funkcja_ryzyka_pid_kaskada_opad.py
#
# Jak funkcja_ryzyka_pid_kaskada.py (kaskada dwóch PI: zewnętrzna CRT ->
# hrt_setpoint, wewnętrzna HRT -> moc), ale setpoint liczony przez
# KontrolerRyzykaOpadBazowy._evaluate_risk_setpoint_z_opadem - dokłada
# prognozę OPADU (przewidywanie_opadow.py) jako dodatkowy warunek zwalniający
# z grzania przy cienkiej, zanikającej pokrywie śniegu (patrz
# funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy). Reszta (obie pętle PI,
# strojenie SIMC) identyczna jak w wariancie bez opadu - patrz tam pełne
# uzasadnienie.

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy, RISK_HRT_ABSOLUTE_FLOOR_C
from funkcja_ryzyka_pid_kaskada import (
    HRT_LIMIT_OSTRZEGAWCZY_C, FALLBACK_K, FALLBACK_T1, FALLBACK_T2, FALLBACK_L,
    _simc_inner_pi, _simc_outer_pi,
)


class KontrolerRyzykaPIDKaskadaOpad(KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

        self._pid_in_kc, self._pid_in_ti = _simc_inner_pi(FALLBACK_K, FALLBACK_T1, FALLBACK_T2, FALLBACK_L)
        self._pid_in_integral = 0.0
        self._pid_in_prev_error = 0.0
        self._pid_in_prev_time = None

        self._pid_out_kc, self._pid_out_ti = _simc_outer_pi(FALLBACK_K)
        self._pid_out_integral = 0.0
        self._pid_out_prev_error = 0.0
        self._pid_out_prev_time = None

        self._nastawy_simc_przeliczone = False

    def risk_function_cascade_pi_opad(self, row_data):
        """Jak risk_function_cascade_pi, ale setpoint z _evaluate_risk_setpoint_z_opadem."""
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        if not self._nastawy_simc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._pid_in_kc, self._pid_in_ti = _simc_inner_pi(wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
                self._pid_out_kc, self._pid_out_ti = _simc_outer_pi(wynik['K'])
            self._nastawy_simc_przeliczone = True

        timestamp = row_data['Timestamp']
        crt_temp = float(row_data['CRT_temp_niegrzana'])
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint_z_opadem(row_data)

        if not need_heat:
            self._pid_out_integral = 0.0
            self._pid_out_prev_error = 0.0
            self._pid_out_prev_time = timestamp
            self._pid_in_integral = 0.0
            self._pid_in_prev_error = 0.0
            self._pid_in_prev_time = timestamp
            power_percent = 0.0
            hrt_setpoint = hrt_temp
        else:
            error_out = target_temperature - crt_temp
            dt_out = (timestamp - self._pid_out_prev_time).total_seconds() if self._pid_out_prev_time else 1.0
            dt_out = max(dt_out, 1e-6)

            proportional_out = self._pid_out_kc * error_out
            unclamped_out = hrt_temp + proportional_out + (self._pid_out_kc / self._pid_out_ti) * self._pid_out_integral
            if (RISK_HRT_ABSOLUTE_FLOOR_C < unclamped_out < HRT_LIMIT_OSTRZEGAWCZY_C
                    or (unclamped_out <= RISK_HRT_ABSOLUTE_FLOOR_C and error_out > 0)
                    or (unclamped_out >= HRT_LIMIT_OSTRZEGAWCZY_C and error_out < 0)):
                self._pid_out_integral += error_out * dt_out

            integral_term_out = (self._pid_out_kc / self._pid_out_ti) * self._pid_out_integral
            hrt_setpoint = hrt_temp + proportional_out + integral_term_out
            hrt_setpoint = min(max(hrt_setpoint, RISK_HRT_ABSOLUTE_FLOOR_C), HRT_LIMIT_OSTRZEGAWCZY_C)

            self._pid_out_prev_error = error_out
            self._pid_out_prev_time = timestamp

            error_in = hrt_setpoint - hrt_temp
            dt_in = (timestamp - self._pid_in_prev_time).total_seconds() if self._pid_in_prev_time else 1.0
            dt_in = max(dt_in, 1e-6)

            proportional_in = self._pid_in_kc * error_in
            unclamped_in = proportional_in + (self._pid_in_kc / self._pid_in_ti) * self._pid_in_integral
            if (0.0 < unclamped_in < 100.0 or (unclamped_in <= 0.0 and error_in > 0)
                    or (unclamped_in >= 100.0 and error_in < 0)):
                self._pid_in_integral += error_in * dt_in

            integral_term_in = (self._pid_in_kc / self._pid_in_ti) * self._pid_in_integral
            power_percent = proportional_in + integral_term_in
            power_percent = min(max(power_percent, 0.0), 100.0)

            self._pid_in_prev_error = error_in
            self._pid_in_prev_time = timestamp

        self._krok_modelu(power_percent)
        self._dodaj_flopy(25)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'hrt_setpoint': hrt_setpoint,
            'pid_error': target_temperature - crt_temp,
            'pid_error_outer': target_temperature - crt_temp,
            'pid_error_inner': hrt_setpoint - hrt_temp,
            'pid_integral_outer': self._pid_out_integral,
            'pid_integral_inner': self._pid_in_integral,
        }
        return power_percent, diagnostics
