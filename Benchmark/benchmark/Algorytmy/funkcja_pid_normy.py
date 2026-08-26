# Algorytmy/funkcja_pid_normy.py
#
# ALGORYTM: regulator PI(D) ciągły (0-100%) dążący do celu wyznaczonego przez
# PROGI NORMY LET-1 (nie funkcji ryzyka) - patrz funkcja_normy_wspolne.py. Ten
# sam regulator PI co funkcja_ryzyka_pid.py (te same nastawy SIMC, bo to
# własność OBIEKTU/grzałki, nie strategii wyznaczania celu) - różni się
# WYŁĄCZNIE źródłem setpointu.

from funkcja_normy_wspolne import KontrolerNormyCiaglaBazowy

# Nastawy identyczne jak w funkcja_ryzyka_pid.py - patrz tam pełne uzasadnienie
# (SIMC z parametrów obiektu zidentyfikowanych przez autotest(): K=51.1163668,
# T1=1120.914508, T2=2450.968465, L=1194.184089).
PID_KC_PERCENT = 2.9262
PID_TI_S = 3571.88
PID_KD_PERCENT = 0.0


class KontrolerNormaPID(KontrolerNormyCiaglaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler - regulator ciągły nie ma
        # dyskretnych przełączeń do ograniczania.
        self.max_switches_per_day = max_switches_per_day

        self._pid_integral = 0.0
        self._pid_prev_error = 0.0
        self._pid_prev_time = None

    def norma_pid(self, row_data):
        """
        Zwraca (moc_procent, diagnostyka) - moc_procent w [0,100], diagnostyka
        {'target_temperature', 'need_heat', 'reason', 'pid_error', 'pid_integral'}.
        Logika regulatora identyczna jak w funkcja_ryzyka_pid.risk_function_pid -
        patrz tam pełny opis anti-windup.
        """
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason = self._evaluate_norm_setpoint(row_data)

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

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'pid_error': target_temperature - hrt_temp,
            'pid_integral': self._pid_integral,
        }
        return power_percent, diagnostics
