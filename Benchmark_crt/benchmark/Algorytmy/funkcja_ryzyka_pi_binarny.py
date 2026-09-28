# Algorytmy/funkcja_ryzyka_pi_binarny.py
#
# ALGORYTM: regulator PI z WYJŚCIEM BINARNYM (0% / 100%) i pętlą histerezy 2°C -
# risk_function_pi_binarny w rejestr_algorytmow.py. Dodany 2026-09-28 na życzenie
# użytkownika: "wersja algorytmu PI, który będzie trzymał temperaturę, ale PI
# binarny z pętlą histerezy np. 2 stopnie".
#
# Temperaturę zadaną wyznacza ta sama funkcja ryzyka co w risk_function_pid /
# risk_function (KontrolerRyzykaBazowy._evaluate_risk_setpoint: Kalman, cyfrowy
# bliźniak, prognoza opadu). Zmienna regulowana to CRT (szyna zimna, główny
# wyznacznik w tym folderze), tak jak w risk_function_pid.
#
# JAK PI JEST ZAMIENIONY NA WYJŚCIE BINARNE:
#   e      = target - CRT                              [°C]
#   e_eff  = e + clamp( (1/Ti) * ∫e dt , ±PI_CALKA_MAX_C )   [°C] - błąd "z całką"
#            (Kc się skraca: hysterezę wyrażamy w °C, więc cały PI jest w °C)
#   Przekaźnik Schmitta na e_eff:
#       załącz  gdy e_eff >= +H/2   (CRT poniżej celu o >= 1°C, licząc z całką)
#       wyłącz  gdy e_eff <= -H/2   (CRT powyżej celu o >= 1°C, licząc z całką)
#   H = PI_HISTEREZA_C = 2.0°C (pełna szerokość pętli; między progami stan trzymany).
#   Całka robi to, czego sama histereza nie umie: gdy średnia temperatura
#   systematycznie leży pod celem, całka narasta i "dociąga" e_eff do progu
#   załączenia (albo przytrzymuje grzanie dłużej) - usuwa stały uchyb średniej
#   temperatury, zamiast pozwolić, by cykl graniczny siedział stale po jednej
#   stronie celu. Ti z SIMC (autotest na żywo, jak w risk_function_pid),
#   całka ograniczona do ±PI_CALKA_MAX_C (anty-windup: bez tego przy długim
#   dużym uchybie CRT całka rosłaby bez końca, a słaby/wolny kanał moc->CRT nie
#   pozwala jej się szybko rozładować).
#
# OCHRONA PRZEKAŹNIKA (jak w risk_function binarnej): min. odstęp między
# przełączeniami RISK_MIN_SWITCH_INTERVAL_S i dobowy limit max_switches_per_day.
#
# UWAGA - interpretacja: "PI binarny z histerezą" można rozumieć też jako PI
# liczące wypełnienie PWM. Tu zrealizowana jest wersja z przekaźnikiem Schmitta
# na błędzie z całką - dokładnie 2°C pętli, bez PWM. Jeśli chodziło o PWM,
# zmiana dotyczy tylko bloku "DECYZJA BINARNA" niżej.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy

RISK_MIN_SWITCH_INTERVAL_S = 60.0   # Minimalny odstęp między przełączeniami grzania (jak w funkcja_ryzyka_binarna.py).
PI_HISTEREZA_C = 2.0                # Pełna szerokość pętli histerezy [°C]: załącz przy +H/2, wyłącz przy -H/2.
PI_CALKA_MAX_C = 2.0                # Limit członu całkującego (1/Ti)*∫e dt [°C] - anty-windup.
PI_TI_S_DOMYSLNE = 3571.88          # Ti fabryczne (SIMC z K=51.1, T1=1121, T2=2451, L=1194), do czasu autotestu.


