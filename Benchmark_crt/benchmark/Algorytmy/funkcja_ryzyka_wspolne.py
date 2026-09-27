# Algorytmy/funkcja_ryzyka_wspolne.py
#
# Logika WSPÓLNA dla obu wersji funkcji ryzyka - binarnej
# (funkcja_ryzyka_binarna.py) i ciągłej PID (funkcja_ryzyka_pid.py): na
# podstawie pamięci + prognozy Kalmana wyznacza temperaturę zadaną (setpoint)
# dla szyny ogrzewanej. Same algorytmy (histereza vs PID wokół tego setpointu)
# są w osobnych plikach - tu jest tylko to, co obie wersje mają identyczne,
# żeby nie rozjeżdżały się przy zmianach.
#
# KontrolerRyzykaOpadBazowy (na końcu pliku) to WARIANT z prognozą OPADU
# (przewidywanie_opadow.py) - dziedziczą po niej *_opad.py: risk_function_opad,
# risk_function_pid_opad, fuzzy_ryzyko_*_opad (patrz rejestr_algorytmow.py).

import os
import sys

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmark/ (rodzic Algorytmy/)
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from rdzen_kontrolera import KontrolerBazowy, RowData, STEP_SECONDS, HORIZON_STEPS, TEMP_FORECAST_REFRESH_S
from przewidywanie_opadow import przewidywanie_opadow as PrzewidywanieOpadow

# ==========================================
# PARAMETRY FUNKCJI RYZYKA: pamięć + prognoza -> temperatura zadana
#
# BENCHMARK_CRT (2026-09-26, POPRAWKA na życzenie użytkownika: "marznący
# deszcz jest również tam w normie... one muszą zostać takie jakie były,
# zobacz sobie PDF z wartościami, tam są dla szyny zimnej czyli dla CRT"):
# hrt_on_precip/hrt_on_dry/RISK_FREEZING_RAIN_TARGET_C NIE są dowolnie
# dobranymi stałymi - to WPROST progi z normy LET-1 (Instrukcja eor,
# Tabela nr 5 "Progi temperaturowe ogrzewania opornic rozjazdu PRZY OPADACH"
# i Tabela nr 6 "...BEZ OPADÓW", wariant "dwa czujniki" - bo nasz system ma
# DWA czujniki: CRT="szyna nieogrzewana", HRT="szyna ogrzewana"):
#
#                          | CRT (szyna nieogrzewana) | HRT (szyna ogrzewana)
#   Tabela 5 (z opadem)    | załączenie +2 / wyłącz +3 | załączenie +4 / wyłącz +7
#   Tabela 6 (bez opadu)   | załączenie -5..-20 / wyłącz zał.+3 | załączenie +1 / wyłącz +3
#
# Wcześniejsza wersja tego pliku (w tej sesji) BŁĘDNIE przeskalowywała te
# wartości współczynnikiem R_CRT_HRT≈0,146 (zmierzony ΔCRT/ΔHRT pod pełną mocą
# grzania) - to poprawne podejście dla progów WYMYŚLONYCH na potrzeby tego
# projektu (np. kara za śnieg niżej), ale BŁĘDNE tutaj: norma LET-1 JUŻ
# podaje osobne, zwalidowane w praktyce wartości DLA CRT (kolumna "szyna
# nieogrzewana") - nie trzeba (i nie należy) ich przeliczać, tylko wziąć
# wprost z tabeli. Stąd teraz: hrt_on_precip=4.0->2.0 (Tab.5 CRT załączenie),
# RISK_FREEZING_RAIN_TARGET_C=7.0->3.0 (Tab.5 CRT wyłączenie), hrt_on_dry=
# 1.0->-5.0 (Tab.6 CRT załączenie, widełki -5..-20 - norma mówi wprost, że to
# zależy od lokalnych warunków klimatycznych zakładu, patrz pkt 2.4.17.1
# instrukcji - wybrany łagodniejszy kraniec -5°C, bo -10 kolidowałoby z
# priorytetem 3 (floor trigger=-8°C, wyżej w kaskadzie) dając ujemny błąd
# regulacji; -5°C zgadza się też z już istniejącym at_low_freeze=-5.0).
#
# BEZWZGLĘDNE limity bezpieczeństwa (floor, -10/-8/-12/-5°C) ZOSTAJĄ BEZ ZMIAN -
# to fizyka zamarzania/oblodzenia (progi materiałowe/normowe), nie z tabeli
# opadowej - obojętne, którym czujnikiem je mierzymy.
#
# RISK_SNOW_PENALTY_PER_MM_C/MAX_C (kara za ZALEGAJĄCY śnieg) NIE są z normy -
# to dodatek własny tego projektu (eskalacja celu ponad bazowy próg przy
# grubej pokrywie) - te DALEJ przeskalowane R_CRT_HRT, bo nie mają odpowiednika
# w tabelach normy.
# ==========================================
R_CRT_HRT = 0.146   # Zmierzony współczynnik ΔCRT/ΔHRT pod pełną mocą - używany WYŁĄCZNIE tam, gdzie norma nie daje gotowej wartości dla CRT (patrz wyżej).

