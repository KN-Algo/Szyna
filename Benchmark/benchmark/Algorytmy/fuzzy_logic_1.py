# Algorytmy/fuzzy_logic_1.py
#
# ALGORYTM: regulator rozmyty (Sugeno) wokół STAŁEGO celu T_ZADANA - wyjście
# ciągłe (0-100%) z miękkim obcięciem krańców (<10% -> 0%, >90% -> 100%).
# Rdzeń wnioskowania (6 reguł) współdzielony z fuzzy_logic_2.py/fuzzy_logic_3.py -
# patrz silniki_fuzzy.py.

from silniki_fuzzy import wnioskowanie_fl_podstawowe, klamra_fl1


class KontrolerFuzzy1:

    def __init__(self, t_zadana=3.0, max_switches_per_day=12, **kwargs):
        self.T_ZADANA = t_zadana
        self.max_switches_per_day = max_switches_per_day  # kompatybilność interfejsu (limit niezaimplementowany w FL1)
        self._flops_licznik = 0  # Licznik RZECZYWISTYCH FLOPs - patrz rdzen_kontrolera.KontrolerBazowy._dodaj_flopy.

    def compute_control(self, row_data):
        hrt = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])

        jest_snieg = snow > 0.0
        jest_deszcz = precip > 0.0

        blad_T = self.T_ZADANA - hrt
        wynik = wnioskowanie_fl_podstawowe(blad_T, hrt, jest_snieg, jest_deszcz)
        self._flops_licznik += 40  # Silnik FL1 (4 funkcje przynależności + 6 reguł Sugeno).
        return klamra_fl1(wynik)
