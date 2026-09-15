# Algorytmy/funkcja_mpc_prognoza_zabezpieczony.py
#
# Jak funkcja_mpc_prognoza.py (patrz mpc_wspolne.py po opis mechaniki MPC), ale
# dziedziczy po _MPCMachineryMixinZabezpieczony zamiast po _MPCMachineryMixin -
# patrz tam pełny opis DWÓCH warstw zabezpieczeń (kontrola jakości dopasowania
# SOPDT + krzyżowa kontrola bieżącego pomiaru HRT). Celowo OSOBNY, zarejestrowany
# algorytm (nie zmiana istniejącego mpc_prognoza_pogody) - na życzenie
# użytkownika 2026-09-15, żeby test awaryjności czujnikow
# (testy/test_awarie_czujnikow.py) mógł pokazać WARTOŚĆ tych zabezpieczeń wprost,
# obok niezabezpieczonej wersji referencyjnej.

from funkcja_ryzyka_wspolne import KontrolerRyzykaOpadBazowy
from mpc_wspolne import _MPCMachineryMixinZabezpieczony


class KontrolerMPCPrognozaZabezpieczony(_MPCMachineryMixinZabezpieczony, KontrolerRyzykaOpadBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # max_switches_per_day przyjmowane wyłącznie dla spójności interfejsu z
        # rejestr_algorytmow.stworz_kontroler (jak w pozostałych wariantach MPC) -
        # MPC ma wyjście ciągłe, nie ma dyskretnych przełączeń do ograniczania.
        self.max_switches_per_day = max_switches_per_day

    def mpc_prognoza_zabezpieczony(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        self._zbuduj_model_blokowy_jesli_trzeba()

        row_do_oceny, hrt_czujnik_odrzucony = self._wiarygodny_pomiar_hrt(row_data)
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = self._evaluate_risk_setpoint_z_opadem(row_do_oceny)

        crt_forecast_fn = self.rail_temperature_prediction

        power_percent, status = self._krok_mpc(row_do_oceny, target_temperature, need_heat, crt_forecast_fn)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'mpc_status': status,
            'mpc_moc_planowana': self._mpc_plan_power_pct,
            'hrt_czujnik_odrzucony': hrt_czujnik_odrzucony,
            'model_blokowy_odrzucony': self._mpc_model_odrzucony,
        }
        return power_percent, diagnostics
