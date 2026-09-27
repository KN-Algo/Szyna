# Algorytmy/algorytm_z_zmienionym_na_crt/funkcja_fuzzy_ryzyko_2v2_crt_progi.py
#
# WARIANT Algorytmy/funkcja_fuzzy_ryzyko_2v2.py (oryginał NIETKNIĘTY, zostaje
# jak był) - na życzenie użytkownika (2026-09-25, "żeby wyznacznikiem teraz
# była szyna zimna"): wyznacznikiem TWARDYCH PROGÓW (4 gałęzie if/elif PRZED
# silnikiem rozmytym) jest teraz CRT (szyna NIEogrzewana) zamiast HRT.
#
# To "płytszy" z dwóch stopni konwersji na CRT - błąd regulacji (blad_T),
# który zasila sam silnik rozmyty (wnioskowanie_fl2v2), ZOSTAJE liczony
# względem HRT, bez zmian (bo to HRT jest rzeczywistym celem grzania - CRT z
# definicji nigdy się nie nagrzeje). Siostrzany, "głębszy" wariant, w którym
# WSZYSTKO (łącznie z błędem regulacji) liczone jest względem CRT:
# funkcja_fuzzy_ryzyko_2v2_crt_pelny.py.
#
# Wszystko poza tą jedną zmianą (4 progi) jest identyczne z oryginałem -
# patrz tam po pełny opis reszty logiki (funkcja ryzyka jako źródło setpointu,
# silnik FL2v2 7-regułowy, wylicz_poziom_ryzyka jako dynamiczne ryzyko).

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from histereza_let1 import wylicz_poziom_ryzyka
from silniki_fuzzy import wnioskowanie_fl2v2, binaryzuj

# BENCHMARK_CRT (2026-09-26): 4 progi niżej przeskalowane R_CRT_HRT≈0,146
# (zmierzony ΔCRT/ΔHRT pod pełną mocą - patrz funkcja_ryzyka_wspolne.py) - były
# kalibrowane pod HRT, CRT fizycznie nie ma jak ich osiągnąć wprost.
R_CRT_HRT = 0.146
PROG_GORACO_CRT = round(6.0 * R_CRT_HRT, 2)
PROG_SREDNI_CRT = round(3.0 * R_CRT_HRT, 2)
PROG_SUFIT_CRT = round(10.0 * R_CRT_HRT, 2)


class KontrolerFuzzyRyzyko2v2CrtProgi(KontrolerRyzykaBazowy):
    def _autotest_startowy(self, row_data):
        return False  # Wymusza natychmiastowe przejście do logiki rozmytej

    def __init__(self, max_switches_per_day=20):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

    def fuzzy_ryzyko_crt_progi(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        hrt_temp = float(row_data['HRT_temp_grzana'])
        crt_temp = float(row_data['CRT_temp_niegrzana'])  # ZMIANA: wyznacznik 4 progów niżej (było HRT)
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        at_temp = float(row_data['AT_temp_powietrza'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        # ZMIANA: te 4 progi czytają teraz CRT (szyna zimna), nie HRT jak w oryginale
        # (3 z nich - PROG_GORACO/SREDNI/SUFIT - dodatkowo przeskalowane R_CRT_HRT).
        if crt_temp < -10.0:
            power_percent = 100.0
        elif crt_temp >= PROG_GORACO_CRT:
            power_percent = 0.0
        elif crt_temp >= PROG_SREDNI_CRT and at_temp < 0.0:
            power_percent = 0.0
        elif at_temp <= -15.0 and crt_temp < PROG_SUFIT_CRT:
            power_percent = 100.0
        else:
            jest_snieg = snow > 0.0
            jest_deszcz = precip > 0.2
            blad_T = target_temperature - hrt_temp  # NIEZMIENIONE - błąd nadal względem HRT (patrz nagłówek)
            ryzyko = wylicz_poziom_ryzyka(row_data)
            wynik = wnioskowanie_fl2v2(blad_T, hrt_temp, ryzyko, jest_snieg, jest_deszcz, at_temp)
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
