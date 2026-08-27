# Algorytmy/funkcja_ryzyka_pid_opad.py
#
# Jak funkcja_ryzyka_pid.py (autotest startowy + PI(D) przestrajany metodą
# SIMC), ale setpoint liczony przez
# KontrolerRyzykaOpadBazowy._evaluate_risk_setpoint_z_opadem - dokłada
# prognozę OPADU (przewidywanie_opadow.py) jako dodatkowy warunek zwalniający
# z grzania przy cienkiej, zanikającej pokrywie śniegu (patrz
# funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy).

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy

# Nastawy fabryczne - identyczne jak w funkcja_ryzyka_pid.py (patrz uzasadnienie tam).
PID_KC_PERCENT_DOMYSLNE = 2.9262
PID_TI_S_DOMYSLNE = 3571.88
PID_KD_PERCENT_DOMYSLNE = 0.0


class KontrolerRyzykaPIDOpad(KontrolerRyzykaOpadBazowy):

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
        """SIMC (Skogestad), lambda=theta - patrz uzasadnienie w funkcja_ryzyka_pid.py."""
        tau = T1 + T2
        theta = L
        lam = theta
        self._pid_kc = (1.0 / K) * (tau / (theta + lam)) * 100.0
        self._pid_ti = min(tau, 4.0 * (theta + lam))
        self._pid_kd = 0.0

    def risk_function_pid_opad(self, row_data):
        """
        Jak risk_function_pid (funkcja_ryzyka_pid.py), ale setpoint z
        _evaluate_risk_setpoint_z_opadem (uwzględnia prognozę opadu).

        Zwraca:
            (moc_procent, diagnostyka) - moc_procent w zakresie [0, 100] (float),
            diagnostyka jak w risk_function_opad plus 'pid_error' i 'pid_integral'
            (albo tylko {'faza': 'autotest', ...} dopóki trwa autotest startowy).
        """
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        if not self._nastawy_simc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._przelicz_nastawy_simc(wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
            self._nastawy_simc_przeliczone = True

        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint_z_opadem(row_data)

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
        self._dodaj_flopy(15)  # Formuła PI(D) + anti-windup (na wierzchu setpointu/cyfrowego bliźniaka).

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'pid_error': target_temperature - hrt_temp,
            'pid_integral': self._pid_integral,
        }
        return power_percent, diagnostics
