# Algorytmy/funkcja_mpc_miekkie.py
#
# Wariant mpc_prognoza_pogody (patrz funkcja_mpc_prognoza.py - ta sama prognoza
# CRT/opadu, ten sam cel z kaskady funkcji ryzyka) z INNYM KSZTAŁTEM kary za
# zbliżanie się do progu bezpieczeństwa w funkcji kosztu MPC: zamiast kwadratowej
# kary PROGOWEJ (mpc_wspolne._MPCMachineryMixin._kara_bezpieczenstwa_mpc - ZERO
# dopóki przewidywana HRT jest nad progiem, kwadrat deficytu dopiero po
# przekroczeniu) używa BARIERY WYKŁADNICZEJ - kara rośnie już PRZED przekroczeniem
# progu (bez ostrego "zera aż do granicy"), i rośnie SZYBCIEJ niż kwadratowo, gdy
# przewidywana HRT faktycznie spadnie poniżej progu.
#
# Cel testu (patrz specyfikacja MPC w AGENTS.md): sprawdzić, czy sam KSZTAŁT kary
# progowej wpływa na kompromis energia/bezpieczeństwo, niezależnie od tego, że
# zewnętrzny bezpiecznik normy (symulacja_fizyczna, snow_reference_mm) i tak obcina
# wyjście - MPC z barierą powinien "wyprzedzająco" zostawiać większy zapas cieplny
# nad progiem niż wariant z karą czysto progową.

import numpy as np

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy
from mpc_wspolne import _MPCMachineryMixin

MPC_BARIERA_K_NA_C = 1.0    # Stromość bariery [1/°C] - jak szybko kara rośnie w miarę zbliżania się do progu.
MPC_BARIERA_W = 5.0         # Skala kary DOKŁADNIE na progu (margin=0) - ten sam rząd wielkości co MPC_WAGA_BEZPIECZENSTWO*1°C^2, żeby oba warianty MPC startowały z porównywalną "wagą" bezpieczeństwa.
MPC_BARIERA_WYKLADNIK_LIMIT = 50.0  # Obcięcie wykładnika przed exp() - zabezpieczenie przed przepełnieniem float64 przy skrajnych, przejściowych próbkach solvera (nie zmienia optymalnego rozwiązania, tylko chroni numerykę).


class KontrolerMPCMiekkie(_MPCMachineryMixin, KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler (jak w pozostałych wariantach MPC) -
        # MPC ma wyjście ciągłe, nie ma dyskretnych przełączeń do ograniczania.
        self.max_switches_per_day = max_switches_per_day

    def _kara_bezpieczenstwa_mpc(self, hrt_pred, target_temperature):
        """
        Bariera wykładnicza: margin = hrt_pred - target_temperature (dodatni = nad
        progiem, ujemny = pod progiem). kara = W * exp(-K * margin) - przy margin=0
        kara = W (jak "próg wejścia"), maleje wykładniczo im dalej NAD progiem
        (nigdy dokładnie do zera - w odróżnieniu od wariantu progowego, tu zawsze
        jest jakaś, choć mała, zachęta do zostawienia zapasu), rośnie wykładniczo
        (szybciej niż kwadratowo) im głębiej POD progiem.
        """
        margin = hrt_pred - target_temperature
        wykladnik = np.clip(-MPC_BARIERA_K_NA_C * margin, -MPC_BARIERA_WYKLADNIK_LIMIT, MPC_BARIERA_WYKLADNIK_LIMIT)
        return float(np.sum(MPC_BARIERA_W * np.exp(wykladnik)))

    def mpc_miekkie(self, row_data):
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
