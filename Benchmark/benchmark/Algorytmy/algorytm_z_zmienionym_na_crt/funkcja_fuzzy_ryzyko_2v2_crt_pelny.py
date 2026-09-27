# Algorytmy/algorytm_z_zmienionym_na_crt/funkcja_fuzzy_ryzyko_2v2_crt_pelny.py
#
# WARIANT Algorytmy/funkcja_fuzzy_ryzyko_2v2.py (oryginał NIETKNIĘTY) - na
# życzenie użytkownika (2026-09-25, "żeby wyznacznikiem teraz była szyna
# zimna"): CAŁY algorytm (4 twarde progi ORAZ błąd regulacji, który zasila
# silnik rozmyty) liczony jest teraz względem CRT (szyna NIEogrzewana)
# zamiast HRT - CRT jest JEDYNYM wyznacznikiem decyzji.
#
# To "głębszy" z dwóch stopni konwersji na CRT - siostrzany, "płytszy"
# wariant (tylko 4 twarde progi na CRT, błąd regulacji zostaje przy HRT):
# funkcja_fuzzy_ryzyko_2v2_crt_progi.py.
#
# UWAGA: silnik wnioskowanie_fl2v2 (silniki_fuzzy.py) sam NIE wie, czy
# dostaje HRT czy CRT - jego drugi parametr pozycyjny nazywa się tam "hrt"
# wyłącznie opisowo (tak nazwano go, gdy silnik projektowano tylko do pracy
# na HRT) - w rzeczywistości to "aktualny odczyt temperatury szyny, na
# podstawie którego silnik podejmuje decyzje", więc podanie mu CRT zamiast
# HRT w pełni wystarcza - silniki_fuzzy.py NIE wymaga żadnej zmiany.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from histereza_let1 import wylicz_poziom_ryzyka
from silniki_fuzzy import wnioskowanie_fl2v2, binaryzuj


class KontrolerFuzzyRyzyko2v2CrtPelny(KontrolerRyzykaBazowy):
    def _autotest_startowy(self, row_data):
        return False  # Wymusza natychmiastowe przejście do logiki rozmytej

    def __init__(self, max_switches_per_day=20):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

    def fuzzy_ryzyko_crt_pelny(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        crt_temp = float(row_data['CRT_temp_niegrzana'])  # ZMIANA: jedyny wyznacznik, wszędzie zamiast HRT
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        at_temp = float(row_data['AT_temp_powietrza'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if crt_temp < -10.0:
            power_percent = 100.0
        elif crt_temp >= 6.0:
            power_percent = 0.0
        elif crt_temp >= 3.0 and at_temp < 0.0:
            power_percent = 0.0
        elif at_temp <= -15.0 and crt_temp < 10.0:
            power_percent = 100.0
        else:
            jest_snieg = snow > 0.0
            jest_deszcz = precip > 0.2
            blad_T = target_temperature - crt_temp  # ZMIANA: błąd regulacji też liczony względem CRT
            ryzyko = wylicz_poziom_ryzyka(row_data)
            wynik = wnioskowanie_fl2v2(blad_T, crt_temp, ryzyko, jest_snieg, jest_deszcz, at_temp)
            power_percent = binaryzuj(wynik)
            self._dodaj_flopy(48)  # Silnik FL2v2 (7 reguł).

        self._krok_modelu(power_percent)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
        }
        return power_percent, diagnostics
