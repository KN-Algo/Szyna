# Algorytmy/funkcja_fuzzy_ryzyko_agresywny.py
#
# ALGORYTM: jak funkcja_fuzzy_ryzyko_1.py (cel z funkcji ryzyka, wykonawczo
# silnik rozmyty FL1), ale z WYRAŹNIE OSTRZEJSZĄ reakcją na pogarszające się
# warunki - silniki_fuzzy.wnioskowanie_fl_agresywne zamiast
# wnioskowanie_fl_podstawowe. Na WYRAŹNE życzenie użytkownika (2026-09-15,
# "bardziej karaj fuzzy logic... żeby znacznie mocniej reagował na warunki
# złe") - jako OSOBNY, nowy algorytm (fuzzy_ryzyko_1 zostaje bez zmian jako
# punkt odniesienia "normalnej" reakcji).
#
# JAK dokładnie "karze" mocniej (patrz silniki_fuzzy.py, stałe *_AGRESYWNY/A) -
# CELOWO nie przez dodanie nowych reguł ani mnożnik na wyniku, tylko przez
# ZMIANĘ SAMYCH FUNKCJI PRZYNALEŻNOŚCI, więc dalej jest to prawidłowe
# wnioskowanie Sugeno (Ta sama matematyka co FL1, inny "kształt" zbiorów
# rozmytych, żadnego ad-hoc skalowania po fakcie):
#   - Granice OK -> chłodno -> mroźno ZACIEŚNIONE (1.5°C/3.5°C zamiast
#     3.0°C/6.0°C) - pełna moc (MOC_HIGH przy opadzie, wysoka MOC_MED bez
#     opadu) osiągana przy DUŻO MNIEJSZYM błędzie regulacji niż w FL1.
#   - Próg "lodowato" (ochrona przed bardzo niską HRT) PRZESUNIĘTY w górę
#     (-12°C/-8°C zamiast -15°C/-12°C) - pełna MOC_HIGH z powodu niskiej HRT
#     włącza się przy ŁAGODNIEJSZYM mrozie, zanim sytuacja stanie się naprawdę
#     krytyczna.
#   - Moc pośrednia (LOW/MED) PODNIESIONA (50%/85% zamiast 25%/60%) - nawet w
#     "łagodnych złych" warunkach (chłodno bez opadu, mroźno bez opadu) grzeje
#     WYRAŹNIE mocniej niż FL1, zamiast czekać aż błąd sam urośnie.
#
# Oczekiwany kompromis: WYŻSZA energia i mniej epizodów poniżej progów
# bezpieczeństwa (kara_bezpieczenstwa) niż fuzzy_ryzyko_1 - to jest CEL tego
# wariantu (agresywny = konserwatywny/bezpieczny kosztem energii), nie błąd.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from silniki_fuzzy import wnioskowanie_fl_agresywne, klamra_fl1


class KontrolerFuzzyRyzykoAgresywny(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day  # spójność interfejsu - regulator ciągły, bez limitu przełączeń

    def fuzzy_ryzyko_agresywny(self, row_data):
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
            wynik = wnioskowanie_fl_agresywne(blad_T, hrt_temp, jest_snieg, jest_deszcz)
            power_percent = klamra_fl1(wynik)
            self._dodaj_flopy(40)  # Silnik FL1 agresywny - te same 6 reguł Sugeno co FL1, tylko inne stałe.

        self._krok_modelu(power_percent)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
        }
        return power_percent, diagnostics
