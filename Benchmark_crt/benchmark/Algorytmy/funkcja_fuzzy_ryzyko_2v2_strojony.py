# Algorytmy/funkcja_fuzzy_ryzyko_2v2_strojony.py
#
# KOPIA funkcja_fuzzy_ryzyko_2v2.py (ten plik NIETKNIĘTY, zostaje punktem odniesienia) - 2026-09-28,
# na życzenie użytkownika: "przeszukać nastaw dla fuzzy ryzyko 2v2, iteracyjnie sprawdzać poprawność
# na najzimniejszym terenie przez miesiąc". Jedyna różnica: silnik FL2v2 to wersja PARAMETRYZOWANA
# (silniki_fuzzy.wnioskowanie_fl2v2_parametryzowane, zweryfikowana jako bit-identyczna z oryginałem
# przy domyślnych argumentach - 20000 losowych próbek, 0 rozbieżności), a jej 6 progów jest teraz
# atrybutami instancji (nie stałymi modułu) - żeby skrypt strojący (testy/strojenie_fuzzy_2v2.py)
# mógł je nadpisać przy tworzeniu kontrolera, bez subprocessów/zmiennych środowiskowych.
#
# Domyślne wartości = DOKŁADNIE te same liczby co w oryginale (patrz stałe FL2V2_*_DOMYSLNY w
# silniki_fuzzy.py) - ten plik bez żadnych nadpisań zachowuje się identycznie jak
# funkcja_fuzzy_ryzyko_2v2.py. Wynik strojenia (wybrane nastawy + metodologia) - patrz
# notatki/strojenie_fuzzy_2v2.md, gdy przebieg strojenia się zakończy.
#
# POPRAWIONY PRZY OKAZJI BŁĄD w silniku (2026-09-28, wykryty przy budowie tego pliku i testy/
# strojenie_fuzzy_2v2.py, naprawiony w silniki_fuzzy.py DLA OBU wersji silnika, oryginalnej i
# parametryzowanej - patrz komentarz w wnioskowanie_fl2v2() tam): gałąź "hrt > -5.0 and
# at_temp <= -10.0" zwracała literał string 'rosnie' zamiast liczby, co wywalało TypeError w
# binaryzuj() - potwierdzone na realnym przebiegu (18/364 zadań, wszystkie warianty FL2v2, na
# lokalizacjach z dość mroźną nocą w krótkim testowym oknie). Dotyczyło WSZYSTKICH 9
# zarejestrowanych algorytmów korzystających z tego silnika (fuzzy_ryzyko_2v2*, fuzzy_normy_2v2,
# fuzzy_logic_2v2) - realne ryzyko przerwania przebiegu na klastrze, nie tylko tego pliku.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from histereza_let1 import wylicz_poziom_ryzyka
from silniki_fuzzy import (
    wnioskowanie_fl2v2_parametryzowane, binaryzuj,
    FL2V2_PROG_CHLODNO_DOMYSLNY, FL2V2_PROG_MROZNO_DOMYSLNY, FL2V2_PROG_GORACO_DOMYSLNY,
    FL2V2_RYZYKO_WSPOLCZYNNIK_DOMYSLNY, FL2V2_RYZYKO_PROG_BONUS_DOMYSLNY, FL2V2_RYZYKO_PROG_MOC_DOMYSLNY,
    MOC_LOW, MOC_MED,
)


class KontrolerFuzzyRyzyko2v2Strojony(KontrolerRyzykaBazowy):
    def _autotest_startowy(self, row_data):
        return False  # Wymusza natychmiastowe przejście do logiki rozmytej (jak w oryginale).

    def __init__(self, max_switches_per_day=20,
                 prog_chlodno=FL2V2_PROG_CHLODNO_DOMYSLNY, prog_mrozno=FL2V2_PROG_MROZNO_DOMYSLNY,
                 prog_goraco=FL2V2_PROG_GORACO_DOMYSLNY, ryzyko_wspolczynnik=FL2V2_RYZYKO_WSPOLCZYNNIK_DOMYSLNY,
                 ryzyko_prog_bonus=FL2V2_RYZYKO_PROG_BONUS_DOMYSLNY, ryzyko_prog_moc=FL2V2_RYZYKO_PROG_MOC_DOMYSLNY,
                 moc_low=MOC_LOW, moc_med=MOC_MED, **kwargs):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day
        # Nastawy silnika FL2v2 - patrz silniki_fuzzy.wnioskowanie_fl2v2_parametryzowane po opis każdej.
        self.prog_chlodno = prog_chlodno
        self.prog_mrozno = prog_mrozno
        self.prog_goraco = prog_goraco
        self.ryzyko_wspolczynnik = ryzyko_wspolczynnik
        self.ryzyko_prog_bonus = ryzyko_prog_bonus
        self.ryzyko_prog_moc = ryzyko_prog_moc
        self.moc_low = moc_low
        self.moc_med = moc_med

    def fuzzy_ryzyko(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        hrt_temp = float(row_data['CRT_temp_niegrzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        at_temp = float(row_data['AT_temp_powietrza'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint(row_data)

        if hrt_temp < -10.0:
            power_percent = 100.0
        else:
            jest_snieg = snow > 0.0
            jest_deszcz = precip > 0.2
            blad_T = target_temperature - hrt_temp
            ryzyko = wylicz_poziom_ryzyka(row_data)
            wynik = wnioskowanie_fl2v2_parametryzowane(
                blad_T, hrt_temp, ryzyko, jest_snieg, jest_deszcz, at_temp,
                prog_chlodno=self.prog_chlodno, prog_mrozno=self.prog_mrozno, prog_goraco=self.prog_goraco,
                ryzyko_wspolczynnik=self.ryzyko_wspolczynnik, ryzyko_prog_bonus=self.ryzyko_prog_bonus,
                ryzyko_prog_moc=self.ryzyko_prog_moc, moc_low=self.moc_low, moc_med=self.moc_med)
            power_percent = binaryzuj(wynik)
            self._dodaj_flopy(50)  # Silnik FL2v2 parametryzowany (7 reguł + podstawienie progów).

        self._krok_modelu(power_percent)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
        }
        return power_percent, diagnostics