RISK_FREEZING_RAIN_TARGET_C = 3.0        # BENCHMARK_CRT: z normy LET-1, Tabela 5, CRT (szyna nieogrzewana), "wyłączenie" (było 7.0 = wartość HRT z tej samej tabeli).
RISK_HRT_ABSOLUTE_FLOOR_C = -10.0        # Bezwzględny dolny limit temperatury szyny ogrzewanej - NIEZMIENIONY (limit bezpieczeństwa, nie z tabeli opadowej).
RISK_HRT_FLOOR_TRIGGER_C = -8.0          # Próg (z zapasem 2°C) uruchamiający ochronę przed spadkiem do floora - NIEZMIENIONY.
RISK_HRT_FLOOR_TARGET_C = -5.0           # Cel grzania w trybie ochrony przed floorem - NIEZMIENIONY (zapas bezpieczeństwa, nie z tabeli opadowej).
RISK_FORECAST_COLD_TRIGGER_C = -12.0     # Gdy prognoza AT (Kalman) pokazuje taki chłód w horyzoncie - grzejemy wyprzedzająco - NIEZMIENIONY.
RISK_NEAR_TERM_STEPS = 2                 # Ile najbliższych próbek prognozy (2 x 15 min = 30 min) liczymy jako "wkrótce".

# BENCHMARK_CRT (2026-09-28, na życzenie użytkownika - "mocniejsze i z
# wyprzedzeniem reagowanie na pogodę... opady"): próg i horyzont dla
# WYPRZEDZAJĄCEGO grzania, gdy prognoza opadu (przewidywanie_opadow.py)
# pokazuje NADCHODZĄCY front, zanim opad faktycznie się zacznie - patrz
# KontrolerRyzykaBazowy._prognoza_nadchodzacego_frontu i priorytet 2b w
# _evaluate_risk_setpoint. Ten sam horyzont co RISK_NEAR_TERM_STEPS/
# RISK_OPAD_HORYZONT_KROKOW (2 x 15 min = 30 min), dla spójności z resztą kaskady.
RISK_OPAD_WYPRZEDZENIE_KROKOW = 2
RISK_OPAD_WYPRZEDZENIE_TEMP_PROG_C = 2.0  # AT LUB CRT poniżej tego progu - dopiero wtedy nadchodzący opad jest ryzykiem oblodzenia (margines nad progiem marznącego deszczu 1.0°C).

RISK_SNOW_LINGER_THRESHOLD_MM = 5.0      # Powyżej tylu mm zalegającego śniegu (nawet gdy opad ustał) dalej aktywnie topimy - NIEZMIENIONY (to próg na ILOŚCI śniegu, nie na temperaturze).
RISK_SNOW_PENALTY_PER_MM_C = round(0.05 * R_CRT_HRT, 5)     # BENCHMARK_CRT: 0.05 -> 0.0073 °C/mm - dodatek własny projektu (nie z normy), przeskalowany R_CRT_HRT.
RISK_SNOW_PENALTY_MAX_C = round(6.0 * R_CRT_HRT, 2)         # BENCHMARK_CRT: 6.0 -> 0.88 - jw., dodatek własny projektu.

