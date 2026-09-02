# Algorytmy/funkcja_ryzyka_pid_auto_strojenie.py
#
# ALGORYTM: risk_function_pid (funkcja ryzyka, PID adaptacyjny - autotest +
# SIMC + cyfrowy bliźniak, patrz funkcja_ryzyka_pid.py) DOŁOŻONY o
# AUTOMATYCZNE STROJENIE progów setpointu - implementacja propozycji z
# notatki/propozycja_auto_strojenie.md ("perturb-and-observe", proste
# wspinanie po zboczu bez gradientu - to samo podejście co _czynnik_nauczony
# w funkcja_nauka_kary_wspolna.py, rozszerzone na KILKA progów naraz z
# kierunkiem zmiany, nie tylko jedną wielkość).
#
# STROJONE PROGI (v1 - zestaw celowo ograniczony do progów bezpiecznych do
# strojenia bez zmiany reszty kaskady, patrz funkcja_ryzyka_wspolne.py):
#   hrt_on_precip              - cel przy opadzie śniegu (bazowy, przed karą)
#   at_low_freeze               - próg suchego mrozu (kiedy w ogóle zaczynamy grzać)
#   hrt_on_dry                  - cel przy suchym mrozie
#   risk_snow_penalty_per_mm_c  - kara za mm zalegającego śniegu (jak mocno
#                                  reagujemy na grubszą pokrywę)
#
# MECHANIZM: co OKRES_STROJENIA_S (7 dni symulowanego czasu) liczy KOSZT
# minionego okresu = zużyta "energia" (całka mocy % po czasie, w %·h - proxy,
# nie prawdziwe kWh, żeby nie importować stałej grzałki z symulacja_fizyczna.py)
# + WAGA_KARA_H x (godziny spędzone z przekroczonym progiem śniegu/lodu/przegrzania
# - te same progi KARA_* co funkcja_nauka_kary_wspolna.py, dla spójności).
# Porównuje z kosztem POPRZEDNIEGO okresu: jeśli spadł, kontynuuje w tym samym
# kierunku zmiany każdego progu; jeśli wzrósł, ODWRACA kierunek. Każdy próg ma
# WŁASNY, mały krok zmiany i twarde granice (min/max) - patrz KROK_STROJENIA/
# GRANICE_STROJENIA niżej. Historia każdej aktualizacji logowana do
# self.historia_strojenia (analogicznie do historia_uczenia w nauka_kary*) -
# do zakładki Excela pokazującej krzywą strojenia w czasie.
#
# OGRANICZENIA (świadome, udokumentowane w notatki/propozycja_auto_strojenie.md):
# może utknąć w lokalnym minimum (brak losowej eksploracji), potrzebuje kilku
# okresów żeby się ustabilizować, WAGA_KARA_H jest ręcznie dobraną stałą.

from funkcja_ryzyka_pid import KontrolerRyzykaPID
from funkcja_nauka_kary_wspolna import KARA_PRZEGRZANIE_HRT_C, KARA_SNIEG_MM, KARA_LOD_MM

OKRES_STROJENIA_S = 7 * 86400.0   # Co ile sekund symulowanego czasu następuje jedna aktualizacja progów (7 dni - dłużej niż OKRES_UCZENIA_S w nauka_kary, żeby zmiana progu zdążyła się objawić).
WAGA_KARA_H = 50.0                # "Cena" jednej godziny spędzonej z przekroczonym progiem kary, w jednostkach %-mocy-godzin (patrz uzasadnienie w nagłówku pliku) - kalibracja ręczna, do rewizji.

KROK_STROJENIA = {
    'hrt_on_precip': 0.2,
    'at_low_freeze': 0.2,
    'hrt_on_dry': 0.1,
    'risk_snow_penalty_per_mm_c': 0.005,
}
GRANICE_STROJENIA = {
    'hrt_on_precip': (2.0, 7.0),
    'at_low_freeze': (-8.0, -2.0),
    'hrt_on_dry': (-1.0, 3.0),
    'risk_snow_penalty_per_mm_c': (0.01, 0.15),
}


