# Algorytmy/funkcja_fuzzy_ryzyko_1.py
#
# ALGORYTM: cel wyznaczany przez funkcję ryzyka (pamięć + prognoza Kalmana +
# kara za śnieg - patrz funkcja_ryzyka_wspolne._evaluate_risk_setpoint), ale
# WYKONAWCZO obsłużony silnikiem rozmytym FL1 (ciągłe 0-100%, miękkie obcięcie
# krańców) zamiast histerezy/PID. Fuzzy logic jest tu regulatorem wykonawczym,
# funkcja ryzyka tylko dostarcza cel (target_temperature) i decyduje CZY w
# ogóle trzeba grzać (need_heat) - samą moc zawsze wylicza silnik rozmyty.
#
# PRZY STARCIE wykonuje JEDNORAZOWY autotest (patrz
# KontrolerRyzykaBazowy._autotest_startowy) - dopóki trwa, grzeje pełną mocą
# i nie podejmuje normalnych decyzji. Wynik identyfikacji zasila fizyczną
# prognozę HRT w _evaluate_risk_setpoint (cyfrowy bliźniak grzałki) - silnik
# rozmyty sam w sobie nie jest przez to przestrajany (nie ma odpowiednika
# SIMC dla progów rozmytych), korzysta tylko z lepszego celu/prognozy.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from silniki_fuzzy import wnioskowanie_fl_podstawowe, klamra_fl1


class KontrolerFuzzyRyzyko1(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day  # spójność interfejsu - regulator ciągły, bez limitu przełączeń

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
            jest_deszcz = precip > 0.0
            blad_T = target_temperature - hrt_temp
            wynik = wnioskowanie_fl_podstawowe(blad_T, hrt_temp, jest_snieg, jest_deszcz)
            power_percent = klamra_fl1(wynik)
            self._dodaj_flopy(40)  # Silnik FL1.

        self._krok_modelu(power_percent)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
        }
        return power_percent, diagnostics
