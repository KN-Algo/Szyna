# Algorytmy/funkcja_fuzzy_normy_2.py
#
# Jak funkcja_fuzzy_normy_1.py, ale regulator wykonawczy to silnik FL2 -
# wyjście twardo zbinaryzowane (próg 50%). Cel z normy LET-1 - patrz
# funkcja_normy_wspolne.py.

from funkcja_normy_wspolne import KontrolerNormyCiaglaBazowy
from silniki_fuzzy import wnioskowanie_fl_podstawowe, binaryzuj


class KontrolerFuzzyNormy2(KontrolerNormyCiaglaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

    def fuzzy_normy(self, row_data):
        hrt_temp = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        target_temperature, need_heat, reason = self._evaluate_norm_setpoint(row_data)

        if not need_heat:
            power_percent = 0.0
        else:
            jest_snieg = snow > 0.0
            jest_deszcz = precip > 0.0
            blad_T = target_temperature - hrt_temp
            wynik = wnioskowanie_fl_podstawowe(blad_T, hrt_temp, jest_snieg, jest_deszcz)
            power_percent = binaryzuj(wynik)
            self._dodaj_flopy(40)  # Silnik FL1/FL2.

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
        }
        return power_percent, diagnostics
