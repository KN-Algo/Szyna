# Algorytmy/funkcja_nauka_kary_pid.py
#
# ALGORYTM: regulator PI(D) ciągły (0-100%) dążący do celu z progów normy
# LET-1 SKORYGOWANEGO o "nauczony" czynnik adaptacyjny (patrz
# funkcja_nauka_kary_wspolna.py) - WARIANT BAZOWY (bez żadnej prognozy, czysto
# reaktywny: uczy się WYŁĄCZNIE z kar zaobserwowanych już PO fakcie w minionej
# doby). Nastawy PI identyczne jak w funkcja_pid_normy.py/funkcja_ryzyka_pid.py
# (własność OBIEKTU, nie strategii wyznaczania celu).

from funkcja_nauka_kary_wspolna import KontrolerNaukaKaryBazowy

PID_KC_PERCENT = 2.9262
PID_TI_S = 3571.88
PID_KD_PERCENT = 0.0


class KontrolerNaukaKaryPID(KontrolerNaukaKaryBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day  # spójność interfejsu (regulator ciągły, bez limitu przełączeń)

        self._pid_integral = 0.0
        self._pid_prev_error = 0.0
        self._pid_prev_time = None

    def nauka_kary(self, row_data):
        """
        Zwraca (moc_procent, diagnostyka) - moc_procent w [0,100], diagnostyka
        {'target_temperature', 'need_heat', 'reason', 'czynnik_nauczony',
        'pid_error', 'pid_integral'}.
        """
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason = self._evaluate_nauczony_setpoint(row_data)

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

        self._dodaj_flopy(15)  # Formuła PI(D) + anti-windup.

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'czynnik_nauczony': self._czynnik_nauczony,
            'pid_error': target_temperature - hrt_temp,
            'pid_integral': self._pid_integral,
        }
        return power_percent, diagnostics
