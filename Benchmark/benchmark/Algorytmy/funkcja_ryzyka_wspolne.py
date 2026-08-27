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
# ==========================================
RISK_FREEZING_RAIN_TARGET_C = 7.0        # Cel HRT przy marznącym deszczu - najwyższy priorytet, grzejemy zawsze.
RISK_HRT_ABSOLUTE_FLOOR_C = -10.0        # Bezwzględny dolny limit temperatury szyny ogrzewanej.
RISK_HRT_FLOOR_TRIGGER_C = -8.0          # Próg (z zapasem 2°C) uruchamiający ochronę przed spadkiem do floora.
RISK_HRT_FLOOR_TARGET_C = -5.0           # Cel grzania w trybie ochrony przed floorem (bezpieczny zapas do -10°C).
RISK_FORECAST_COLD_TRIGGER_C = -12.0     # Gdy prognoza AT (Kalman) pokazuje taki chłód w horyzoncie - grzejemy wyprzedzająco.
RISK_NEAR_TERM_STEPS = 2                 # Ile najbliższych próbek prognozy (2 x 15 min = 30 min) liczymy jako "wkrótce".

RISK_SNOW_LINGER_THRESHOLD_MM = 5.0      # Powyżej tylu mm zalegającego śniegu (nawet gdy opad ustał) dalej aktywnie topimy.
RISK_SNOW_PENALTY_PER_MM_C = 0.05        # O ile °C podnosimy cel za każdy mm zalegającego śniegu - im więcej śniegu, tym więcej trzeba wytopić.
RISK_SNOW_PENALTY_MAX_C = 6.0            # Górny limit dodatku z tytułu kary za śnieg (cel nie rośnie w nieskończoność).


