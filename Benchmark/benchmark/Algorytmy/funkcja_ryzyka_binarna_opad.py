# Algorytmy/funkcja_ryzyka_binarna_opad.py
#
# Jak funkcja_ryzyka_binarna.py, ale setpoint liczony przez
# KontrolerRyzykaOpadBazowy._evaluate_risk_setpoint_z_opadem - dokłada
# prognozę OPADU (przewidywanie_opadow.py) jako dodatkowy warunek zwalniający
# z grzania przy cienkiej, zanikającej pokrywie śniegu (patrz
# funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy). Reszta logiki (histereza
# 0%/100% wokół setpointu, limit przełączeń/dobę) identyczna jak w wersji bez
# opadu.

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy

RISK_MIN_SWITCH_INTERVAL_S = 60.0        # Minimalny odstęp między przełączeniami grzania (1 minuta).
RISK_HYSTERESIS_C = 2.0                  # Zapas HRT ponad temperaturę zadaną, zanim wyłączymy grzanie.


class KontrolerRyzykaBinarnyOpad(KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        # --- STAN FUNKCJI RYZYKA ---
        self.risk_heating_on = False
        self.risk_current_date = None
        self.risk_switch_count_today = 0
        self._risk_last_switch_time = None
        self.max_switches_per_day = max_switches_per_day

    def risk_function_opad(self, row_data):
        """
        Jak risk_function (funkcja_ryzyka_binarna.py), ale setpoint z
        _evaluate_risk_setpoint_z_opadem (uwzględnia prognozę opadu).

        Zwraca:
            (moc_procent, diagnostyka) - moc_procent to 0.0 albo 100.0, a diagnostyka
            to słownik {'target_temperature', 'need_heat', 'reason', 'forecast_min_c',
            'warmup_soon'} przydatny do testowania/wykresów.
        """
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint_z_opadem(row_data)

        # --- RESET LICZNIKA PRZEŁĄCZEŃ Z NASTANIEM NOWEGO DNIA. ---
        active_date = timestamp.date()
        if self.risk_current_date != active_date:
            self.risk_current_date = active_date
            self.risk_switch_count_today = 0

        # --- DECYZJA BINARNA: histereza wokół temperatury zadanej. ---
        previous_state = self.risk_heating_on
        if not need_heat:
            desired_state = False
        elif previous_state:
            desired_state = hrt_temp < (target_temperature + RISK_HYSTERESIS_C)
        else:
            desired_state = hrt_temp < target_temperature

        # --- MINIMALNY ODSTĘP MIĘDZY PRZEŁĄCZENIAMI (1 minuta). ---
        can_switch = (self._risk_last_switch_time is None
                      or (timestamp - self._risk_last_switch_time).total_seconds() >= RISK_MIN_SWITCH_INTERVAL_S)

        if desired_state != previous_state and can_switch:
            if self.risk_switch_count_today < self.max_switches_per_day:
                self.risk_heating_on = desired_state
                self.risk_switch_count_today += 1
                self._risk_last_switch_time = timestamp

        self._dodaj_flopy(15)  # Histereza + limit przełączeń (na wierzchu setpointu z _evaluate_risk_setpoint_z_opadem).

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
        }
        return (100.0 if self.risk_heating_on else 0.0), diagnostics
