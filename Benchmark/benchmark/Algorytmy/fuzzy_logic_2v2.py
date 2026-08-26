# Algorytmy/fuzzy_logic_2v2.py
#
# ALGORYTM: wariant fuzzy_logic_2.py z własnym, 7-regułowym rdzeniem wnioskowania
# (dodatkowa reguła "śnieg + chłodno -> HIGH", próg "lodowato" zależny od
# intensywności opadu zamiast stały) - patrz silniki_fuzzy.wnioskowanie_fl2v2.
# Wyjście również twardo zbinaryzowane (próg 50%). UWAGA: próg deszczu tu to
# precip > 0.2 (nie > 0.0 jak w pozostałych trzech wariantach) - zgodnie z
# oryginałem.

from silniki_fuzzy import wnioskowanie_fl2v2, binaryzuj


class KontrolerFuzzy2v2:

    def __init__(self, t_zadana=3.0, max_switches_per_day=12, **kwargs):
        self.T_ZADANA = t_zadana
        self.max_switches_per_day = max_switches_per_day

    def compute_control(self, row_data):
        hrt = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])

        jest_snieg = snow > 0.0
        jest_deszcz = precip > 0.2

        blad_T = self.T_ZADANA - hrt
        wynik = wnioskowanie_fl2v2(blad_T, hrt, precip, jest_snieg, jest_deszcz)
        return binaryzuj(wynik)
