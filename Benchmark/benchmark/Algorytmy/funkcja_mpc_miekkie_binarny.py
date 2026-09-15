# Algorytmy/funkcja_mpc_miekkie_binarny.py
#
# Jak funkcja_mpc_miekkie.py (patrz mpc_wspolne.py po opis mechaniki MPC i tego
# pliku po opis bariery wykładniczej), ale dziedziczy po
# _MPCMachineryMixinBinarny zamiast _MPCMachineryMixin - patrz
# funkcja_mpc_binarny.py po pełny opis: moc na blok OGRANICZONA do {0%, 100%},
# rozwiązywana WYCZERPUJĄCYM przeszukaniem (2^8=256 kombinacji) zamiast QP z
# wyjściem ciągłym. Dodane 2026-09-15 na życzenie użytkownika, żeby porównanie
# ciągłe-vs-binarne było KOMPLETNE na wszystkich 3 wariantach MPC - punkt
# odniesienia tu to mpc_miekkie_ograniczenia (identyczny model/cel/bariera
# wykładnicza, RÓŻNI SIĘ WYŁĄCZNIE dopuszczalnym zbiorem mocy).

import numpy as np

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy
from mpc_wspolne import _MPCMachineryMixinBinarny

MPC_BARIERA_K_NA_C = 1.0    # Jak w funkcja_mpc_miekkie.py - patrz tam uzasadnienie.
MPC_BARIERA_W = 5.0
MPC_BARIERA_WYKLADNIK_LIMIT = 50.0


class KontrolerMPCMiekkieBinarny(_MPCMachineryMixinBinarny, KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # Jak w mpc_binarny - TU moc faktycznie JEST binarna (0/100%), patrz tam uzasadnienie.
        self.max_switches_per_day = max_switches_per_day

    def _kara_bezpieczenstwa_mpc(self, hrt_pred, target_temperature):
        """Bariera wykładnicza - identyczna jak w funkcja_mpc_miekkie.KontrolerMPCMiekkie, patrz tam pełny opis."""
        margin = hrt_pred - target_temperature
        wykladnik = np.clip(-MPC_BARIERA_K_NA_C * margin, -MPC_BARIERA_WYKLADNIK_LIMIT, MPC_BARIERA_WYKLADNIK_LIMIT)
        return float(np.sum(MPC_BARIERA_W * np.exp(wykladnik)))

    def mpc_miekkie_binarny(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        self._zbuduj_model_blokowy_jesli_trzeba()

        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = self._evaluate_risk_setpoint_z_opadem(row_data)

        crt_forecast_fn = self.rail_temperature_prediction

        power_percent, status = self._krok_mpc(row_data, target_temperature, need_heat, crt_forecast_fn)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'mpc_status': status,
            'mpc_moc_planowana': self._mpc_plan_power_pct,
        }
        return power_percent, diagnostics
