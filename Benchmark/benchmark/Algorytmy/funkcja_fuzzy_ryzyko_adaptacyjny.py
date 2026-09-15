# Algorytmy/funkcja_fuzzy_ryzyko_adaptacyjny.py
#
# ALGORYTM: jak funkcja_fuzzy_ryzyko_1.py (cel z funkcji ryzyka, wykonawczo
# silnik rozmyty FL1 - patrz tam), ale DOŁOŻONY o AUTOMATYCZNE STROJENIE
# PROGÓW FUNKCJI PRZYNALEŻNOŚCI silnika rozmytego - dokładnie to, czego
# funkcja_fuzzy_ryzyko_1.py w swoim nagłówku wprost zaznacza jako brak ("silnik
# rozmyty sam w sobie nie jest przestrajany - nie ma odpowiednika SIMC dla
# progów rozmytych"). Ten plik jest tym odpowiednikiem - metoda IDENTYCZNA
# ("perturb-and-observe", proste wspinanie po zboczu bez gradientu) co
# funkcja_ryzyka_pid_auto_strojenie.py, tylko zastosowana do progów
# wnioskowania rozmytego (silniki_fuzzy.wnioskowanie_fl_parametryzowane)
# zamiast do progów setpointu funkcji ryzyka - patrz tam pełne uzasadnienie
# mechanizmu i notatki/propozycja_auto_strojenie.md.
#
# STROJONE PROGI (patrz silniki_fuzzy.wnioskowanie_fl_parametryzowane):
#   prog_chlodno          - granica między zbiorem "OK" a "chłodno" (blad_T, °C)
#   prog_mrozno            - granica między "chłodno" a "mroźno" (blad_T, °C)
#   prog_lodowato_dolny    - dolny koniec rampy "lodowato" (HRT, °C) - poniżej: pełne 100%
#   prog_lodowato_gorny    - górny koniec rampy "lodowato" (HRT, °C) - powyżej: reguła nieaktywna
#
# MECHANIZM: identyczny jak w funkcja_ryzyka_pid_auto_strojenie.py - co
# OKRES_STROJENIA_S liczy koszt minionego okresu (całka mocy % + WAGA_KARA_H x
# godziny z przekroczonym progiem śniegu/lodu/przegrzania, te same progi KARA_*
# co funkcja_nauka_kary_wspolna.py), porównuje z poprzednim okresem - spadek
# kosztu: kontynuuje kierunek, wzrost: odwraca kierunek KAŻDEGO progu osobno.
#
# OGRANICZENIA (te same co auto_strojenie, patrz tam): może utknąć w lokalnym
# minimum (brak losowej eksploracji), potrzebuje kilku okresów żeby się
# ustabilizować, WAGA_KARA_H jest ręcznie dobraną stałą.

from funkcja_ryzyka_wspolne import KontrolerRyzykaBazowy
from funkcja_nauka_kary_wspolna import KARA_PRZEGRZANIE_HRT_C, KARA_SNIEG_MM, KARA_LOD_MM
from silniki_fuzzy import (
    wnioskowanie_fl_parametryzowane, klamra_fl1,
    PROG_CHLODNO_DOMYSLNY, PROG_MROZNO_DOMYSLNY,
    PROG_LODOWATO_DOLNY_DOMYSLNY, PROG_LODOWATO_GORNY_DOMYSLNY,
)

OKRES_STROJENIA_S = 7 * 86400.0   # Jak w auto_strojenie - 7 dni symulowanego czasu na aktualizację.
WAGA_KARA_H = 50.0                # Jak w auto_strojenie - "cena" 1h z przekroczonym progiem kary, w %-mocy-godzinach.

KROK_STROJENIA = {
    'prog_chlodno': 0.2,
    'prog_mrozno': 0.2,
    'prog_lodowato_dolny': 0.2,
    'prog_lodowato_gorny': 0.2,
}
GRANICE_STROJENIA = {
    'prog_chlodno': (1.0, 5.0),                    # Wokół domyślnych 3.0°C.
    'prog_mrozno': (4.0, 9.0),                      # Wokół domyślnych 6.0°C, zawsze > prog_chlodno w praktyce (krok mały, granice rozłączne).
    'prog_lodowato_dolny': (-18.0, -12.0),          # Wokół domyślnych -15.0°C.
    'prog_lodowato_gorny': (-14.0, -9.0),           # Wokół domyślnych -12.0°C.
}


