# Algorytmy/funkcja_mpc_binarny.py
#
# Jak funkcja_mpc_liniowy.py (patrz mpc_wspolne.py po pełny opis mechaniki MPC:
# model blokowy 15-minutowy z autotestu, move blocking, kara bezpieczeństwa),
# ale dziedziczy po _MPCMachineryMixinBinarny zamiast _MPCMachineryMixin - patrz
# tam pełny opis: moc na blok jest OGRANICZONA do {0%, 100%} (przekaźnik
# załącz/wyłącz, jak większość pozostałych algorytmów projektu), rozwiązywana
# WYCZERPUJĄCYM przeszukaniem (2^8=256 kombinacji, dokładne optimum globalne)
# zamiast QP z wyjściem ciągłym. Dodane 2026-09-15 na życzenie użytkownika -
# porównanie z mpc_liniowy (identyczny model/cel/częstotliwość przeplanowania,
# RÓŻNI SIĘ WYŁĄCZNIE dopuszczalnym zbiorem mocy) izoluje czysty koszt
# dyskretyzacji na przekaźnik binarny względem regulacji ciągłej (SSR/PWM).

from rdzen_kontrolera import HORIZON_STEPS
from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from mpc_wspolne import _MPCMachineryMixinBinarny


class KontrolerMPCBinarny(_MPCMachineryMixinBinarny, KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        # W ODRÓŻNIENIU od pozostałych wariantów MPC (wyjście ciągłe, parametr
        # przyjmowany tylko dla spójności interfejsu) - TU moc faktycznie JEST
        # binarna (0/100%), więc max_switches_per_day ma realne znaczenie, choć
        # NIE jest egzekwowany WEWNĄTRZ tego kontrolera (tak jak inne algorytmy
        # z bezpiecznikiem=True - ograniczenie liczby przełączeń wymusza
        # symulacja_fizyczna.py na poziomie referencyjnym normy, patrz
        # rejestr_algorytmow.podlega_bezpiecznikowi).
        self.max_switches_per_day = max_switches_per_day

    def mpc_binarny(self, row_data):
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
