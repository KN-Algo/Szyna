# Algorytmy/funkcja_mpc_liniowy.py
#
# Regulator MPC (patrz mpc_wspolne.py po pełny opis mechaniki: model blokowy
# 15-minutowy z autotestu, QP L-BFGS-B, move blocking) - wariant WARIANT
# KONTROLNY "bez prognozy pogody": temperatura CRT na całym horyzoncie
# planowania zakładana STAŁA (ostatni odczyt), zamiast prognozy Kalmana.
# Punkt odniesienia do funkcja_mpc_prognoza.py - porównanie tych dwóch
# pokazuje CZYSTĄ wartość dodaną prognozy pogody przy pełnej optymalizacji
# trajektorii (w odróżnieniu od pary *_opad reszty algorytmów, gdzie różnica
# dotyczy tylko furtki ucieczki - tu dotyczy całego mechanizmu przewidywania
# trajektorii wewnątrz MPC).
#
# Cel/próg bezpieczeństwa (target_temperature) mimo wszystko liczony przez
# funkcję ryzyka (_evaluate_risk_setpoint) - ta, tak jak WSZĘDZIE indziej w
# projekcie, wewnętrznie korzysta z prognozy Kalmana do wyznaczenia progu
# (warmup_soon/forecast_min_c) - "bez prognozy pogody" odnosi się WYŁĄCZNIE
# do zaburzenia użytego przez SAM MPC do przewidywania własnej trajektorii,
# nie do współdzielonej logiki wyznaczania progu (patrz mpc_wspolne.py,
# nagłówek, i AGENTS.md).

from rdzen_kontrolera import HORIZON_STEPS
from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from mpc_wspolne import _MPCMachineryMixin


class KontrolerMPCLiniowy(_MPCMachineryMixin, KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler (jak w funkcja_ryzyka_pid.py) -
        # MPC ma wyjście ciągłe, nie ma dyskretnych przełączeń do ograniczania.
        self.max_switches_per_day = max_switches_per_day

    def mpc_liniowy(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        self._zbuduj_model_blokowy_jesli_trzeba()

        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = self._evaluate_risk_setpoint(row_data)

        crt_temp = float(row_data['CRT_temp_niegrzana'])
        crt_forecast_fn = lambda: [crt_temp] * HORIZON_STEPS

        power_percent, status = self._krok_mpc(row_data, target_temperature, need_heat, crt_forecast_fn)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'mpc_status': status,
            'mpc_moc_planowana': self._mpc_plan_power_pct,
        }
        return power_percent, diagnostics