class KontrolerRyzykaPIBinarny(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()

        self.max_switches_per_day = max_switches_per_day
        self.pi_heating_on = False
        self.pi_current_date = None
        self.pi_switch_count_today = 0
        self._pi_last_switch_time = None

        self._pi_ti = PI_TI_S_DOMYSLNE
        self._pi_integral = 0.0          # ∫e dt [°C*s]
        self._pi_prev_time = None
        self._nastawy_simc_przeliczone = False

    def _przelicz_ti_simc(self, K, T1, T2, L):
        """SIMC (Skogestad), lambda=theta - tylko Ti (Kc skraca się w błędzie efektywnym w °C)."""
        tau = T1 + T2
        theta = L
        lam = theta
        self._pi_ti = max(min(tau, 4.0 * (theta + lam)), 1.0)

    def risk_function_pi_binarny(self, row_data):
        """
        Zwraca: (moc_procent, diagnostyka) - moc_procent to 0.0 albo 100.0;
        diagnostyka jak w risk_function_pid plus 'pi_e_eff' (błąd z całką) i
        'pi_histereza_c'.
        """
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        if not self._nastawy_simc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._przelicz_ti_simc(wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
            self._nastawy_simc_przeliczone = True

        timestamp = row_data['Timestamp']
        crt_temp = float(row_data['CRT_temp_niegrzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        # --- RESET LICZNIKA PRZEŁĄCZEŃ Z NASTANIEM NOWEGO DNIA. ---
        active_date = timestamp.date()
        if self.pi_current_date != active_date:
            self.pi_current_date = active_date
            self.pi_switch_count_today = 0

        error = target_temperature - crt_temp
        dt = (timestamp - self._pi_prev_time).total_seconds() if self._pi_prev_time else 1.0
        dt = max(dt, 1e-6)
        self._pi_prev_time = timestamp

        if not need_heat:
            # Brak zagrożenia - całka czyszczona (jak w risk_function_pid), grzanie wyłączone.
            self._pi_integral = 0.0
            e_eff = error
            desired_state = False
        else:
            # Anty-windup: całkujemy dalej tylko, dopóki człon całkujący nie jest w limicie
            # (albo błąd ciągnie go z powrotem do środka zakresu).
            calka_c = self._pi_integral / self._pi_ti
            if (abs(calka_c) < PI_CALKA_MAX_C
                    or (calka_c >= PI_CALKA_MAX_C and error < 0)
                    or (calka_c <= -PI_CALKA_MAX_C and error > 0)):
                self._pi_integral += error * dt
            calka_c = min(max(self._pi_integral / self._pi_ti, -PI_CALKA_MAX_C), PI_CALKA_MAX_C)
            e_eff = error + calka_c

            # --- DECYZJA BINARNA: przekaźnik Schmitta na błędzie z całką (pętla PI_HISTEREZA_C). ---
            polowa = PI_HISTEREZA_C / 2.0
            if self.pi_heating_on:
                desired_state = e_eff > -polowa   # trzymamy grzanie, aż e_eff spadnie do -H/2
            else:
                desired_state = e_eff >= polowa   # załączamy dopiero od +H/2

        # --- MINIMALNY ODSTĘP MIĘDZY PRZEŁĄCZENIAMI + LIMIT DOBOWY. ---
        previous_state = self.pi_heating_on
        can_switch = (self._pi_last_switch_time is None
                      or (timestamp - self._pi_last_switch_time).total_seconds() >= RISK_MIN_SWITCH_INTERVAL_S)
        if desired_state != previous_state and can_switch:
            # Jak w risk_function binarnej: po wyczerpaniu limitu dobowego zostajemy przy poprzednim stanie.
            if self.pi_switch_count_today < self.max_switches_per_day:
                self.pi_heating_on = desired_state
                self.pi_switch_count_today += 1
                self._pi_last_switch_time = timestamp

        power_percent = 100.0 if self.pi_heating_on else 0.0
        self._krok_modelu(power_percent)
        self._dodaj_flopy(20)  # PI (całka + anty-windup) + przekaźnik Schmitta + limity przełączeń.

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'pid_error': error,
            'pid_integral': self._pi_integral,
            'pi_e_eff': e_eff,
            'pi_histereza_c': PI_HISTEREZA_C,
        }
        return power_percent, diagnostics
