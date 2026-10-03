# Algorytmy/funkcja_mpc_model_adaptacyjny.py
#
# ALGORYTM: jak funkcja_mpc_liniowy.py (cała maszyneria MPC - _MPCMachineryMixin,
# model blokowy 15-minutowy, QP L-BFGS-B, move blocking - patrz mpc_wspolne.py), ale
# model blokowy NIE jest budowany RAZ z jednorazowego autotestu (K/T1/T2/L zamrożone) -
# jest ODŚWIEŻANY co krok z ŻYWEGO modelu RLS (model_obiektu_rls.py - WSPÓLNY z
# funkcja_ryzyka_model_adaptacyjny.py i funkcja_ryzyka_adrc_model_adaptacyjny.py,
# 2026-10-02), więc MPC planuje na podstawie najświeższej wiedzy o obiekcie, nie
# migawki sprzed całego przebiegu.
#
# UPROSZCZENIE: model RLS ma tylko JEDEN biegun (a,b - patrz model_obiektu_rls.py),
# więc blok budowany jest jako FOPDT pierwszego rzędu (K=a/b, T1=1/b, T2=0, L=0) -
# PROSTSZY niż 2-biegunowy model z autotestu SOPDT używany przez pozostałe warianty
# MPC. `c` (wzmocnienie słoneczne) z modelu RLS jest liczone i w diagnostyce, ale NIE
# wchodzi do modelu blokowego - blok modeluje WYŁĄCZNIE kanał moc->HRT (pogoda/słońce
# trafiają do MPC osobno, przez crt_forecast - TA SAMA architektura co reszta rodziny
# MPC, patrz mpc_wspolne.py nagłówek).
#
# Model blokowy jest ODŚWIEŻANY (nowe A/B/C/D z najnowszych a/b), ale stan (x,
# u_history) NIE jest resetowany przy odświeżeniu - standardowe uproszczenie
# gain-scheduled/adaptive MPC dla wolno zmieniających się parametrów (parametry RLS
# zmieniają się powoli dzięki LAMBDA_ZAPOMINANIA bliskiej 1 - patrz model_obiektu_rls.py).

import numpy as np
from scipy import signal

from rdzen_kontrolera import HORIZON_STEPS, STEP_SECONDS, NANOS_PER_BIN
from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from mpc_wspolne import _MPCMachineryMixin
from model_obiektu_rls import ModelObiektuRLS, A0_DOMYSLNE, B0_DOMYSLNE, LAMBDA_ZAPOMINANIA_DOMYSLNA


class KontrolerMPCModelAdaptacyjny(_MPCMachineryMixin, KontrolerRyzykaBazowy):

    def _autotest_startowy(self, row_data):
        return False  # Brak jednorazowego autotestu - model blokowy płynie z RLS od pierwszego kroku.

    def __init__(self, max_switches_per_day=12, lam_zapominania=LAMBDA_ZAPOMINANIA_DOMYSLNA):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

        self._model = ModelObiektuRLS(lam=lam_zapominania)
        self._mpc_model_zbudowany = True  # "żywy" model jest gotowy od pierwszego kroku (priory a0/b0)
        self._odswiez_model_blokowy(A0_DOMYSLNE, B0_DOMYSLNE)
        self._ostatni_bin_odswiezenia = None

    def _odswiez_model_blokowy(self, a, b):
        """Przebudowuje A/B/C/D w rozdzielczości bloku (STEP_SECONDS) z najnowszych
        (a,b) z RLS - K=a/b, T1=1/b, T2=0, L=0 (patrz nagłówek pliku). x/u_history
        ZOSTAJĄ nietknięte (ciągłość stanu modelu), tylko jego dynamika się odświeża."""
        b_bezp = max(b, 1e-6)
        K = a / b_bezp
        T1 = 1.0 / b_bezp
        tf = signal.TransferFunction([K], [T1, 1.0])  # K/(T1*s+1) - 1 biegun, bez zera (patrz nagłówek pliku)
        sys_ss = signal.tf2ss(tf.num, tf.den)
        A_d, B_d, C_d, D_d, _ = signal.cont2discrete(sys_ss, STEP_SECONDS, method='zoh')

        self._mpc_model_A = A_d
        self._mpc_model_B = B_d
        self._mpc_model_C = C_d
        self._mpc_model_D = D_d
        self._mpc_model_opoznienie_bloki = 0
        if self._mpc_model_x is None:
            self._mpc_model_x = np.zeros((A_d.shape[0], 1))

    def mpc_model_adaptacyjny(self, row_data):
        czas_teraz = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        at_temp = float(row_data['AT_temp_powietrza'])
        crt_temp = float(row_data['CRT_temp_niegrzana'])

        a, b, c, proxy = self._model.aktualizuj_i_pobierz(czas_teraz, hrt_temp, at_temp)

        # Przebudowa modelu blokowego TYLKO na granicy bloku 15-minutowego (ta sama
        # siatka co _krok_mpc/_rozwiaz_mpc) - przebudowa co krok symulacji (dt=10s)
        # byłaby ~90x droższa (tf2ss+cont2discrete) bez żadnej korzyści, bo i tak nic
        # nie planuje się częściej niż raz na blok.
        bin_id = czas_teraz.value // NANOS_PER_BIN
        if bin_id != self._ostatni_bin_odswiezenia:
            self._odswiez_model_blokowy(a, b)
            self._ostatni_bin_odswiezenia = bin_id

        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        crt_forecast_fn = lambda: [crt_temp] * HORIZON_STEPS
        power_percent, status = self._krok_mpc(row_data, target_temperature, need_heat, crt_forecast_fn)

        self._model.zapamietaj_regresor(czas_teraz, hrt_temp, at_temp, power_percent / 100.0, proxy)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'mpc_status': status,
            'mpc_moc_planowana': self._mpc_plan_power_pct,
            'model_a_grzalka': float(a),
            'model_b_pogoda': float(b),
            'model_c_slonce': float(c),
        }
        return power_percent, diagnostics