# ==========================================
# WAGI METRYKI 'kara_bezpieczeństwa' (symulacja_fizyczna.uruchom_kontroler) -
# CELOWO ODDZIELONE od stałych sterujących wyżej, mimo że nominalnie mają tę
# samą wartość co RISK_SNOW_PENALTY_PER_MM_C. Kara bezpieczeństwa jest metryką
# POROZNAWCZĄ liczoną z GROUND-TRUTH przebiegu (patrz notatki/kara_bezpieczenstwa.md),
# nie wejściem do żadnej decyzji sterującej - to rozdzielenie pozwala testować
# wrażliwość RANKINGU algorytmów na dobór tych wag (patrz KARA_WAGI_SCENARIUSZE
# niżej) WYŁĄCZNIE post-hoc, z JUŻ zasymulowanej trajektorii, bez ponownego
# odpalania fizyki/sterowania - gdyby te wagi były tymi samymi stałymi co wyżej,
# ich zmiana zmieniałaby też zachowanie funkcji ryzyka (RISK_SNOW_PENALTY_PER_MM_C
# steruje celem grzania przy zalegającym śniegu), co wymagałoby pełnej ponownej
# symulacji dla każdego scenariusza wag - dokładnie tego, czego ten podział unika.
KARA_WAGA_SNIEG_C_PER_MM = 0.05  # BENCHMARK_CRT: NIE przeskalowane przez R_CRT_HRT (celowo odłączone od
                                  # RISK_SNOW_PENALTY_PER_MM_C, patrz wyżej) - kara bezpieczeństwa mierzy
                                  # PRAWDZIWY, fizyczny wynik (ile śniegu naprawdę zalega), niezależnie od
                                  # tego, jakim czujnikiem sterownik podejmował decyzję - musi zostać na tej
                                  # samej skali co w Benchmark/benchmark, żeby wyniki były porównywalne.
KARA_WAGA_MROZ_DESZCZ = 1.0              # Waga deficytu marznącego deszczu (°C) w sumie kary - baza = 1.0 (bez ważenia).
KARA_WAGA_FLOOR = 1.0                    # Waga deficytu poniżej floora -10°C w sumie kary - baza = 1.0 (bez ważenia).

# Scenariusze do analizy wrażliwości wag kary bezpieczeństwa: każdy zaburza
# JEDNĄ z trzech wag o +/-50% względem nominalnej (pozostałe dwie bez zmian) -
# sprawdza, czy RANKING algorytmów wg kary bezpieczeństwa jest stabilny
# niezależnie od dokładnego doboru tych (z natury nieco arbitralnych) wag.
# Liczone w JEDNYM przebiegu symulacji razem z wariantem nominalnym (patrz
# symulacja_fizyczna.uruchom_kontroler) - to tylko dodatkowe sumowanie po
# już policzonych składowych (snow_excess_mm/marznacy_deszcz_deficyt_c/
# floor_deficyt_c), więc ZERO dodatkowego kosztu ponownej symulacji fizyki.
KARA_WAGI_SCENARIUSZE = {
    # etykieta:            (mnożnik_snieg, mnożnik_mroz, mnożnik_floor)
    'snieg_x0.5':           (0.5, 1.0, 1.0),
    'snieg_x2':             (2.0, 1.0, 1.0),
    'mroz_x0.5':            (1.0, 0.5, 1.0),
    'mroz_x2':              (1.0, 2.0, 1.0),
    'floor_x0.5':           (1.0, 1.0, 0.5),
    'floor_x2':             (1.0, 1.0, 2.0),
}


