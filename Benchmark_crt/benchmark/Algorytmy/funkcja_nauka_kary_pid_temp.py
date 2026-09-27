# Algorytmy/funkcja_nauka_kary_pid_temp.py
#
# Jak funkcja_nauka_kary_pid.py, ale DOKŁADA prognozę temperatury POWIETRZA
# (Kalman, rdzen_kontrolera.KontrolerBazowy.temperature_prediction - 8 kroków
# x 15 min) jako DWIE dodatkowe rzeczy:
#   1) Wyprzedzający, PRZEJŚCIOWY (nie akumulowany na stałe) bonus do celu,
#      gdy prognoza pokazuje rychłe wejście w suchy mróz - grzejemy z lekkim
#      wyprzedzeniem, zanim faktycznie zrobi się zimno (obiekt ma bezwładność).
#   2) Dodatkową, WYPRZEDZAJĄCĄ karę do mechanizmu uczenia, gdy prognoza
#      pokazuje bardzo głęboki mróz - "uczymy się" trochę szybciej w takich
#      warunkach, zamiast czekać, aż realnie dojdzie do przegrzania/niedogrzania.

from funkcja_nauka_kary_wspolna import KontrolerNaukaKaryBazowy

PID_KC_PERCENT = 2.9262
PID_TI_S = 3571.88
PID_KD_PERCENT = 0.0

PROGNOZA_BLISKI_TERMIN_KROKOW = 2       # 2 x 15 min = 30 min - jak RISK_NEAR_TERM_STEPS w funkcja_ryzyka_wspolne.py.
PROGNOZA_BONUS_WYPRZEDZAJACY_C = 1.0    # Przejściowy bonus do celu, gdy prognoza pokazuje rychły suchy mróz.
PROGNOZA_GLEBOKI_MROZ_C = -12.0         # Jak RISK_FORECAST_COLD_TRIGGER_C - poniżej tego w prognozie: dodatkowa kara.


class KontrolerNaukaKaryPIDTemp(KontrolerNaukaKaryBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

        self._pid_integral = 0.0
        self._pid_prev_error = 0.0
        self._pid_prev_time = None

    def nauka_kary(self, row_data):
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])

        forecast_at = self.temperature_prediction()
        bonus_chwilowy = 0.0
        dodatkowa_kara = 0.0
        if forecast_at:
            near_term = forecast_at[:PROGNOZA_BLISKI_TERMIN_KROKOW]
            if any(v <= self.at_low_freeze for v in near_term):
                bonus_chwilowy = PROGNOZA_BONUS_WYPRZEDZAJACY_C
            if min(forecast_at) <= PROGNOZA_GLEBOKI_MROZ_C:
                dodatkowa_kara = 1.0
            self._dodaj_flopy(2 * len(forecast_at))  # Przejrzenie prognozy (min/any na 8 elementach).

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
