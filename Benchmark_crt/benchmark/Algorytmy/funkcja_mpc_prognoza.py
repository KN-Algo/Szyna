# Algorytmy/funkcja_mpc_prognoza.py
#
# Jak funkcja_mpc_liniowy.py (patrz mpc_wspolne.py po pełny opis mechaniki
# MPC), ale zaburzenie użyte przez MPC do przewidywania WŁASNEJ trajektorii
# bierze z prognozy Kalmana (rail_temperature_prediction - CRT, 2h horyzontu)
# zamiast zakładać wartość stałą - a cel/próg bezpieczeństwa liczony wariantem
# funkcji ryzyka Z PROGNOZĄ OPADU (KontrolerRyzykaOpadBazowy._evaluate_risk_setpoint_z_opadem,
# przewidywanie_opadow.py) - "pełna" wersja MPC wykorzystująca WSZYSTKIE
# dostępne prognozy. Porównanie z mpc_liniowy pokazuje wartość dodaną
# wiedzy o przyszłości przy pełnej optymalizacji trajektorii.

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy
from mpc_wspolne import _MPCMachineryMixin


class KontrolerMPCPrognoza(_MPCMachineryMixin, KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler (jak w funkcja_ryzyka_pid.py) -
        # MPC ma wyjście ciągłe, nie ma dyskretnych przełączeń do ograniczania.
        self.max_switches_per_day = max_switches_per_day

    def mpc_prognoza(self, row_data):
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
