# Algorytmy/funkcja_ryzyka_binarna.py
#
# ALGORYTM: funkcja ryzyka z pamięcią i prognozą Kalmana - WYJŚCIE BINARNE
# (0% / 100%, risk_function w rejestr_algorytmow.py). Wyznaczanie temperatury
# zadanej jest wspólne z wersją PID - patrz funkcja_ryzyka_wspolne.py
# (KontrolerRyzykaBazowy._evaluate_risk_setpoint). Tu jest tylko decyzja
# binarna z histerezą wokół tego setpointu.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy

RISK_MIN_SWITCH_INTERVAL_S = 60.0        # Minimalny odstęp między przełączeniami grzania (1 minuta).
RISK_HYSTERESIS_C = 2.0                  # Zapas HRT ponad temperaturę zadaną, zanim wyłączymy grzanie.


class KontrolerRyzykaBinarny(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        # --- STAN FUNKCJI RYZYKA ---
        self.risk_heating_on = False
        self.risk_current_date = None
        self.risk_switch_count_today = 0
        self._risk_last_switch_time = None
        self.max_switches_per_day = max_switches_per_day

    def risk_function(self, row_data):
        """
        Funkcja ryzyka z pamięcią i prognozą - WERSJA BINARNA (0% / 100%).
        Logika wyznaczania temperatury zadanej opisana w
        KontrolerRyzykaBazowy._evaluate_risk_setpoint().

        Wyjście jest przełączane z histerezą (RISK_HYSTERESIS_C) i NIE CZĘŚCIEJ niż
        raz na RISK_MIN_SWITCH_INTERVAL_S (1 minuta), niezależnie od tego jak szybko
        zmieniają się warunki wejściowe.

        Zwraca:
            (moc_procent, diagnostyka) - moc_procent to 0.0 albo 100.0, a diagnostyka
            to słownik {'target_temperature', 'need_heat', 'reason', 'forecast_min_c',
            'warmup_soon'} przydatny do testowania/wykresów.
        """
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

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
            # Już grzejemy - zostajemy w tym stanie, dopóki HRT nie przekroczy
            # temperatury zadanej z zapasem (unikamy szybkiego pstrykania).
            desired_state = hrt_temp < (target_temperature + RISK_HYSTERESIS_C)
        else:
            # Nie grzejemy - załączamy dopiero, gdy HRT faktycznie spadnie poniżej celu.
            desired_state = hrt_temp < target_temperature

        # --- MINIMALNY ODSTĘP MIĘDZY PRZEŁĄCZENIAMI (1 minuta). ---
        can_switch = (self._risk_last_switch_time is None
                      or (timestamp - self._risk_last_switch_time).total_seconds() >= RISK_MIN_SWITCH_INTERVAL_S)

        if desired_state != previous_state and can_switch:
            if self.risk_switch_count_today < self.max_switches_per_day:
                self.risk_heating_on = desired_state
                self.risk_switch_count_today += 1
                self._risk_last_switch_time = timestamp
            # W przeciwnym razie limit dobowy wyczerpany - zostajemy przy poprzednim stanie.

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
        }
        return (100.0 if self.risk_heating_on else 0.0), diagnostics