class KontrolerRyzykaBazowy(KontrolerBazowy):
    """
    Nie jest samodzielnym algorytmem (brak wpisu w rejestr_algorytmow.py) -
    dziedziczą po niej funkcja_ryzyka_binarna.KontrolerRyzykaBinarny i
    funkcja_ryzyka_pid.KontrolerRyzykaPID.
    """

    def __init__(self):
        super().__init__()

        # Progi z normy LET-1 (Instrukcja eor, Tabela nr 5 i 6, wariant "dwa
        # czujniki") potrzebne w _evaluate_risk_setpoint. BENCHMARK_CRT:
        # WPROST wartości z kolumny CRT ("szyna nieogrzewana") tych samych
        # tabel - NIE przeliczane żadnym współczynnikiem, norma już je podaje
        # gotowe - patrz nagłówek pliku po pełne uzasadnienie i tabelę.
        self.hrt_on_precip = 2.0    # BENCHMARK_CRT: z normy, Tabela nr 5, CRT załączenie przy opadach (było 4.0 = wartość HRT z tej samej tabeli).
        self.at_low_freeze = -5.0   # Suchy mróz dolna granica: -5°C (Tabela nr 6) - NIEZMIENIONY, próg na AT, nie na CRT/HRT.
        self.hrt_on_dry = -5.0      # BENCHMARK_CRT: z normy, Tabela nr 6, CRT załączenie bez opadów (widełki -5..-20 - wybrany łagodniejszy kraniec, bo -10 kolidowałoby z priorytetem 3 (floor trigger=-8°C, wyżej w kaskadzie) i dawałoby ujemny błąd regulacji; -5°C zgadza się też z już istniejącym at_low_freeze=-5.0 - było 1.0 = wartość HRT z tej samej tabeli).
        # Kara za zalegający śnieg (patrz priorytet 2 w _evaluate_risk_setpoint) -
        # PROMOWANA do atrybutu instancji (domyślnie = stała modułowa, zero zmiany
        # zachowania dla wszystkich dotychczasowych algorytmów) wyłącznie po to,
        # żeby funkcja_ryzyka_pid_auto_strojenie.KontrolerRyzykaPIDAutoStrojenie
        # mogła ją bezpiecznie stroić PER INSTANCJA, bez ryzyka mutowania
        # WSPÓLNEJ stałej modułowej (co zepsułoby WSZYSTKIE inne kontrolery w
        # tym samym procesie roboczym).
        self.risk_snow_penalty_per_mm_c = RISK_SNOW_PENALTY_PER_MM_C
        # _ostatnia_moc_autotestu i _autotest_startowy przeniesione do
        # rdzen_kontrolera.KontrolerBazowy (żeby były dostępne dla każdego
        # kontrolera, nie tylko rodziny funkcji ryzyka) - dziedziczone stąd bez zmian.

        # BENCHMARK_CRT (2026-09-28, na życzenie użytkownika - "mocniejsze i z
        # wyprzedzeniem reagowanie na pogodę... opady"): prognoza opadu
        # (przewidywanie_opadow.py) PRZENIESIONA tu z KontrolerRyzykaOpadBazowy
        # (niżej w tym pliku) - dostępna teraz dla WSZYSTKICH algorytmów rodziny
        # funkcji ryzyka, nie tylko wariantów *_opad. Wariant *_opad zostaje
        # jako ten z DODATKOWYM mechanizmem zwalniania z grzania
        # (_front_ustepuje) - patrz niżej.
        self._opad_forecaster = PrzewidywanieOpadow(persistence_steps=1)

    def _prognoza_intensywnosci_opadu(self, row_data, precip_total_mm):
        """
        Woła przewidywanie_opadow.predict_winter_precipitation z danymi, które
        kontroler już i tak ma: prognoza AT z Kalmana (self.temperature_prediction(),
        ten sam horyzont 8x15min co przewidywanie_opadow oczekuje), ostatni
        odczyt opadu, punkt rosy i wiatr z bieżącej próbki (pola 'PUNKT_ROSY_C'/
        'WIATR_M_S' - patrz symulacja_fizyczna.uruchom_kontroler). Zwraca tablicę
        8 intensywności (0-3) na najbliższe 2h.
        """
        future_at = self.temperature_prediction()
        if not future_at:
            return [0] * HORIZON_STEPS
        current_dp = float(row_data.get('PUNKT_ROSY_C', row_data['AT_temp_powietrza']))
        current_wind = float(row_data.get('WIATR_M_S', 3.0))
        return self._opad_forecaster.predict_winter_precipitation(
            [precip_total_mm], future_at, current_dp, current_wind,
        )

    def _prognoza_nadchodzacego_frontu(self, row_data, precip_total_mm):
        """
        BENCHMARK_CRT (2026-09-28): odwrotność _front_ustepuje - zwraca True,
        gdy prognoza opadu (przewidywanie_opadow) pokazuje intensywność > 0 w
        najbliższych RISK_OPAD_WYPRZEDZENIE_KROKOW krokach (~30 min), czyli
        front dopiero NADCHODZI. Używane w _evaluate_risk_setpoint, żeby
        zacząć grzać z wyprzedzeniem, ZANIM opad faktycznie się zacznie -
        realizuje "wyprzedzające reagowanie na opady" dla WSZYSTKICH
        algorytmów (nie tylko *_opad, który dokłada odwrotny mechanizm -
        zwalnianie z grzania, gdy front kończy się).
        """
        prognoza = self._prognoza_intensywnosci_opadu(row_data, precip_total_mm)
        self._dodaj_flopy(160)  # przewidywanie_opadow: ~20 FLOPs/krok x 8 kroków horyzontu.
        return any(int(v) > 0 for v in prognoza[:RISK_OPAD_WYPRZEDZENIE_KROKOW])

    def _evaluate_risk_setpoint(self, row_data, dodatkowa_ucieczka_sniegu=None):
        """
        Wspólna logika dla risk_function (binarna) i risk_function_pid (ciągła):
        na podstawie bieżącej próbki pogodowej, pamięci (self.sensor_history) i
        prognozy Kalmana temperatury SZYNY (self.rail_temperature_prediction() -
        prognoza CRT, a nie tylko powietrza) wyznacza temperaturę zadaną (setpoint)
        dla szyny ogrzewanej oraz czy w ogóle trzeba grzać.

        Priorytety decyzji (od najważniejszego):
          1) Marznący deszcz - grzejemy BEZWARUNKOWO, niezależnie od prognozy. To zbyt
             niebezpieczne, żeby czekać - gołoledź może powstać natychmiast.
          2) Opad śniegu LUB zalegająca pokrywa (RISK_SNOW_LINGER_THRESHOLD_MM) - z
             automatu MUSIMY ją wytapiać, CHYBA że FIZYCZNA prognoza CRT
             (crt_transmittance_prediction, ze znanej transmitancji AT->CRT -
             patrz rdzen_kontrolera.py) pokazuje, że w najbliższych ~30 minutach
             (RISK_NEAR_TERM_STEPS próbek co 15 min) CRT samo wejdzie powyżej 0°C, a
             pokrywa jest jeszcze cienka - wtedy nie ma sensu grzać na siłę.
             IM WIĘCEJ śniegu zalega, TYM WYŻSZA temperatura zadana (kara za zaleganie
             - więcej śniegu = więcej energii potrzeba, żeby go porządnie wytopić;
             patrz RISK_SNOW_PENALTY_PER_MM_C / RISK_SNOW_PENALTY_MAX_C).
          3) BENCHMARK_CRT: ochrona przed spadkiem CRT (szyna zimna, GŁÓWNY
             wyznacznik w tym folderze) poniżej -10°C - uwzględniając też
             fizyczną prognozę CRT: jeśli transmitancja AT->CRT przewiduje bardzo
             niską temperaturę w horyzoncie 2h, grzejemy z niewielkim
             wyprzedzeniem, żeby zdążyć zanim faktycznie dojdzie do spadku.
          4) Standardowy suchy mróz wg progów LET-1 (jak w histereza_let1.py).

        Grubość zalegającego śniegu (mm) NIE jest czytana z row_data (to pole,
        'SNIEG_GRUBOSC_MM', niesie PRAWDZIWĄ wartość z modelu fizycznego
        symulacji i służy WYŁĄCZNIE bezpiecznikowi/referencji w
        symulacja_fizyczna.py - kontroler nie ma do niej dostępu, dokładnie
        jak prawdziwy sterownik) - liczona samodzielnie przez
        self._estymuj_grubosc_sniegu_mm (bilans: przyrost z odczytu
        intensywności opadu śniegu, ubytek z szacowanego tempa topnienia przy
        HRT>0°C - patrz rdzen_kontrolera.KontrolerBazowy._estymuj_grubosc_sniegu_mm).

        dodatkowa_ucieczka_sniegu: opcjonalny callable(row_data, snow_depth_mm) ->
            (bool, opis_albo_None), wywoływany TYLKO w gałęzi śniegu i TYLKO gdy
            podstawowy warunek warmup_soon (prognoza CRT) NIE zwolnił już z
            grzania - pozwala podklasom (patrz KontrolerRyzykaOpadBazowy poniżej)
            dołożyć DODATKOWY warunek zwolnienia z grzania (np. prognoza opadu
            pokazująca koniec frontu), bez kopiowania całej tej metody. Domyślnie
            None -> zachowanie DOKŁADNIE jak przed dodaniem tego parametru.

        Zwraca: (target_temperature, need_heat, reason, forecast_min_c, warmup_soon)
        """
        timestamp = row_data['Timestamp']
        at_temp = float(row_data['AT_temp_powietrza'])
        crt_temp = float(row_data['CRT_temp_niegrzana'])
        hrt_temp = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        rh_humidity = float(row_data['RH_wilgotnosc_wzgledna'])
        snow_depth_mm = self._estymuj_grubosc_sniegu_mm(row_data)

        is_raining = precip > 0.0001
        is_snowing = snow > 0.0001
        is_freezing_rain = is_raining and (crt_temp <= 1.0 or at_temp <= 1.0)

        # --- PAMIĘĆ: dopisujemy próbkę do tej samej historii, z której korzysta
        # temperature_prediction/rail_temperature_prediction (Kalman) i autotest
        # - "pamięta trochę tej pogody". ---
        reading = RowData()
        reading.timestamp = timestamp
        reading.crt_temp = crt_temp
        reading.hrt_temp = hrt_temp
        reading.at_temp = at_temp
        reading.precip = precip
        reading.snow = snow
        reading.rh_humidity = rh_humidity
        self._append_sensor_history(reading)

        # --- PROGNOZA: 8 x 15 min (2h) do przodu. ---
        # Składowa pogodowa (CRT) zawsze z filtru Kalmana (statystyka z historii -
        # nie mamy fizycznego modelu POGODY). Jeśli autotest zidentyfikował
        # grzałkę (self._model_zidentyfikowany), DOKŁADAMY do tego fizyczną
        # prognozę zanikającego ciepła z już wydanych komend mocy (cyfrowy
        # bliźniak - patrz KontrolerBazowy._prognoza_zanikania_ciepla) - to
        # realnie poprawia "warmup_soon"/"forecast_min_c" tam, gdzie w rurze
        # zostało jeszcze ciepło z niedawnego grzania, którego sama prognoza CRT
        # (z definicji NIE uwzględniająca grzania) nigdy by nie zobaczyła. Bez
        # zidentyfikowanego modelu zachowanie jest DOKŁADNIE jak przed tą funkcją.
        # BENCHMARK_CRT (2026-09-26): prognoza CRT liczona FIZYCZNIE, ze
        # znanej transmitancji AT->CRT (crt_transmittance_prediction, patrz
        # rdzen_kontrolera.py), NIE statystycznym Kalmanem jak w oryginale
        # (rail_temperature_prediction).
        #
        # POPRAWKA 2026-09-28 (na życzenie użytkownika): CRT NIE jest już
        # modelowane jako całkowicie odcięte od grzania - reaguje słabo i
        # wolno (patrz K_H_CRT_KONTROLER/T1_H_CRT_KONTROLER w
        # rdzen_kontrolera.py oraz K_H_CRT/T1_H_CRT w symulacja_fizyczna.py -
        # to ZAŁOŻENIE, nie pomiar, identyfikacja_crt_miso.py nie dała
        # czystego sygnału). Dlatego - dokładnie jak w oryginalnym
        # Benchmark/benchmark dla prognozy HRT - do fizycznej prognozy
        # pogodowej DOKŁADAMY prognozę resztkowego (słabego/wolnego) wpływu
        # JUŻ wydanych komend mocy (_prognoza_zanikania_ciepla_crt). Dostępne
        # tylko dla algorytmów, które w ogóle wołają _krok_modelu (rodzina PID/
        # ADRC/kaskada) - warianty binarne nie mają cyfrowego bliźniaka wcale,
        # dokładnie jak dziś dla HRT.
        forecast_crt_pogoda = self.crt_transmittance_prediction()
        if getattr(self, '_model_crt_zbudowany', False) and forecast_crt_pogoda:
            cached = getattr(self, '_model_crt_forecast_cache', None)
            cached_time = getattr(self, '_model_crt_forecast_cache_time', None)
            if (cached is not None and cached_time is not None
                    and (timestamp - cached_time).total_seconds() < TEMP_FORECAST_REFRESH_S):
                zanikanie_na_siatce = cached
            else:
                krok_siatki_w_probkach = max(int(round(STEP_SECONDS / self._dt_sterowania)), 1)
                liczba_krokow_prognozy = int(round(HORIZON_STEPS * STEP_SECONDS / self._dt_sterowania))
                zanikanie = self._prognoza_zanikania_ciepla_crt(liczba_krokow_prognozy)
                zanikanie_na_siatce = zanikanie[krok_siatki_w_probkach - 1::krok_siatki_w_probkach][:len(forecast_crt_pogoda)]
                self._model_crt_forecast_cache = zanikanie_na_siatce
                self._model_crt_forecast_cache_time = timestamp
            forecast_crt = [c + h for c, h in zip(forecast_crt_pogoda, zanikanie_na_siatce)]
        else:
            forecast_crt = forecast_crt_pogoda

        near_term = forecast_crt[:RISK_NEAR_TERM_STEPS] if forecast_crt else []
        warmup_soon = any(v > 0.0 for v in near_term)
        forecast_min_c = min(forecast_crt) if forecast_crt else crt_temp

        # --- WYZNACZENIE TEMPERATURY ZADANEJ I POTRZEBY GRZANIA (priorytety 1-4).
        # BENCHMARK_CRT: CRT jest teraz głównym wyznacznikiem - "target_temperature"
        # niżej jest odtąd celem dla CRT (nie HRT), a ochrona floora (priorytet 3)
        # wyzwala się z CRT, nie z HRT (patrz też każdy plik wykonawczy
        # risk_function*/fuzzy_ryzyko_*, gdzie blad_T = target - CRT). ---
        if is_freezing_rain:
            need_heat = True
            target_temperature = RISK_FREEZING_RAIN_TARGET_C
            reason = 'marznący deszcz - grzanie bezwarunkowe'
        elif is_snowing or snow_depth_mm > RISK_SNOW_LINGER_THRESHOLD_MM:
            if warmup_soon and snow_depth_mm <= RISK_SNOW_LINGER_THRESHOLD_MM:
                need_heat = False
                target_temperature = crt_temp
                reason = 'śnieg, ale prognoza szyny (CRT) pokazuje ocieplenie w ~30 min - czekamy na naturalny zanik'
            else:
                ucieczka, powod_ucieczki = (False, None)
                if dodatkowa_ucieczka_sniegu is not None:
                    ucieczka, powod_ucieczki = dodatkowa_ucieczka_sniegu(row_data, snow_depth_mm)
                if ucieczka:
                    need_heat = False
                    target_temperature = crt_temp
                    reason = powod_ucieczki
                else:
                    need_heat = True
                    penalty = min(snow_depth_mm * self.risk_snow_penalty_per_mm_c, RISK_SNOW_PENALTY_MAX_C)
                    target_temperature = self.hrt_on_precip + penalty
                    if snow_depth_mm > RISK_SNOW_LINGER_THRESHOLD_MM:
                        reason = f'zalegający śnieg ({snow_depth_mm:.0f} mm) - cel podniesiony o {penalty:.1f}°C, żeby go porządnie wytopić'
                    else:
                        reason = 'opad śniegu do wytopienia'
        elif ((at_temp <= RISK_OPAD_WYPRZEDZENIE_TEMP_PROG_C or crt_temp <= RISK_OPAD_WYPRZEDZENIE_TEMP_PROG_C)
                and self._prognoza_nadchodzacego_frontu(row_data, precip + snow)):
            # BENCHMARK_CRT (2026-09-28): priorytet 2b - NIE pada jeszcze, ale
            # prognoza opadu (przewidywanie_opadow) pokazuje nadchodzący front
            # w ~30 min, a temperatura jest już blisko zera - zaczynamy grzać
            # PRZED opadem, zamiast dopiero gdy zacznie faktycznie padać
            # (priorytet 2 wyżej). Patrz _prognoza_nadchodzacego_frontu.
            need_heat = True
            target_temperature = self.hrt_on_precip
            reason = 'prognoza opadu pokazuje nadchodzący front w ~30 min - grzanie wyprzedzające'
        elif crt_temp <= RISK_HRT_FLOOR_TRIGGER_C or forecast_min_c <= RISK_FORECAST_COLD_TRIGGER_C:
            need_heat = True
            target_temperature = RISK_HRT_FLOOR_TARGET_C
            reason = f'ochrona przed spadkiem CRT poniżej {RISK_HRT_ABSOLUTE_FLOOR_C:.0f}°C (bieżąco lub wg prognozy transmitancji)'
        elif at_temp <= self.at_low_freeze:
            need_heat = True
            target_temperature = self.hrt_on_dry
            reason = 'suchy mróz'
        else:
            need_heat = False
            target_temperature = crt_temp
            reason = 'brak zagrożenia'

        self._dodaj_flopy(20)  # Priorytety 1-4 (porównania progów, kara za śnieg).
        return target_temperature, need_heat, reason, forecast_min_c, warmup_soon

    def _poziom_ryzyka_funkcji(self, reason: str) -> int:
        """
        Numeryczny poziom ryzyka (0-4) na podstawie priorytetu decyzji, który
        WŁAŚNIE podjęła _evaluate_risk_setpoint (patrz tam pełny opis
        priorytetów 1-4) - identyfikowany przez tekst `reason`, żeby nie
        duplikować logiki progów. Używane WYŁĄCZNIE przez
        silniki_fuzzy.wnioskowanie_fl2v2 (dynamiczny próg "lodowato" w
        fuzzy_ryzyko_2v2/fuzzy_ryzyko_2v2_opad - patrz
        notatki/algorytmy/fuzzy_logic_2v2.md). Wołane TYLKO gdy need_heat=True
        (4 gałęzie priorytetów 1-4), więc nie trzeba obsługiwać "brak zagrożenia".

        Skala (rosnąco wg powagi): 1=suchy mróz, 2=ochrona przed floor/prognoza
        mrozu, 3=śnieg/zalegająca pokrywa, 4=marznący deszcz (najwyższe
        zagrożenie - grzanie bezwarunkowe).
        """
        if reason.startswith('marznący deszcz'):
            return 4
        if (reason.startswith('zalegający śnieg') or reason == 'opad śniegu do wytopienia'
                or reason.startswith('prognoza opadu pokazuje nadchodzący front')):
            return 3
        if reason.startswith('ochrona przed spadkiem CRT'):
            return 2
        if reason == 'suchy mróz':
            return 1
        return 0


