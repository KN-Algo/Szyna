# Algorytmy/funkcja_ryzyka_pid.py
#
# ALGORYTM: funkcja ryzyka z pamięcią i prognozą Kalmana - WYJŚCIE CIĄGŁE
# (0-100%, risk_function_pid w rejestr_algorytmow.py), regulator PI(D) wokół
# temperatury zadanej. Wyznaczanie temperatury zadanej jest wspólne z wersją
# binarną - patrz funkcja_ryzyka_wspolne.py
# (KontrolerRyzykaBazowy._evaluate_risk_setpoint).
#
# PRZY STARCIE wykonuje JEDNORAZOWY autotest (patrz
# KontrolerRyzykaBazowy._autotest_startowy) - dopóki trwa, grzeje pełną mocą
# i nie podejmuje normalnych decyzji. Po udanej identyfikacji PRZELICZA własne
# nastawy PI metodą SIMC z ŚWIEŻO zidentyfikowanych K/T1/T2/L (zamiast
# fabrycznych stałych poniżej) - dostraja się więc do REALNEGO obiektu, a nie
# do wartości poznanych wcześniej w innym teście. Jeśli identyfikacja się nie
# powiedzie, zostaje przy nastawach fabrycznych.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy

# ==========================================
# NASTAWY FABRYCZNE (używane, dopóki autotest się nie zakończy, i jako
# bezpieczna wartość zapasowa, gdyby identyfikacja się nie powiodła) -
# wyliczone metodą SIMC z parametrów obiektu zidentyfikowanych we wcześniejszym
# teście (K, T1, T2, L - patrz Identyfikacja_obiektu/autotest_identyfikacja_testing.py):
# K=51.1163668, T1=1120.914508, T2=2450.968465, L=1194.184089. Przybliżenie do
# I rzędu z opóźnieniem: tau=T1+T2, theta=L, lambda=theta ("średnio agresywna").
# ==========================================
PID_KC_PERCENT_DOMYSLNE = 2.9262    # %mocy na °C błędu: Kc = (1/K) * (tau/(theta+lambda)) * 100
PID_TI_S_DOMYSLNE = 3571.88         # Czas zdwojenia całki [s]: Ti = min(tau, 4*(theta+lambda)) = tau
PID_KD_PERCENT_DOMYSLNE = 0.0       # Człon różniczkujący domyślnie wyłączony (duże opóźnienie -> D wzmacnia szum).


class KontrolerRyzykaPID(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler (wywoływane jednolicie dla
        # wszystkich algorytmów) - regulator ciągły nie ma dyskretnych
        # przełączeń do ograniczania, więc parametr nie jest tu używany.
        self.max_switches_per_day = max_switches_per_day

        # --- STAN REGULATORA PI(D) - nastawy fabryczne, dopóki autotest nie
        # zidentyfikuje obiektu na żywo (patrz _przelicz_nastawy_simc). ---
        self._pid_kc = PID_KC_PERCENT_DOMYSLNE
        self._pid_ti = PID_TI_S_DOMYSLNE
        self._pid_kd = PID_KD_PERCENT_DOMYSLNE
        self._pid_integral = 0.0
        self._pid_prev_error = 0.0
        self._pid_prev_time = None
        self._nastawy_simc_przeliczone = False

    def _przelicz_nastawy_simc(self, K, T1, T2, L):
        """SIMC (Skogestad), lambda=theta - patrz uzasadnienie w nagłówku pliku."""
        tau = T1 + T2
        theta = L
        lam = theta
        self._pid_kc = (1.0 / K) * (tau / (theta + lam)) * 100.0
        self._pid_ti = min(tau, 4.0 * (theta + lam))
        self._pid_kd = 0.0

    def risk_function_pid(self, row_data):
        """
        Ta sama logika ryzyka co risk_function (patrz
        KontrolerRyzykaBazowy._evaluate_risk_setpoint), ale wyjście jest
        CIĄGŁE (0-100%) zamiast binarnego - regulator PI(D) dąży do
        temperatury zadanej, więc może "delikatnie" dogrzewać zamiast skakać
        między pełną mocą a zerem.

        Zwraca:
            (moc_procent, diagnostyka) - moc_procent w zakresie [0, 100] (float),
            diagnostyka jak w risk_function plus 'pid_error' i 'pid_integral'
            (albo tylko {'faza': 'autotest', ...} dopóki trwa autotest startowy).
        """
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        # Przeliczenie nastaw PI metodą SIMC z ŚWIEŻO zidentyfikowanych K/T1/T2/L -
        # dokładnie RAZ, tuż po zakończeniu autotestu (patrz nagłówek pliku). Jeśli
        # identyfikacja się nie powiodła (fit_ok=False), zostajemy przy nastawach
        # fabrycznych - _nastawy_simc_przeliczone i tak ustawiamy, żeby nie
        # sprawdzać tego przy każdym kolejnym kroku.
        if not self._nastawy_simc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._przelicz_nastawy_simc(wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
            self._nastawy_simc_przeliczone = True

        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if not need_heat:
            # Nie ma zagrożenia - nie grzejemy i czyścimy całkę, żeby nie było
            # "doładowanego" regulatora, który przestrzeliwuje przy następnym zagrożeniu.
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

            # Anti-windup: całkujemy błąd tylko, gdy wyjście nieograniczone nie jest
            # już w nasyceniu (0% lub 100%) - inaczej całka pęczniałaby bez sensu.
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
