# Algorytmy/fuzzy_logic_2.py
#
# ALGORYTM: regulator rozmyty (Sugeno) wokół STAŁEGO celu T_ZADANA - jak
# fuzzy_logic_1.py, ale wyjście jest TWARDO zbinaryzowane (próg 50%: <50% -> 0%,
# >=50% -> 100%) zamiast ciągłe. Rdzeń wnioskowania (6 reguł) współdzielony z
# fuzzy_logic_1.py/fuzzy_logic_3.py - patrz silniki_fuzzy.py.

from silniki_fuzzy import wnioskowanie_fl_podstawowe, binaryzuj


class KontrolerFuzzy2:

    def __init__(self, t_zadana=3.0, max_switches_per_day=12, **kwargs):
        self.T_ZADANA = t_zadana
        self.max_switches_per_day = max_switches_per_day  # kompatybilność interfejsu (limit niezaimplementowany w FL2)
        self._flops_licznik = 0  # Licznik RZECZYWISTYCH FLOPs - patrz rdzen_kontrolera.KontrolerBazowy._dodaj_flopy.

    def compute_control(self, row_data):
        hrt = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])

        jest_snieg = snow > 0.0
        jest_deszcz = precip > 0.0

        blad_T = self.T_ZADANA - hrt
        wynik = wnioskowanie_fl_podstawowe(blad_T, hrt, jest_snieg, jest_deszcz)
        self._flops_licznik += 40  # Silnik FL1/FL2 (4 funkcje przynależności + 6 reguł Sugeno).
        return binaryzuj(wynik)