# ==========================================
# WARIANT Z PROGNOZĄ OPADU (przewidywanie_opadow.py)
# ==========================================
RISK_OPAD_PROGNOZA_CIENKA_MM = 10.0  # Cienka pokrywa (<= tyle mm): jeśli prognoza opadu pokazuje rychły koniec
                                      # frontu, ufamy bezwładności cieplnej/naturalnemu ociepleniu zamiast grzać
                                      # na zapas (patrz KontrolerRyzykaOpadBazowy._front_ustepuje).
RISK_OPAD_HORYZONT_KROKOW = 2        # Ile najbliższych kroków prognozy opadu (2 x 15 min = 30 min) sprawdzamy,
                                      # czy front już ustępuje - ta sama szerokość okna co RISK_NEAR_TERM_STEPS.


class KontrolerRyzykaOpadBazowy(KontrolerRyzykaBazowy):
    """
    Jak KontrolerRyzykaBazowy (która od 2026-09-28 ma już DOSTĘP do prognozy
    opadu dla WSZYSTKICH algorytmów - patrz _opad_forecaster/
    _prognoza_intensywnosci_opadu/_prognoza_nadchodzacego_frontu tam), ale
    dokłada DODATKOWY warunek zwalniający z grzania w gałęzi śniegu: jeśli
    prognoza pokazuje, że front opadowy kończy się w najbliższych
    RISK_OPAD_HORYZONT_KROKOW krokach, a zalegająca pokrywa jest cienka
    (<= RISK_OPAD_PROGNOZA_CIENKA_MM), NIE grzejemy na zapas - ufamy, że
    bezwładność cieplna/naturalne ocieplenie dokończy topienie. To przesłanka
    NIEZALEŻNA od prognozy CRT (warmup_soon) - łapie sytuacje, gdy front mija,
    ale sama szyna jeszcze się nie zdążyła ocieplić.

    Różnica względem bazowej klasy jest więc TERAZ tylko w tym mechanizmie
    zwalniania (_front_ustepuje) - "zwykłe" algorytmy od 2026-09-28 mają już
    wyprzedzające WŁĄCZANIE grzania (priorytet 2b w _evaluate_risk_setpoint),
    a *_opad dokłada do tego jeszcze wyprzedzające WYŁĄCZANIE.

    Nie jest samodzielnym algorytmem (brak wpisu w rejestr_algorytmow.py) -
    dziedziczą po niej *_opad.py: funkcja_ryzyka_binarna_opad.py,
    funkcja_ryzyka_pid_opad.py, funkcja_fuzzy_ryzyko_*_opad.py.
    """

    def _front_ustepuje(self, row_data, snow_depth_mm):
        """
        callable zgodny z parametrem dodatkowa_ucieczka_sniegu w
        _evaluate_risk_setpoint - zwraca (True, opis) tylko gdy pokrywa jest
        cienka I prognoza opadu nie widzi już żadnej intensywności w
        najbliższych RISK_OPAD_HORYZONT_KROKOW krokach.
        """
        if snow_depth_mm > RISK_OPAD_PROGNOZA_CIENKA_MM:
            return False, None

        precip_total_mm = float(row_data['PRECIP_opad']) + float(row_data['SNOW_snieg'])
        prognoza = self._prognoza_intensywnosci_opadu(row_data, precip_total_mm)
        self._dodaj_flopy(160)  # przewidywanie_opadow: ~20 FLOPs/krok x 8 kroków horyzontu.
        front_ustepuje = not any(int(v) > 0 for v in prognoza[:RISK_OPAD_HORYZONT_KROKOW])
        if not front_ustepuje:
            return False, None

        return True, (f'prognoza opadu (przewidywanie_opadow) pokazuje koniec frontu w ~30 min, '
                       f'cienka pokrywa ({snow_depth_mm:.0f} mm) - ufamy bezwładności zamiast grzać na zapas')

    def _evaluate_risk_setpoint_z_opadem(self, row_data):
        """Jak _evaluate_risk_setpoint, plus dodatkowa ucieczka z grzania wg prognozy opadu (patrz wyżej)."""
        return self._evaluate_risk_setpoint(row_data, dodatkowa_ucieczka_sniegu=self._front_ustepuje)
