# Algorytmy/funkcja_mpc_prognoza_binarny.py
#
# Jak funkcja_mpc_prognoza.py (patrz mpc_wspolne.py po pełny opis mechaniki MPC),
# ale dziedziczy po _MPCMachineryMixinBinarny zamiast _MPCMachineryMixin - patrz
# funkcja_mpc_binarny.py po pełny opis: moc na blok OGRANICZONA do {0%, 100%},
# rozwiązywana WYCZERPUJĄCYM przeszukaniem (2^8=256 kombinacji) zamiast QP z
# wyjściem ciągłym. Dodane 2026-09-15 na życzenie użytkownika, żeby porównanie
# ciągłe-vs-binarne było KOMPLETNE na wszystkich 3 wariantach MPC (nie tylko
# mpc_liniowy/mpc_binarny) - punkt odniesienia tu to mpc_prognoza_pogody
# (identyczny model/cel/prognoza, RÓŻNI SIĘ WYŁĄCZNIE dopuszczalnym zbiorem mocy).

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy
from mpc_wspolne import _MPCMachineryMixinBinarny


class KontrolerMPCPrognozaBinarny(_MPCMachineryMixinBinarny, KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # Jak w mpc_binarny - TU moc faktycznie JEST binarna (0/100%), patrz tam uzasadnienie.
        self.max_switches_per_day = max_switches_per_day

    def mpc_prognoza_binarny(self, row_data):
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