class KontrolerRyzykaPIDAutoStrojenie(KontrolerRyzykaPID):

    def __init__(self, max_switches_per_day=12):
        super().__init__(max_switches_per_day=max_switches_per_day)

        self._strojenie_kierunek = {p: 1 for p in KROK_STROJENIA}
        self._strojenie_koszt_poprzedni = None
        self._strojenie_ostatnia_aktualizacja = None
        self._strojenie_moc_calka = 0.0     # Suma power_percent*dt/3600 w bieżącym okresie (%*h).
        self._strojenie_kara_snieg_s = 0.0
        self._strojenie_kara_lod_s = 0.0
        self._strojenie_kara_przegrzanie_s = 0.0
        # Log KAŻDEJ aktualizacji (jak historia_uczenia w nauka_kary*) - do
        # zakładki "Uczenie_adaptacyjne"/podobnej w Excelu.
        self.historia_strojenia = []
        self.historia_uczenia = self.historia_strojenia  # alias - żeby test_wszystkie_rownolegle.py (patrz getattr(kontroler,'historia_uczenia',None)) automatycznie zapisał też i tę historię, bez zmian w skrypcie testowym.

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
            # Koszt wzrósł względem poprzedniego okresu - zawracamy kierunek KAŻDEGO progu.
            for p in self._strojenie_kierunek:
                self._strojenie_kierunek[p] *= -1
        # Jeśli koszt spadł (albo to pierwsza aktualizacja) - kontynuujemy dotychczasowy kierunek.

        for p, krok in KROK_STROJENIA.items():
            wartosc = getattr(self, p) + self._strojenie_kierunek[p] * krok
            lo, hi = GRANICE_STROJENIA[p]
            setattr(self, p, min(max(wartosc, lo), hi))

        self.historia_strojenia.append({
            'timestamp': timestamp,
            'koszt': koszt,
            'moc_calka_pct_h': self._strojenie_moc_calka,
            'kary_h': kary_h,
            'hrt_on_precip': self.hrt_on_precip,
            'at_low_freeze': self.at_low_freeze,
            'hrt_on_dry': self.hrt_on_dry,
            'risk_snow_penalty_per_mm_c': self.risk_snow_penalty_per_mm_c,
        })

        self._strojenie_koszt_poprzedni = koszt
        self._strojenie_moc_calka = 0.0
        self._strojenie_kara_snieg_s = 0.0
        self._strojenie_kara_lod_s = 0.0
        self._strojenie_kara_przegrzanie_s = 0.0
        self._strojenie_ostatnia_aktualizacja = timestamp

    def risk_function_pid_auto(self, row_data):
        """Jak risk_function_pid, plus automatyczne strojenie progów setpointu -
        patrz nagłówek pliku. Zwraca (moc_procent, diagnostyka) jak risk_function_pid,
        diagnostyka dodatkowo z 'strojone_progi' (snapshot aktualnych wartości)."""
        power_percent, diagnostics = self.risk_function_pid(row_data)

        if diagnostics.get('faza') != 'autotest':
            timestamp = row_data['Timestamp']
            hrt_temp = float(row_data['HRT_temp_grzana'])
            dt = self._dt_sterowania

            self._strojenie_moc_calka += power_percent * dt / 3600.0
            # Estymator śniegu już zaktualizowany PRZEZ risk_function_pid (przez
            # _evaluate_risk_setpoint -> _estymuj_grubosc_sniegu_mm) - czytamy
            # WYNIK bezpośrednio z self, NIE wołamy estymatora drugi raz (to by
            # podwójnie doliczyło przyrost/ubytek w tym samym kroku).
            self._zarejestruj_kary_strojenia(hrt_temp, self._snieg_estymowany_mm, dt)
            self._aktualizuj_strojenie(timestamp)

            diagnostics = dict(diagnostics)
            diagnostics['strojone_progi'] = {
                'hrt_on_precip': self.hrt_on_precip,
                'at_low_freeze': self.at_low_freeze,
                'hrt_on_dry': self.hrt_on_dry,
                'risk_snow_penalty_per_mm_c': self.risk_snow_penalty_per_mm_c,
            }

        return power_percent, diagnostics
