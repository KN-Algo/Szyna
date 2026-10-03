# Algorytmy/funkcja_ryzyka_adrc_model_adaptacyjny.py
#
# ALGORYTM: jak risk_function_ladrc (ESO - Extended State Observer, 2-stanowy, + liniowe
# prawo sterowania - Gao 2003), ale BEZ jednorazowego autotestu - wzmocnienie wejścia ESO
# (b0) jest braną NA ŻYWO wartością `a` (wzmocnienie grzałki) ze WSPÓLNEGO modelu RLS
# (model_obiektu_rls.py - ten sam co funkcja_ryzyka_model_adaptacyjny.py i
# funkcja_mpc_model_adaptacyjny.py, 2026-10-02), aktualizowaną co krok z PRAWDZIWEJ
# obserwacji (moc, AT, HRT). Klasyczna zaleta ADRC: ESO (z2) i tak pochłania WSZYSTKO, co
# model nie wyjaśnia (pogodę, słońce, błąd modelu) jako "całkowite zakłócenie" - więc w
# odróżnieniu od funkcja_ryzyka_model_adaptacyjny.py, tu z modelu RLS używane jest
# WYŁĄCZNIE b0=a (b/c z tego samego modelu liczone i udostępnione w diagnostyce, ale NIE
# wchodzą do prawa sterowania - ESO i tak je "zobaczy" przez z2).
#
# Cel pętli wykonawczej (jak w funkcja_ryzyka_model_adaptacyjny.py) jest w skali HRT
# (hrt_target_c), NIE w skali CRT z _evaluate_risk_setpoint - użycie target_temperature
# (kalibrowanego do progów CRT) bezpośrednio jako celu HRT powtórzyłoby błąd skali
# znaleziony wcześniej w risk_function_ladrc/nadrc (patrz funkcja_ryzyka_adrc_wspolne.py).
#
# omega_c/omega_o (pasma regulatora/obserwatora) - BEZ żywej identyfikacji drugiego bieguna
# T2/opóźnienia L (model RLS ma tylko jeden biegun) - zostają STAŁYMI hiperparametrami
# konstruktora, przeszukiwanymi przez testy/strojenie_modele_adaptacyjne.py.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from model_obiektu_rls import ModelObiektuRLS, A_MIN, LAMBDA_ZAPOMINANIA_DOMYSLNA

HRT_TARGET_C_DOMYSLNE = 5.0       # Patrz uzasadnienie w funkcja_ryzyka_model_adaptacyjny.py.
OMEGA_C_DOMYSLNE = 0.01           # Pasmo regulatora [rad/s] - ~100s stała czasowa zamknięta pętla.
OMEGA_O_DOMYSLNE = 0.05           # Pasmo obserwatora [rad/s] - typowo 3-5x szybsze niż omega_c (Gao 2003).


class KontrolerRyzykaADRCModelAdaptacyjny(KontrolerRyzykaBazowy):

    def _autotest_startowy(self, row_data):
        return False  # Brak jednorazowego autotestu - b0 (=a) płynie z modelu RLS od pierwszego kroku.

    def __init__(self, max_switches_per_day=12, hrt_target_c=HRT_TARGET_C_DOMYSLNE,
                 omega_c=OMEGA_C_DOMYSLNE, omega_o=OMEGA_O_DOMYSLNE,
                 lam_zapominania=LAMBDA_ZAPOMINANIA_DOMYSLNA):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day
        self.hrt_target_c = hrt_target_c
        self.omega_c = omega_c
        self.omega_o = omega_o

        self._model = ModelObiektuRLS(lam=lam_zapominania)

        # --- STAN ESO (Extended State Observer) ---
        self._z1 = None      # estymata HRT [°C] - None dopóki pierwszy pomiar nie zainicjalizuje
        self._z2 = 0.0        # estymata "całkowitego zakłócenia" [°C/s]
        self._poprzednia_moc_procent = 0.0
        self._adrc_prev_time = None

    def risk_function_adrc_model_adaptacyjny(self, row_data):
        czas_teraz = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        at_temp = float(row_data['AT_temp_powietrza'])

        a, b, c, proxy = self._model.aktualizuj_i_pobierz(czas_teraz, hrt_temp, at_temp)
        b0 = max(a, A_MIN)

        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if self._z1 is None:
            self._z1 = hrt_temp  # inicjalizacja ESO pierwszym prawdziwym pomiarem, nie zerem

        dt = (czas_teraz - self._adrc_prev_time).total_seconds() if self._adrc_prev_time else 1.0
        dt = max(dt, 1e-6)
        beta01 = 2.0 * self.omega_o          # wzmocnienia ESO z rozmieszczenia biegunów w -omega_o (podwójny biegun)
        beta02 = self.omega_o ** 2

        # --- ESO - liczony ZAWSZE, niezależnie od need_heat, żeby estymata zakłócenia
        # była aktualna, gdy grzanie znów będzie potrzebne. b0 TERAZ płynie z modelu RLS
        # (a), nie z jednorazowego autotestu. ---
        e_obserwatora = self._z1 - hrt_temp
        z1_nowe = self._z1 + dt * (self._z2 - beta01 * e_obserwatora + b0 * self._poprzednia_moc_procent)
        z2_nowe = self._z2 + dt * (-beta02 * e_obserwatora)
        self._z1, self._z2 = z1_nowe, z2_nowe

        if not need_heat:
            power_percent = 0.0
        else:
            error = self.hrt_target_c - self._z1   # cel w skali HRT, zgodnie z z1 (estymata HRT) - patrz nagłówek
            u0 = self.omega_c * error
            power_percent = (u0 - self._z2) / b0
            power_percent = min(max(power_percent, 0.0), 100.0)

        self._poprzednia_moc_procent = power_percent
        self._adrc_prev_time = czas_teraz

        self._model.zapamietaj_regresor(czas_teraz, hrt_temp, at_temp, power_percent / 100.0, proxy)

        self._krok_modelu(power_percent)
        self._dodaj_flopy(40)  # RLS (3x3) + ESO (2 stany liniowe) + prawo sterowania.

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'adrc_z1_est_hrt': self._z1,
            'adrc_z2_est_zaklocenie': self._z2,
            'model_a_grzalka': float(a),
            'model_b_pogoda': float(b),
            'model_c_slonce': float(c),
        }
        return power_percent, diagnostics
