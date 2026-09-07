# Algorytmy/funkcja_ryzyka_nadrc.py
#
# ALGORYTM: funkcja ryzyka + Nieliniowe ADRC (Active Disturbance Rejection
# Control, Han Jingqing 2009 - oryginalna wersja z funkcją fal()) zamiast PID
# wokół temperatury zadanej. Wyznaczanie temperatury zadanej jest WSPÓLNE z
# pozostałymi wariantami funkcji ryzyka - patrz funkcja_ryzyka_wspolne.py
# (KontrolerRyzykaBazowy._evaluate_risk_setpoint). Matematyka wspólna z
# wariantem liniowym (LADRC) - patrz funkcja_ryzyka_adrc_wspolne.py (fal(),
# wylicz_parametry_adrc) i funkcja_ryzyka_ladrc.py (ogólne wprowadzenie do idei
# ADRC - warto przeczytać najpierw, jeśli nieznane).
#
# RÓŻNICA względem LADRC: poprawki obserwatora (NLESO) i prawo sterowania
# (NLSEF) używają fal(e, alpha, delta) zamiast zwykłego wzmocnienia liniowego -
# dla alpha<1 daje to SILNIEJSZĄ korekcję blisko zera (szybsza zbieżność małych
# błędów) i SŁABSZĄ (wolniej rosnącą niż liniowo) korekcję przy dużych błędach
# - łagodniejszy, mniej "szarpiący" przyrost mocy przy nagłych skokach
# warunków niż czyste wzmocnienie liniowe. Wagi (beta01/beta02/kp) SKALIBROWANE
# tak, żeby w wąskiej strefie liniowej (|e|<=ADRC_NADRC_DELTA_C) zachowanie
# było IDENTYCZNE jak w LADRC - różnica ujawnia się WYŁĄCZNIE poza tą strefą,
# więc para LADRC/NADRC jest uczciwie porównywalna (ta sama "agresywność"
# bazowa, inny kształt reakcji na duże odchylenia).
#
# PRZY STARCIE wykonuje ten sam JEDNORAZOWY autotest co risk_function_pid/
# risk_function_ladrc - dopóki trwa, grzeje pełną mocą. Po udanej identyfikacji
# przelicza b0/omega_c/omega_o ze świeżo zidentyfikowanych K/T1/T2/L.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from funkcja_ryzyka_adrc_wspolne import (
    wylicz_parametry_adrc, fal,
    ADRC_FALLBACK_K, ADRC_FALLBACK_T1, ADRC_FALLBACK_T2, ADRC_FALLBACK_L,
    ADRC_NADRC_ALPHA1, ADRC_NADRC_ALPHA2, ADRC_NADRC_ALPHA_CTRL, ADRC_NADRC_DELTA_C,
)


class KontrolerRyzykaNADRC(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day  # spójność interfejsu - regulator ciągły, nieużywane

        self._b0, self._omega_c, self._omega_o = wylicz_parametry_adrc(
            ADRC_FALLBACK_K, ADRC_FALLBACK_T1, ADRC_FALLBACK_T2, ADRC_FALLBACK_L)
        self._nastawy_adrc_przeliczone = False

        self._z1 = None
        self._z2 = 0.0
        self._poprzednia_moc_procent = 0.0
        self._adrc_prev_time = None

    def risk_function_nadrc(self, row_data):
        """
        Jak risk_function_ladrc, ale ESO (NLESO) i prawo sterowania (NLSEF)
        używają fal() zamiast wzmocnienia liniowego - patrz różnica opisana w
        nagłówku pliku.

        Zwraca:
            (moc_procent, diagnostyka) - jak risk_function_ladrc.
        """
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        if not self._nastawy_adrc_przeliczone:
            wynik = self.autotest_result
            if wynik is not None and wynik['fit_ok']:
                self._b0, self._omega_c, self._omega_o = wylicz_parametry_adrc(
                    wynik['K'], wynik['T1'], wynik['T2'], wynik['L'])
            self._nastawy_adrc_przeliczone = True

        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if self._z1 is None:
            self._z1 = hrt_temp

        dt = (timestamp - self._adrc_prev_time).total_seconds() if self._adrc_prev_time else 1.0
        dt = max(dt, 1e-6)

        # --- Wagi NLESO/NLSEF skalibrowane tak, żeby wewnątrz strefy liniowej
        # (|e|<=ADRC_NADRC_DELTA_C) dawały DOKŁADNIE te same poprawki co
        # LADRC (beta01_liniowe*e, nie beta01_liniowe*fal(e,...)) - bo w tej
        # strefie fal(e,alpha,delta)=e/delta^(1-alpha), więc
        # beta*delta^(1-alpha) * (e/delta^(1-alpha)) = beta*e. Poza strefą
        # (gdzie fal() staje się |e|^alpha*sign(e)) zachowanie się rozjeżdża -
        # to jest właśnie różnica liniowy vs nieliniowy ADRC. ---
        beta01_liniowe = 2.0 * self._omega_o
        beta02_liniowe = self._omega_o ** 2
        beta01 = beta01_liniowe * (ADRC_NADRC_DELTA_C ** (1.0 - ADRC_NADRC_ALPHA1))
        beta02 = beta02_liniowe * (ADRC_NADRC_DELTA_C ** (1.0 - ADRC_NADRC_ALPHA2))
        kp = self._omega_c * (ADRC_NADRC_DELTA_C ** (1.0 - ADRC_NADRC_ALPHA_CTRL))

        e_obserwatora = self._z1 - hrt_temp
        z1_nowe = self._z1 + dt * (
            self._z2
            - beta01 * fal(e_obserwatora, ADRC_NADRC_ALPHA1, ADRC_NADRC_DELTA_C)
            + self._b0 * self._poprzednia_moc_procent
        )
        z2_nowe = self._z2 + dt * (-beta02 * fal(e_obserwatora, ADRC_NADRC_ALPHA2, ADRC_NADRC_DELTA_C))
        self._z1, self._z2 = z1_nowe, z2_nowe

        if not need_heat:
            power_percent = 0.0
        else:
            error = target_temperature - self._z1
            u0 = kp * fal(error, ADRC_NADRC_ALPHA_CTRL, ADRC_NADRC_DELTA_C)
            power_percent = (u0 - self._z2) / self._b0
            power_percent = min(max(power_percent, 0.0), 100.0)

        self._poprzednia_moc_procent = power_percent
        self._adrc_prev_time = timestamp

        self._krok_modelu(power_percent)
        self._dodaj_flopy(30)  # NLESO (2 stany, 2x fal()) + NLSEF (1x fal()) - drożej niż LADRC (bez fal()).

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'adrc_z1_est_hrt': self._z1,
            'adrc_z2_est_zaklocenie': self._z2,
        }
        return power_percent, diagnostics