class KontrolerFuzzyRyzykoAdaptacyjny(KontrolerRyzykaBazowy):

    def __init__(self, max_switches_per_day=12):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day  # spójność interfejsu - regulator ciągły, bez limitu przełączeń

        self.prog_chlodno = PROG_CHLODNO_DOMYSLNY
        self.prog_mrozno = PROG_MROZNO_DOMYSLNY
        self.prog_lodowato_dolny = PROG_LODOWATO_DOLNY_DOMYSLNY
        self.prog_lodowato_gorny = PROG_LODOWATO_GORNY_DOMYSLNY

        self._strojenie_kierunek = {p: 1 for p in KROK_STROJENIA}
        self._strojenie_koszt_poprzedni = None
        self._strojenie_ostatnia_aktualizacja = None
        self._strojenie_moc_calka = 0.0     # Suma power_percent*dt/3600 w bieżącym okresie (%*h).
        self._strojenie_kara_snieg_s = 0.0
        self._strojenie_kara_lod_s = 0.0
        self._strojenie_kara_przegrzanie_s = 0.0
        # Log KAŻDEJ aktualizacji (jak historia_uczenia w nauka_kary*/historia_strojenia
        # w auto_strojenie) - do zakładki "Uczenie_adaptacyjne" w Excelu.
        self.historia_strojenia = []
        self.historia_uczenia = self.historia_strojenia  # alias - test_wszystkie_rownolegle.py zapisuje historia_uczenia automatycznie.

    def _zarejestruj_kary_strojenia(self, hrt_temp, snow_depth_mm, dt):
        if hrt_temp > KARA_PRZEGRZANIE_HRT_C:
            self._strojenie_kara_przegrzanie_s += dt
        if snow_depth_mm > KARA_SNIEG_MM:
            self._strojenie_kara_snieg_s += dt
        ice_proxy_mm = snow_depth_mm if hrt_temp <= 0.0 else 0.0
        if ice_proxy_mm > KARA_LOD_MM:
            self._strojenie_kara_lod_s += dt

    def _aktualizuj_strojenie(self, timestamp):
        if self._strojenie_ostatnia_aktualizacja is None:
            self._strojenie_ostatnia_aktualizacja = timestamp
            return

        if (timestamp - self._strojenie_ostatnia_aktualizacja).total_seconds() < OKRES_STROJENIA_S:
            return

        kary_h = (self._strojenie_kara_snieg_s + self._strojenie_kara_lod_s
                  + self._strojenie_kara_przegrzanie_s) / 3600.0
        koszt = self._strojenie_moc_calka + WAGA_KARA_H * kary_h

        if self._strojenie_koszt_poprzedni is not None and koszt > self._strojenie_koszt_poprzedni:
            for p in self._strojenie_kierunek:
                self._strojenie_kierunek[p] *= -1

        for p, krok in KROK_STROJENIA.items():
            wartosc = getattr(self, p) + self._strojenie_kierunek[p] * krok
            lo, hi = GRANICE_STROJENIA[p]
            setattr(self, p, min(max(wartosc, lo), hi))

        self.historia_strojenia.append({
            'timestamp': timestamp,
            'koszt': koszt,
            'moc_calka_pct_h': self._strojenie_moc_calka,
            'kary_h': kary_h,
            'prog_chlodno': self.prog_chlodno,
            'prog_mrozno': self.prog_mrozno,
            'prog_lodowato_dolny': self.prog_lodowato_dolny,
            'prog_lodowato_gorny': self.prog_lodowato_gorny,
        })

        self._strojenie_koszt_poprzedni = koszt
        self._strojenie_moc_calka = 0.0
        self._strojenie_kara_snieg_s = 0.0
        self._strojenie_kara_lod_s = 0.0
        self._strojenie_kara_przegrzanie_s = 0.0
        self._strojenie_ostatnia_aktualizacja = timestamp

    def fuzzy_ryzyko_adaptacyjny(self, row_data):
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
            wynik = wnioskowanie_fl_parametryzowane(
                blad_T, hrt_temp, jest_snieg, jest_deszcz,
                prog_chlodno=self.prog_chlodno, prog_mrozno=self.prog_mrozno,
                prog_lodowato_dolny=self.prog_lodowato_dolny, prog_lodowato_gorny=self.prog_lodowato_gorny,
            )
            power_percent = klamra_fl1(wynik)
            self._dodaj_flopy(40)  # Silnik FL1 (parametryzowany - te same 6 reguł Sugeno).

        self._krok_modelu(power_percent)

        timestamp = row_data['Timestamp']
        dt = self._dt_sterowania
        self._strojenie_moc_calka += power_percent * dt / 3600.0
        # Estymator śniegu już zaktualizowany PRZEZ _evaluate_risk_setpoint (przez
        # _estymuj_grubosc_sniegu_mm) - czytamy WYNIK bezpośrednio z self, NIE
        # wołamy estymatora drugi raz (podwójnie doliczyłoby przyrost/ubytek).
        self._zarejestruj_kary_strojenia(hrt_temp, self._snieg_estymowany_mm, dt)
        self._aktualizuj_strojenie(timestamp)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'strojone_progi': {
                'prog_chlodno': self.prog_chlodno,
                'prog_mrozno': self.prog_mrozno,
                'prog_lodowato_dolny': self.prog_lodowato_dolny,
                'prog_lodowato_gorny': self.prog_lodowato_gorny,
            },
        }
        return power_percent, diagnostics
