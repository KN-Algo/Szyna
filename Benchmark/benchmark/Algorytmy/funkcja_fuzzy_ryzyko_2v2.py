# Algorytmy/funkcja_fuzzy_ryzyko_2v2.py
#
# Jak funkcja_fuzzy_ryzyko_2.py, ale regulator wykonawczy to silnik FL2v2
# (7 reguł, dodatkowa reguła śnieg+chłodno, próg "lodowato" zależny od
# intensywności opadu; próg deszczu precip>0.2 jak w oryginale FL2v2). Cel
# nadal z funkcji ryzyka - patrz funkcja_ryzyka_wspolne.py.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from silniki_fuzzy import wnioskowanie_fl2v2, binaryzuj


class KontrolerFuzzyRyzyko2v2(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

    def fuzzy_ryzyko(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        hrt_temp = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if not need_heat:
            power_percent = 0.0
        else:
            jest_snieg = snow > 0.0
            jest_deszcz = precip > 0.2
            blad_T = target_temperature - hrt_temp
            wynik = wnioskowanie_fl2v2(blad_T, hrt_temp, precip, jest_snieg, jest_deszcz)
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