class KontrolerRyzykaBazowy(KontrolerBazowy):
    """
    Nie jest samodzielnym algorytmem (brak wpisu w rejestr_algorytmow.py) -
    dziedziczą po niej funkcja_ryzyka_binarna.KontrolerRyzykaBinarny i
    funkcja_ryzyka_pid.KontrolerRyzykaPID.
    """

    def __init__(self):
        super().__init__()

        # Progi LET-1 potrzebne w _evaluate_risk_setpoint (Tabela nr 5 i 6,
        # identyczne wartości jak w histereza_let1.KontrolerHisterezaLET1).
        self.hrt_on_precip = 4.0    # HRT załączenie przy opadach: +4°C (Tabela nr 5)
        self.at_low_freeze = -5.0   # Suchy mróz dolna granica: -5°C (Tabela nr 6)
        self.hrt_on_dry = 1.0       # HRT załączenie bez opadów: +1°C (Tabela nr 6)
        # _ostatnia_moc_autotestu i _autotest_startowy przeniesione do
        # rdzen_kontrolera.KontrolerBazowy (żeby były dostępne dla każdego
        # kontrolera, nie tylko rodziny funkcji ryzyka) - dziedziczone stąd bez zmian.

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
             automatu MUSIMY ją wytapiać, CHYBA że prognoza Kalmana temperatury szyny
             (rail_temperature_prediction) pokazuje, że w najbliższych ~30 minutach
             (RISK_NEAR_TERM_STEPS próbek co 15 min) CRT samo wejdzie powyżej 0°C, a
             pokrywa jest jeszcze cienka - wtedy nie ma sensu grzać na siłę.
             IM WIĘCEJ śniegu zalega, TYM WYŻSZA temperatura zadana (kara za zaleganie
             - więcej śniegu = więcej energii potrzeba, żeby go porządnie wytopić;
             patrz RISK_SNOW_PENALTY_PER_MM_C / RISK_SNOW_PENALTY_MAX_C).
          3) Ochrona przed spadkiem temperatury szyny ogrzewanej poniżej -10°C -
             uwzględniając też prognozę CRT: jeśli Kalman przewiduje bardzo niską
             temperaturę szyny w horyzoncie 2h, grzejemy z niewielkim wyprzedzeniem,
             żeby zdążyć zanim faktycznie dojdzie do spadku (obiekt ma bezwładność
             i opóźnienie transportowe rzędu ~20 minut - patrz autotest/L_H).
          4) Standardowy suchy mróz wg progów LET-1 (jak w histereza_let1.py).

        Oczekuje opcjonalnego pola 'SNIEG_GRUBOSC_MM' w row_data (aktualna grubość
        zalegającego śniegu na szynie, mm) - jeśli go brak, przyjmujemy 0.0 (brak
        informacji o zaleganiu, zachowanie jak poprzednio).

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
        snow_depth_mm = float(row_data.get('SNIEG_GRUBOSC_MM', 0.0))

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
        forecast_crt = self.rail_temperature_prediction()
        if self._model_zidentyfikowany and forecast_crt:
            # Cache: _prognoza_zanikania_ciepla robi pętlę o długości HORIZON_STEPS*
            # STEP_SECONDS (7200 kroków) - wołanie jej co sekundę byłoby równie
            # zabójcze jak nieocache'owana prognoza Kalmana, więc odświeżamy z tą
            # samą częstotliwością (TEMP_FORECAST_REFRESH_S).
            cached = self._model_forecast_cache
            cached_time = self._model_forecast_cache_time
            if (cached is not None and cached_time is not None
                    and (timestamp - cached_time).total_seconds() < TEMP_FORECAST_REFRESH_S):
                zanikanie_na_siatce = cached
            else:
                # _prognoza_zanikania_ciepla liczy w KROKACH MODELU (każdy krok =
                # self._dt_sterowania sekund, nie zawsze 1s - patrz _autotest_startowy),
                # więc żeby pokryć HORIZON_STEPS*STEP_SECONDS sekund realnego czasu,
                # trzeba przeliczyć liczbę kroków i szerokość siatki (co ile kroków
                # modelu przypada jeden punkt siatki 15-minutowej) przez dt_sterowania.
                krok_siatki_w_probkach = max(int(round(STEP_SECONDS / self._dt_sterowania)), 1)
                liczba_krokow_prognozy = int(round(HORIZON_STEPS * STEP_SECONDS / self._dt_sterowania))
                zanikanie = self._prognoza_zanikania_ciepla(liczba_krokow_prognozy)
                zanikanie_na_siatce = zanikanie[krok_siatki_w_probkach - 1::krok_siatki_w_probkach][:len(forecast_crt)]
                self._model_forecast_cache = zanikanie_na_siatce
                self._model_forecast_cache_time = timestamp
            forecast_hrt = [c + h for c, h in zip(forecast_crt, zanikanie_na_siatce)]
        else:
            forecast_hrt = forecast_crt

        near_term = forecast_hrt[:RISK_NEAR_TERM_STEPS] if forecast_hrt else []
        warmup_soon = any(v > 0.0 for v in near_term)
        forecast_min_c = min(forecast_hrt) if forecast_hrt else crt_temp

        # --- WYZNACZENIE TEMPERATURY ZADANEJ I POTRZEBY GRZANIA (priorytety 1-4). ---
        if is_freezing_rain:
            need_heat = True
            target_temperature = RISK_FREEZING_RAIN_TARGET_C
            reason = 'marznący deszcz - grzanie bezwarunkowe'
        elif is_snowing or snow_depth_mm > RISK_SNOW_LINGER_THRESHOLD_MM:
            if warmup_soon and snow_depth_mm <= RISK_SNOW_LINGER_THRESHOLD_MM:
                need_heat = False
                target_temperature = hrt_temp
                reason = 'śnieg, ale prognoza szyny (CRT) pokazuje ocieplenie w ~30 min - czekamy na naturalny zanik'
            else:
                ucieczka, powod_ucieczki = (False, None)
                if dodatkowa_ucieczka_sniegu is not None:
                    ucieczka, powod_ucieczki = dodatkowa_ucieczka_sniegu(row_data, snow_depth_mm)
                if ucieczka:
                    need_heat = False
                    target_temperature = hrt_temp
                    reason = powod_ucieczki
                else:
                    need_heat = True
                    penalty = min(snow_depth_mm * RISK_SNOW_PENALTY_PER_MM_C, RISK_SNOW_PENALTY_MAX_C)
                    target_temperature = self.hrt_on_precip + penalty
                    if snow_depth_mm > RISK_SNOW_LINGER_THRESHOLD_MM:
                        reason = f'zalegający śnieg ({snow_depth_mm:.0f} mm) - cel podniesiony o {penalty:.1f}°C, żeby go porządnie wytopić'
                    else:
                        reason = 'opad śniegu do wytopienia'
        elif hrt_temp <= RISK_HRT_FLOOR_TRIGGER_C or forecast_min_c <= RISK_FORECAST_COLD_TRIGGER_C:
            need_heat = True
            target_temperature = RISK_HRT_FLOOR_TARGET_C
            reason = f'ochrona przed spadkiem HRT poniżej {RISK_HRT_ABSOLUTE_FLOOR_C:.0f}°C (bieżąco lub wg prognozy)'
        elif at_temp <= self.at_low_freeze:
            need_heat = True
            target_temperature = self.hrt_on_dry
            reason = 'suchy mróz'
        else:
            need_heat = False
            target_temperature = hrt_temp
            reason = 'brak zagrożenia'

        self._dodaj_flopy(20)  # Priorytety 1-4 (porównania progów, kara za śnieg).
        return target_temperature, need_heat, reason, forecast_min_c, warmup_soon


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
    Jak KontrolerRyzykaBazowy, ale dokłada prognozę OPADU (przewidywanie_opadow.py -
    model wilgotności względnej/temperatury mokrego termometru na prognozie AT z
    Kalmana) jako DODATKOWY warunek zwalniający z grzania w gałęzi śniegu: jeśli
    prognoza pokazuje, że front opadowy kończy się w najbliższych
    RISK_OPAD_HORYZONT_KROKOW krokach, a zalegająca pokrywa jest cienka
    (<= RISK_OPAD_PROGNOZA_CIENKA_MM), NIE grzejemy na zapas - ufamy, że
    bezwładność cieplna/naturalne ocieplenie dokończy topienie. To przesłanka
    NIEZALEŻNA od prognozy CRT (warmup_soon) - łapie sytuacje, gdy front mija,
    ale sama szyna jeszcze się nie zdążyła ocieplić.

    Nie jest samodzielnym algorytmem (brak wpisu w rejestr_algorytmow.py) -
    dziedziczą po niej *_opad.py: funkcja_ryzyka_binarna_opad.py,
    funkcja_ryzyka_pid_opad.py, funkcja_fuzzy_ryzyko_*_opad.py.
    """

    def __init__(self):
        super().__init__()
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
