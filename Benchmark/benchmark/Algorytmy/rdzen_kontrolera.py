# Algorytmy/rdzen_kontrolera.py
#
# WSPÓLNY RDZEŃ dla wszystkich kontrolerów opartych o pamięć czujników +
# prognozę Kalmana (histereza_let1.py, funkcja_ryzyka_binarna.py,
# funkcja_ryzyka_pid.py). Każdy z tych plików to OSOBNY algorytm (osobna
# klasa, osobny plik - łatwiej nawigować), ale wszystkie potrzebują tej samej
# infrastruktury: pamięci odczytów czujników, prognozy Kalmana AT/CRT
# (2h horyzontu, krok 15 min) i (opcjonalnie) autotestu identyfikującego
# obiekt grzewczy (SOPDT). Trzymanie tego w jednym miejscu gwarantuje, że
# żaden z algorytmów nie rozjedzie się przypadkiem w szczegółach prognozy.
#
# KontrolerBazowy to klasa bazowa (nie jest samodzielnym algorytmem i nie ma
# wpisu w rejestr_algorytmow.py) - każdy właściwy algorytm dziedziczy po niej
# (bezpośrednio albo przez funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy).

from collections import deque
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from numba import njit
from scipy import signal
from scipy.optimize import curve_fit

MODEL_HISTORIA_U_MAX_PROBEK = 4800  # zapas ponad typowe opoznienie L (~1200s) - patrz _krok_modelu

# ==========================================
# PARAMETRY FILTRU KALMANA (prognoza temperatury AT / CRT, horyzont max 2h)
# Wartości identyczne jak w Risk_function/Kalman_2.py
# ==========================================
PROCESS_VARIANCE = 0.05       # Szum procesu: jak bardzo temperatura może sama „dryfować”.
MEASUREMENT_VARIANCE = 0.25   # Szum pomiaru: jak bardzo odczyt może być niedokładny.
STEP_MINUTES = 15             # Czas trwania pojedynczego kroku prognozy (w minutach).
STEP_SECONDS = STEP_MINUTES * 60  # Szerokość okna resamplingu [s], do szybkiej ścieżki numba.
NANOS_PER_BIN = STEP_SECONDS * 1_000_000_000  # Szerokość binu w nanosekundach (Timestamp.value).
HORIZON_STEPS = 8             # Liczba próbek w horyzoncie prognozy (8 próbek * 15 min = 2 godziny).
MAX_ROLLING_HISTORY = 36      # Maksymalna liczba punktów historii brana pod uwagę przez model.

TEMP_FORECAST_REFRESH_S = 300            # Odśwież prognozę Kalmana nie częściej niż raz na tyle sekund (5 min - obiekt ma stałe czasowe rzędu 20-40 min, więc częstsze odświeżanie nic nie daje, a przy wywoływaniu co sekundę koszt O(historia) na krok byłby zabójczy).

# ==========================================
# PARAMETRY AUTOTESTU (identyfikacja obiektu SOPDT metodą skoku temperatury)
# Zwalidowane skryptem Identyfikacja_obiektu/autotest_identyfikacja_testing.py
# ==========================================
AUTOTEST_HARD_MAX_HRT_C = 40.0                 # Twardy limit konstrukcyjny szyny ogrzewanej.
AUTOTEST_SAFETY_MARGIN_C = 2.0                 # Zapas na bezwładność/opóźnienie reakcji układu.
AUTOTEST_SAFETY_CUTOFF_HRT_C = AUTOTEST_HARD_MAX_HRT_C - AUTOTEST_SAFETY_MARGIN_C  # Realny próg przerwania testu (latem decyduje głównie ten warunek).
AUTOTEST_MAX_DURATION_S = 4 * 3600             # Twardy limit czasowy autotestu (4h) - nie czekamy w nieskończoność na stabilizację.
AUTOTEST_MIN_RESPONSE_FOR_STAB_C = 1.0         # Zanim sprawdzamy stabilizację, odpowiedź musi realnie ruszyć (unika fałszywej detekcji w trakcie samego opóźnienia).
AUTOTEST_SMOOTH_WINDOW_S = 60                  # Krótkie okno uśredniania sygnału przed sprawdzeniem progu startowego [s] (odporność na szum czujników).
AUTOTEST_STAB_WINDOW_S = 600                   # Okno, na którym regresją liniową liczymy tempo zmian [s] (zimą odpowiedź potrafi się ustabilizować przed limitem 40°C).
AUTOTEST_STAB_RATE_THRESHOLD_C_PER_S = 0.0008  # Poniżej tego tempa zmian (z regresji) uznajemy odpowiedź za ustabilizowaną.

# ==========================================
# ESTYMATOR GRUBOŚCI ŚNIEGU (bilans masy z odczytów, BEZ dostępu do prawdziwej
# grubości z modelu fizycznego) - patrz KontrolerBazowy._estymuj_grubosc_sniegu_mm.
# ==========================================
SNIEG_TOPNIENIE_MM_S_NA_C = 0.001  # Szacowane tempo topnienia pokrywy pod wpływem HRT>0°C [mm/s na °C].


@njit(cache=True)
def _kalman_forecast_core(values, steps, process_variance, measurement_variance):
    """
    Rdzeń filtru Kalmana (poziom + trend) skompilowany JIT-em numba - te same
    równania co klasyczna postać macierzowa (stan 2D, kowariancja 2x2), tylko
    rozpisane na skalary, żeby numba mogła je skompilować do kodu maszynowego
    (nopython mode nie wspiera dobrze operacji na macierzach z pandas/obiektami).
    Wywoływana z każdego kroku symulacji (co TEMP_FORECAST_REFRESH_S) - JIT
    eliminuje narzut interpretera Pythona na tej pętli.
    """
    n = values.shape[0]
    q = process_variance
    r = measurement_variance

    if n == 1:
        level = values[0]
        trend = 0.0
    else:
        level = values[-1]
        trend = values[-1] - values[-2]

    p00 = 1.0
    p01 = 0.0
    p11 = 1.0

    for i in range(n):
        measurement = values[i]

        level_pred = level + trend
        trend_pred = trend
        p00_pred = p00 + 2.0 * p01 + p11 + q
        p01_pred = p01 + p11
        p11_pred = p11 + q

        innovation = measurement - level_pred
        s = p00_pred + r
        k0 = p00_pred / s
        k1 = p01_pred / s

        level = level_pred + k0 * innovation
        trend = trend_pred + k1 * innovation

        p00 = (1.0 - k0) * p00_pred
        p01 = (1.0 - k0) * p01_pred
        p11 = p11_pred - k1 * p01_pred

    forecasts = np.empty(steps, dtype=np.float64)
    for j in range(steps):
        level = level + trend
        forecasts[j] = level
        p00 = p00 + 2.0 * p01 + p11 + q
        p01 = p01 + p11
        p11 = p11 + q

    return forecasts


@dataclass
class RowData:
    """Struktura danych reprezentująca pojedynczy odczyt z czujników."""

    timestamp: datetime = None
    crt_temp: float = 0.0  # Temperatura szyny nieogrzewanej (CRT_temp_niegrzana)
    hrt_temp: float = 0.0  # Temperatura szyny ogrzewanej (HRT_temp_grzana)
    at_temp: float = 0.0  # Temperatura powietrza (AT_temp_powietrza)
    rh_humidity: float = 0.0  # Wilgotność względna (RH_wilgotnosc_wzgledna)
    pressure: float = 0.0  # Ciśnienie atmosferyczne (PRES_cisnienie)
    precip: float = 0.0  # Opad atmosferyczny (PRECIP_opad)
    snow: float = 0.0  # Śnieg (SNOW_snieg)
    pwr_l1: float = 0.0  # Moc L1 (PWR_L1)
    pwr_l2: float = 0.0  # Moc L2 (PWR_L2)


class KontrolerBazowy:
    """
    Klasa bazowa: pamięć odczytów czujników + prognoza Kalmana (AT/CRT) +
    autotest identyfikujący obiekt grzewczy (SOPDT). NIE jest samodzielnym
    algorytmem sterowania (brak wpisu w rejestr_algorytmow.py) - dziedziczą
    po niej histereza_let1.KontrolerHisterezaLET1 i (przez
    funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy) obie wersje funkcji ryzyka.
    """

    def __init__(self):
        self.row_data = RowData()

        # --- KROK STEROWANIA [s] - co ile sekund symulacja FAKTYCZNIE woła
        # metodę decyzyjną tego kontrolera (ustawiane z zewnątrz przez
        # symulacja_fizyczna.uruchom_kontroler zaraz po utworzeniu instancji -
        # `controller._dt_sterowania = dt`). Domyślnie 1.0 - DOKŁADNIE
        # zachowanie sprzed dodania tego parametru. Używane wyłącznie do
        # poprawnego przeskalowania "cyfrowego bliźniaka" (patrz
        # _zbuduj_model_z_autotestu w funkcja_ryzyka_wspolne._autotest_startowy
        # i _evaluate_risk_setpoint) - bez tego model wewnętrznie zakładałby
        # dt=1s niezależnie od realnego kroku symulacji i rozjeżdżałby się z
        # upływem czasu przy dt != 1.0. ---
        self._dt_sterowania = 1.0

        # --- LICZNIK OPERACJI ZMIENNOPRZECINKOWYCH (FLOPs) - patrz _dodaj_flopy.
        # W odróżnieniu od 'flops_na_krok' w rejestr_algorytmow.py (szacunek
        # analityczny, stały na algorytm) to jest RZECZYWISTA, zmierzona liczba
        # operacji wykonanych PRZEZ TĄ KONKRETNĄ instancję w TYM KONKRETNYM
        # przebiegu - zależy od faktycznej długości historii/prognoz, nie tylko
        # od typu algorytmu. Odczytywany na końcu przez
        # symulacja_fizyczna.uruchom_kontroler i zapisywany jako
        # stats['flops_rzeczywiste']. ---
        self._flops_licznik = 0

        # --- STAN AUTOTESTU (identyfikacja obiektu skokiem temperatury) ---
        self.autotest_active = False        # Czy autotest jest właśnie w trakcie trwania.
        self.autotest_start_time = None     # Chwila (Timestamp) rozpoczęcia bieżącego autotestu.
        self.autotest_samples = []          # Lista (czas_od_startu_s, HRT, CRT) zebrana w trakcie testu.
        self.autotest_result = None         # Wynik ostatniego zakończonego autotestu (dict albo None).
        self._autotest_window_ptr = 0       # Wskaźnik do próbki sprzed okna stabilizacji (optymalizacja).

        # --- CACHE PROGNOZ KALMANA (patrz TEMP_FORECAST_REFRESH_S i _forecast_attribute) ---
        self._forecast_cache_at = None
        self._forecast_cache_time_at = None
        self._forecast_cache_crt = None
        self._forecast_cache_time_crt = None

        # --- BUFOR KROCZĄCEJ ŚREDNIEJ 15-MINUTOWEJ (AT/CRT) dla _forecast_attribute -
        # ZAMIAST trzymania surowej historii odczytów (poprzedni projekt: rosnącej
        # do 86400 próbek, czyli O(min(krok,86400)) pamięci na instancję kontrolera,
        # ~18-21MB szacunkowo w rejestr_algorytmow.py), _append_sensor_history AGREGUJE na bieżąco: sumuje
        # próbki w BIEŻĄCYM (jeszcze niezamkniętym) binie 15-minutowym
        # (`_cur_sum_at/_cur_sum_crt/_cur_count`), a gdy napłynie próbka z NOWEGO
        # bin_id, zamyka poprzedni bin (dzieli sumę przez licznik) i dopisuje jego
        # średnią do `deque(maxlen=MAX_ROLLING_HISTORY)` - stały rozmiar O(36)
        # NIEZALEŻNIE od długości symulacji, bo `_kalman_forecast_series` i tak
        # nigdy nie używa więcej niż ostatnie MAX_ROLLING_HISTORY uśrednionych
        # binów (patrz `resampled = full_means[-MAX_ROLLING_HISTORY:]` w
        # _forecast_attribute - stare podejście liczyło to samo obcięcie na
        # WIELE RAZY większej tablicy, więc wynik był identyczny, tylko drożej
        # liczony). Matematycznie RÓWNOWAŻNE staremu podejściu (weryfikacja:
        # bit-identyczna energia risk_function_pid przed/po, patrz AGENTS.md) -
        # bo bin_id w tym symulatorze są zawsze ściśle kolejne (brak
        # rzeczywistych "dziur" w próbkowaniu), więc interpolacja luk (np.interp
        # niżej) jest no-opem w praktyce, a "ostatnie 36 binów" ze skróconego
        # bufora to dokładnie te same biny, co "ostatnie 36 binów" wyliczone ze
        # WSZYSTKICH binów od początku symulacji. ---
        self._roll_bin_ids = deque(maxlen=MAX_ROLLING_HISTORY)
        self._roll_means_at = deque(maxlen=MAX_ROLLING_HISTORY)
        self._roll_means_crt = deque(maxlen=MAX_ROLLING_HISTORY)
        self._cur_bin_id = None
        self._cur_sum_at = 0.0
        self._cur_sum_crt = 0.0
        self._cur_count = 0
        self._hist_last_timestamp = None

        # --- "CYFROWY BLIŹNIAK" GRZAŁKI ZBUDOWANY Z WYNIKU AUTOTESTU (patrz
        # _zbuduj_model_z_autotestu / _krok_modelu / _prognoza_zanikania_ciepla) -
        # pozwala _evaluate_risk_setpoint prognozować HRT fizycznie (zanikające
        # ciepło z już wydanych komend mocy), a nie tylko statystycznie z Kalmana.
        # Dopóki self._model_zidentyfikowany == False, wszystko działa DOKŁADNIE
        # jak przed tą funkcją (czysta prognoza Kalmana). ---
        self._model_zidentyfikowany = False
        self._model_A = None
        self._model_B = None
        self._model_C = None
        self._model_D = None
        self._model_opoznienie_kroki = 0
        self._model_x = None
        self._model_u_history = []
        # Cache prognozy zanikania ciepła (patrz funkcja_ryzyka_wspolne._evaluate_risk_setpoint) -
        # _prognoza_zanikania_ciepla robi pętlę o długości HORIZON_STEPS*STEP_SECONDS
        # (domyślnie 7200 kroków) - bez cache'a wołanie jej co sekundę (tak jak
        # _evaluate_risk_setpoint jest wołane) byłoby zabójczo kosztowne, dokładnie
        # tak samo jak bez cache'a byłaby prognoza Kalmana (TEMP_FORECAST_REFRESH_S).
        self._model_forecast_cache = None
        self._model_forecast_cache_time = None

        # Ostatnia moc zwrócona przez autotest() (100% w trakcie testu, 0% w
        # kroku, w którym się kończy) - patrz _autotest_startowy.
        self._ostatnia_moc_autotestu = 100.0

        # --- ESTYMATOR GRUBOŚCI ŚNIEGU (patrz _estymuj_grubosc_sniegu_mm) - stan
        # WŁASNEGO, samodzielnie liczonego bilansu masy śniegu kontrolera, NIE
        # prawdziwej grubości z modelu fizycznego symulacji. ---
        self._snieg_estymowany_mm = 0.0

    def _dodaj_flopy(self, n):
        """Dopisuje `n` do licznika RZECZYWIŚCIE wykonanych FLOPs (patrz __init__)."""
        self._flops_licznik += n

    def _estymuj_grubosc_sniegu_mm(self, row_data):
        """
        Prosty bilans masy śniegu SZACOWANY WYŁĄCZNIE z tego, co widziałby
        prawdziwy sterownik (odczyt intensywności opadu śniegu SNOW_snieg
        [mm/s] + odczyt HRT) - BEZ dostępu do prawdziwej grubości śniegu z
        modelu fizycznego (ice_model.snow_depth_m w symulacja_fizyczna.py,
        przekazywanej do row_data jako 'SNIEG_GRUBOSC_MM' WYŁĄCZNIE do użytku
        bezpiecznika/referencji symulacji - patrz snow_reference_mm w
        symulacja_fizyczna.uruchom_kontroler - NIE do czytania przez logikę
        decyzyjną kontrolera, stąd ta metoda zamiast bezpośredniego odczytu
        tego pola).

        CELOWE uproszczenie (nie replikuje bilansu energetycznego SnowClim,
        analogicznie do przybliżenia ice_proxy_mm w
        funkcja_nauka_kary_wspolna.py - jawnie udokumentowane, nie "ukryty"
        skrót):
          - PRZYROST = intensywność opadu śniegu (SNOW_snieg, mm/s) * krok
            sterowania (self._dt_sterowania) - ile śniegu realnie spadło w
            tym kroku.
          - UBYTEK = przybliżone tempo topnienia proporcjonalne do HRT > 0°C
            (prosty model typu "degree-day": SNIEG_TOPNIENIE_MM_S_NA_C *
            max(HRT, 0) * krok sterowania) - im cieplejsza (ogrzana) szyna,
            tym szybciej styka się z nią topniejący śnieg.

        Stan (self._snieg_estymowany_mm) jest WŁASNOŚCIĄ INSTANCJI kontrolera
        (nie symulacji) - każdy kontroler liczy WŁASNY, niezależny bilans z
        WŁASNYCH odczytów, dokładnie tak jak robiłby to prawdziwy sterownik.

        Ponieważ liczone WYŁĄCZNIE z pól row_data, te same pola przechodzą
        przez ewentualny fault_injector (patrz
        symulacja_fizyczna.uruchom_kontroler, wołany PRZED przekazaniem
        odczytu kontrolerowi) - ten estymator jest więc automatycznie
        podatny na te same awarie/szum co reszta logiki kontrolera (np. bias
        albo szum na SNOW_snieg/HRT_temp_grzana w test_awarie_czujnikow.py
        skazi też ten bilans), bez potrzeby osobnego mechanizmu zaszumiania.
        """
        snow_rate_mm_s = float(row_data.get('SNOW_snieg', 0.0))
        hrt_temp = float(row_data.get('HRT_temp_grzana', 0.0))
        dt = self._dt_sterowania

        przyrost = snow_rate_mm_s * dt
        ubytek = SNIEG_TOPNIENIE_MM_S_NA_C * max(hrt_temp, 0.0) * dt

        self._snieg_estymowany_mm = max(0.0, self._snieg_estymowany_mm + przyrost - ubytek)
        self._dodaj_flopy(4)  # 2 mnożenia (przyrost, ubytek) + odjęcie + max/clip.
        return self._snieg_estymowany_mm

    # --- Funkcja pomocnicza filtru Kalmana: zamienia wejście na czystą serię liczbową ---
    @staticmethod
    def _normalize_series(values):
        series = pd.Series(values)  # Konwertujemy dowolny input na serię pandas.
        series = series.dropna()  # Usuwamy braki danych, bo Kalman nie lubi pustych punktów.
        series = series.astype(float)  # Wymuszamy typ liczbowy, żeby działały obliczenia.
        return series  # Zwracamy oczyszczoną serię, gotową do filtrowania.

    # --- Filtr Kalmana (poziom + trend): uczy się na historii i prognozuje do przodu ---
    # Rdzeń numeryczny to _kalman_forecast_core (JIT numba) - tu tylko przygotowujemy
    # dane wejściowe (pandas -> czysta tablica float64) i oddajemy wynik jako listę,
    # żeby interfejs metody się nie zmienił.
    def _kalman_forecast_series(self, values, steps):
        series = self._normalize_series(values)  # Czyścimy dane wejściowe.
        if series.empty:  # Jeżeli nie ma danych, nie da się przewidywać.
            return []  # Zwracamy pustą listę prognoz.

        values_arr = series.to_numpy(dtype=np.float64)
        forecasts = _kalman_forecast_core(values_arr, int(steps), PROCESS_VARIANCE, MEASUREMENT_VARIANCE)
        # ~20 FLOPs/próbka historii (aktualizacja stanu+kowariancji Kalmana) +
        # ~7 FLOPs/krok prognozy w przód (patrz rozpiska w _kalman_forecast_core).
        self._dodaj_flopy(len(values_arr) * 20 + int(steps) * 7)
        return forecasts.tolist()  # Oddajemy listę wartości temperatury w przyszłości, krok po kroku.

    def _append_sensor_history(self, reading):
        """Aktualizuje bufor kroczącej średniej 15-minutowej w STAŁEJ pamięci
        O(MAX_ROLLING_HISTORY) - patrz uzasadnienie przy deklaracji buforów w
        __init__. Zamyka bieżący bin (dzieli sumę przez licznik próbek) i
        dopisuje jego średnią do bufora kroczącego dokładnie wtedy, gdy
        napłynie próbka należąca już do NOWEGO binu 15-minutowego - to samo
        grupowanie "po kolejnych równych bin_id", co dawne (usunięte)
        _bin_average_core na surowej historii, tylko liczone PRZYROSTOWO."""
        if reading.timestamp is None:
            return

        bin_id = reading.timestamp.value // NANOS_PER_BIN
        if self._cur_bin_id is None:
            self._cur_bin_id = bin_id
        elif bin_id != self._cur_bin_id:
            self._roll_bin_ids.append(self._cur_bin_id)
            self._roll_means_at.append(self._cur_sum_at / self._cur_count)
            self._roll_means_crt.append(self._cur_sum_crt / self._cur_count)
            self._dodaj_flopy(2)  # Dwa dzielenia (średnia AT, średnia CRT) przy zamknięciu binu.
            self._cur_bin_id = bin_id
            self._cur_sum_at = 0.0
            self._cur_sum_crt = 0.0
            self._cur_count = 0

        self._cur_sum_at += reading.at_temp
        self._cur_sum_crt += reading.crt_temp
        self._cur_count += 1
        self._hist_last_timestamp = reading.timestamp
        self._dodaj_flopy(2)  # Dwa sumowania (AT, CRT) do bieżącego binu.

    def _forecast_attribute(self, attribute_name, cache_key):
        """
        Ogólna prognoza Kalmana (poziom + trend) dla wybranego atrybutu historii
        zapisanej w self.sensor_history (np. 'at_temp' albo 'crt_temp'). Zwraca
        tablicę 8 wartości co 15 minut (2h horyzontu), tak jak temperature_prediction.

        Cache: przy wywoływaniu co sekundę (np. z risk_function) nie ma sensu przeliczać
        prognozy częściej niż raz na TEMP_FORECAST_REFRESH_S - w tym oknie i tak nie
        zmieni się ona znacząco, a przeliczanie kosztuje O(historia) za każdym razem.
        Każdy atrybut ma WŁASNY cache (cache_key), żeby prognoza AT i prognoza CRT
        się nie nadpisywały.

        Resampling do siatki 15-minutowej: `_append_sensor_history` utrzymuje już
        gotowy bufor KROCZĄCEJ średniej (`self._roll_bin_ids/_roll_means_at/_crt`,
        rozmiar co najwyżej MAX_ROLLING_HISTORY, patrz uzasadnienie przy
        deklaracji w __init__) zamiast surowej historii odczytów - tutaj
        wystarczy doczytać ten mały bufor + domknąć BIEŻĄCY (jeszcze
        niezamknięty) bin jego dotychczasową średnią. Ewentualne luki
        (brakujący bin - realny dropout czujnika, czego ten symulator nigdy
        nie generuje) wypełnia np.interp po indeksie binu - dla siatki o
        stałym kroku (900 s) to dokładnie to samo co pandas
        `.interpolate(method='time')`.
        """
        array = [0, 0, 0, 0, 0, 0, 0, 0]
        cache_value_attr = f'_forecast_cache_{cache_key}'
        cache_time_attr = f'_forecast_cache_time_{cache_key}'

        latest_timestamp = self._hist_last_timestamp
        cached_value = getattr(self, cache_value_attr)
        cached_time = getattr(self, cache_time_attr)
        if (cached_value is not None and latest_timestamp is not None and cached_time is not None
                and (latest_timestamp - cached_time).total_seconds() < TEMP_FORECAST_REFRESH_S):
            return cached_value

        roll_means = self._roll_means_at if attribute_name == 'at_temp' else self._roll_means_crt
        bin_ids = list(self._roll_bin_ids)
        means = list(roll_means)
        if self._cur_count > 0:
            cur_sum = self._cur_sum_at if attribute_name == 'at_temp' else self._cur_sum_crt
            bin_ids.append(self._cur_bin_id)
            means.append(cur_sum / self._cur_count)
            self._dodaj_flopy(1)  # Średnia bieżącego (niezamkniętego) binu.

        if len(bin_ids) < 2:  # Bez minimum dwóch binów nie da się ustawić trendu.
            return array  # Zwracamy domyślną tablicę zer, tak jak w oryginalnym interfejsie.

        bin_group_ids = np.array(bin_ids, dtype=np.int64)
        bin_means = np.array(means, dtype=np.float64)

        full_bins = np.arange(bin_group_ids[0], bin_group_ids[-1] + 1)
        full_means = np.interp(full_bins, bin_group_ids, bin_means)
        # ~2 FLOPs/bin interpolowany (np.interp - wyszukanie przedziału + interpolacja liniowa) -
        # co najwyżej MAX_ROLLING_HISTORY+1 binów teraz, nie cała historia od początku symulacji.
        self._dodaj_flopy(len(full_bins) * 2)
        if len(full_means) < 2:
            return array

        resampled = full_means[-MAX_ROLLING_HISTORY:]  # Ograniczamy pamięć modelu tak jak w oryginale.

        forecasts = self._kalman_forecast_series(resampled, HORIZON_STEPS)
        if len(forecasts) < HORIZON_STEPS:  # Zabezpieczenie na wypadek zbyt krótkiej historii.
            padding_value = forecasts[-1] if forecasts else 0.0
            forecasts = forecasts + [padding_value] * (HORIZON_STEPS - len(forecasts))

        setattr(self, cache_value_attr, forecasts)
        setattr(self, cache_time_attr, latest_timestamp)
        return forecasts

    def temperature_prediction(self):
        """
        Metoda zwraca tablicę z 8 wartościami predykcji temperatury POWIETRZA (°C)
        informującą o temperaturze w najbliższych 2 godzinach (krok 15 minutowy).
        Prognoza jest wyliczana filtrem Kalmana (poziom + trend) na podstawie
        historii odczytów AT_temp_powietrza zapisanej w self.sensor_history.
        """
        return self._forecast_attribute('at_temp', 'at')

    def rail_temperature_prediction(self):
        """
        Analogicznie do temperature_prediction, ale prognozuje temperaturę SZYNY
        NIEOGRZEWANEJ (CRT), tym samym filtrem Kalmana, na podstawie historii CRT
        zapisanej w self.sensor_history. CRT niesie więcej informacji o realnym
        stanie szyny niż sama temperatura powietrza (uwzględnia bezwładność cieplną
        - por. transmitancję pogodową K_W/T1_W/TZ_W z symulacja_fizyczna.py), więc
        lepiej nadaje się do oceny, czy sama szyna naturalnie się ociepli/ochłodzi -
        używana w funkcja_ryzyka_wspolne._evaluate_risk_setpoint zamiast prognozy
        powietrza.
        """
        return self._forecast_attribute('crt_temp', 'crt')

    # --- Model matematyczny odpowiedzi skokowej obiektu II rzędu z opóźnieniem (SOPDT) ---
    @staticmethod
    def _sopdt_step_response(t, k, t1, t2, l):
        tau = np.clip(t - l, 0.0, None)  # Przed upływem opóźnienia odpowiedź jest zerowa.
        if abs(t1 - t2) < 1e-3:  # Przypadek krytycznie tłumiony (T1 == T2) wymaga osobnego wzoru.
            y = k * (1.0 - np.exp(-tau / t1) * (1.0 + tau / t1))
        else:
            y = k * (1.0 - (t1 * np.exp(-tau / t1) - t2 * np.exp(-tau / t2)) / (t1 - t2))
        return np.where(t < l, 0.0, y)

    # --- Identyfikacja parametrów K, T1, T2, L z (możliwie niepełnej) krzywej odpowiedzi ---
    def _identify_sopdt(self, t_arr, y_arr):
        y_max = max(float(np.max(y_arr)), 0.1)
        t_max = float(t_arr[-1]) if len(t_arr) else 1.0

        # Prosty szacunek opóźnienia: pierwszy moment, gdy sygnał wyraźnie ruszył.
        threshold = max(0.05 * y_max, 0.2)
        above = np.where(y_arr > threshold)[0]
        l_guess = float(t_arr[above[0]]) if len(above) else 0.0

        bounds_lower = [0.1, 5.0, 5.0, 0.0]
        bounds_upper = [300.0, 30000.0, 30000.0, max(t_max, 10.0)]
        t_span = max(t_max - l_guess, 10.0)

        # Kilka wariantów startowych dla K, bo przy nieukończonym skoku wzmocnienie
        # ustalone (K) jest najtrudniejszym do odgadnięcia parametrem.
        best_fit = None
        best_sse = np.inf
        for k0 in (y_max * 1.1, y_max * 1.5, y_max * 2.5, y_max * 4.0, y_max * 8.0):
            p0 = [k0, max(t_span / 4.0, 10.0), max(t_span / 2.0, 20.0), max(l_guess, 0.0)]
            p0 = [min(max(p0[i], bounds_lower[i]), bounds_upper[i]) for i in range(4)]
            try:
                popt, _ = curve_fit(
                    self._sopdt_step_response, t_arr, y_arr, p0=p0,
                    bounds=(bounds_lower, bounds_upper), maxfev=20000,
                )
            except RuntimeError:
                continue
            sse = float(np.sum((y_arr - self._sopdt_step_response(t_arr, *popt)) ** 2))
            if sse < best_sse:
                best_sse = sse
                best_fit = popt

        if best_fit is None:
            return None

        pred = self._sopdt_step_response(t_arr, *best_fit)
        ss_res = float(np.sum((y_arr - pred) ** 2))
        ss_tot = float(np.sum((y_arr - np.mean(y_arr)) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
        k_fit, t1_fit, t2_fit, l_fit = best_fit
        return {'K': float(k_fit), 'T1': float(t1_fit), 'T2': float(t2_fit), 'L': float(l_fit), 'r_squared': r_squared}

    def autotest(self, row_data):
        """
        Autotest tożsamości obiektu grzewczego: wykonuje skok grzania 0% -> 100%
        i na podstawie zebranej odpowiedzi identyfikuje model inercyjny II rzędu
        z opóźnieniem (SOPDT: K, T1, T2, L), zakładając że właśnie taki jest typ
        naszego obiektu (grzałka rozjazdu).

        WAŻNE OGRANICZENIE BEZPIECZEŃSTWA: nie wolno czekać na pełną stabilizację
        temperatury, bo szyna ogrzewana (HRT) może osiągnąć maksymalnie 40°C -
        zimą zwykle starcza zapasu, żeby test zdążył się ustabilizować sam, ale
        latem (ciepłe powietrze = wysoka CRT) limit ten jest łatwo osiągalny dużo
        wcześniej. Dlatego test jest ucinany, gdy pierwsze z trzech zdarzeń
        nastąpi: HRT osiąga próg bezpieczeństwa, odpowiedź się ustabilizowała
        (typowe zimą) albo upłynął maksymalny dozwolony czas testu. Podejście to
        zostało zwalidowane w Identyfikacja_obiektu/autotest_identyfikacja_testing.py
        (błąd identyfikacji rzędu pojedynczych procent nawet przy ucięciu testu).

        Wywoływana cyklicznie (analogicznie do compute_control) z tym samym
        słownikiem pomiarowym row_data (potrzebne klucze: 'Timestamp',
        'HRT_temp_grzana', 'CRT_temp_niegrzana'). Zwraca krotkę:
          (moc_grzania_procent, wynik)
        gdzie `wynik` to None dopóki test trwa, a po zakończeniu - słownik
        {'K', 'T1', 'T2', 'L', 'r_squared', 'fit_ok', 'stop_reason',
         'duration_s', 'max_hrt_reached'}.
        """
        timestamp = row_data['Timestamp']
        hrt = float(row_data['HRT_temp_grzana'])
        crt = float(row_data['CRT_temp_niegrzana'])

        if not self.autotest_active:
            # (Re)start autotestu od zera - skok grzania 0% -> 100% zaczyna się teraz.
            self.autotest_active = True
            self.autotest_start_time = timestamp
            self.autotest_samples = []
            self.autotest_result = None
            self._autotest_window_ptr = 0

        elapsed = (timestamp - self.autotest_start_time).total_seconds()
        self.autotest_samples.append((elapsed, hrt, crt))

        stop_reason = None
        if hrt >= AUTOTEST_SAFETY_CUTOFF_HRT_C:
            # a) Warunek bezpieczeństwa - nadrzędny nad wszystkim innym. Sprawdzany na
            # ZMIERZONEJ wartości (tak jak widzi ją prawdziwy sterownik), stąd margines
            # AUTOTEST_SAFETY_MARGIN_C ponad ewentualny szum pomiarowy.
            stop_reason = 'safety_cap'
        elif elapsed >= AUTOTEST_MAX_DURATION_S:
            # c) Twardy limit czasowy - nie czekamy w nieskończoność.
            stop_reason = 'max_duration'
        else:
            # b) Detekcja naturalnej stabilizacji (typowe zimą - nie ma sensu ciągnąć testu dalej).
            # Zamiast porównywać dwie pojedyncze (zaszumione) próbki, uśredniamy sygnał na
            # krótkim oknie i liczymy tempo zmian regresją liniową na całym oknie stabilizacji -
            # to odporne na szum pomiarowy czujników HRT/CRT (dwupunktowe porównanie fałszywie
            # wykrywało "stabilizację" już przy szumie rzędu 0.2°C).
            smooth_cutoff = elapsed - AUTOTEST_SMOOTH_WINDOW_S
            smooth_values = [h - c for (t, h, c) in reversed(self.autotest_samples) if t >= smooth_cutoff]
            y_smoothed_now = float(np.mean(smooth_values)) if smooth_values else (hrt - crt)

            if y_smoothed_now > AUTOTEST_MIN_RESPONSE_FOR_STAB_C and elapsed > AUTOTEST_STAB_WINDOW_S:
                target_time = elapsed - AUTOTEST_STAB_WINDOW_S
                while (self._autotest_window_ptr < len(self.autotest_samples) - 1
                       and self.autotest_samples[self._autotest_window_ptr][0] < target_time):
                    self._autotest_window_ptr += 1
                window_samples = self.autotest_samples[self._autotest_window_ptr:]
                if len(window_samples) >= 2:
                    t_window = np.array([s[0] for s in window_samples])
                    y_window = np.array([s[1] - s[2] for s in window_samples])
                    slope = float(np.polyfit(t_window, y_window, 1)[0])
                    if abs(slope) < AUTOTEST_STAB_RATE_THRESHOLD_C_PER_S:
                        stop_reason = 'stabilized'

        if stop_reason is None:
            return 100.0, None  # Test trwa - kontynuujemy pełne grzanie.

        # Test zakończony - identyfikujemy obiekt na zebranych próbkach.
        t_arr = np.array([s[0] for s in self.autotest_samples])
        hrt_arr = np.array([s[1] for s in self.autotest_samples])
        crt_arr = np.array([s[2] for s in self.autotest_samples])
        y_arr = hrt_arr - crt_arr

        fit = self._identify_sopdt(t_arr, y_arr)
        self.autotest_result = {
            'K': fit['K'] if fit else None,
            'T1': fit['T1'] if fit else None,
            'T2': fit['T2'] if fit else None,
            'L': fit['L'] if fit else None,
            'r_squared': fit['r_squared'] if fit else None,
            'fit_ok': fit is not None,
            'stop_reason': stop_reason,
            'duration_s': float(elapsed),
            'max_hrt_reached': float(np.max(hrt_arr)),
        }
        self.autotest_active = False

        return 0.0, self.autotest_result

    # ------------------------------------------------------------------
    # "CYFROWY BLIŹNIAK" GRZAŁKI - zbudowany z K/T1/T2/L zidentyfikowanych
    # przez autotest(). Pozwala prognozować HRT FIZYCZNIE zamiast tylko
    # statystycznie (Kalman) - patrz funkcja_ryzyka_wspolne._evaluate_risk_setpoint.
    # ------------------------------------------------------------------
    def _zbuduj_model_z_autotestu(self, K, T1, T2, L, dt=1.0):
        """
        Buduje dyskretny model stanowy identyfikowanej grzałki (SOPDT: K, T1, T2,
        opóźnienie L) - DOKŁADNIE tą samą metodą co symulacja_fizyczna.przygotuj_modele_stanowe
        dla PRAWDZIWEGO obiektu (tf2ss + cont2discrete, zoh), żeby mechanika
        "cyfrowego bliźniaka" była identyczna z tym, jak faktycznie zachowuje się
        symulowana (albo prawdziwa) grzałka. Wywoływana RAZ, po udanym autoteście.
        """
        tf = signal.TransferFunction([K * 0.0, K], np.polymul([T1, 1], [T2, 1]).tolist())
        sys_ss = signal.tf2ss(tf.num, tf.den)
        A_d, B_d, C_d, D_d, _ = signal.cont2discrete(sys_ss, dt, method='zoh')

        self._model_A = A_d
        self._model_B = B_d
        self._model_C = C_d
        self._model_D = D_d
        self._model_opoznienie_kroki = max(int(round(L / dt)), 0)
        self._model_x = np.zeros((A_d.shape[0], 1))
        self._model_u_history = []
        self._model_zidentyfikowany = True

    def _krok_modelu(self, moc_procent):
        """
        Wywoływana RAZ na krok (po podjęciu decyzji o mocy) - przesuwa stan
        cyfrowego bliźniaka o jeden krok, dokładnie tak samo jak
        symulacja_fizyczna.uruchom_kontroler przesuwa PRAWDZIWY obiekt (ta sama
        linia opóźnienia: komenda mocy dociera z opóźnieniem L). Jeśli model
        nie został jeszcze zbudowany (autotest się nie powiódł/jeszcze trwa),
        nic nie robi - reszta kodu ma wtedy działać jak bez tej funkcji.
        """
        if not self._model_zidentyfikowany:
            return

        u = moc_procent / 100.0
        self._model_u_history.append(u)
        if len(self._model_u_history) > MODEL_HISTORIA_U_MAX_PROBEK * 2:
            self._model_u_history = self._model_u_history[-MODEL_HISTORIA_U_MAX_PROBEK:]

        idx = len(self._model_u_history) - 1
        if idx >= self._model_opoznienie_kroki:
            u_delayed = self._model_u_history[idx - self._model_opoznienie_kroki]
        else:
            u_delayed = 0.0

        self._model_x = self._model_A @ self._model_x + self._model_B * u_delayed
        # Aktualizacja stanu: A@x (n^2 mnożeń + n*(n-1) dodawań) + B*u (n mnożeń + n dodawań), n = wymiar stanu.
        n = self._model_A.shape[0]
        self._dodaj_flopy(2 * n * n + 2 * n)

    def _prognoza_zanikania_ciepla(self, liczba_krokow):
        """
        Symuluje cyfrowego bliźniaka W PRZÓD na `liczba_krokow` sekund, zakładając
        ZEROWĄ moc od teraz (czyli: "ile ciepła zostało jeszcze w rurze" z komend
        JUŻ wydanych, zanim naturalnie zaniknie). Komendy wydane w ostatnich
        `opoznienie_kroki` sekundach są jeszcze "w locie" (fizycznie nieuniknione,
        niezależnie od obecnej decyzji) - one WCIĄŻ dotrą, dopiero po nich moc
        realnie spada do zera. Zwraca listę składowej grzewczej HRT na każdy krok
        (pustą listę, jeśli model nie został jeszcze zbudowany).
        """
        if not self._model_zidentyfikowany:
            return []

        x = self._model_x.copy()
        if self._model_opoznienie_kroki > 0:
            juz_w_locie = self._model_u_history[-self._model_opoznienie_kroki:]
        else:
            juz_w_locie = []

        wyniki = np.empty(liczba_krokow, dtype=np.float64)
        for i in range(liczba_krokow):
            u_delayed = juz_w_locie[i] if i < len(juz_w_locie) else 0.0
            # y[k] = C@x[k] + D@u[k] LICZONE PRZED przesunięciem stanu - ta sama
            # konwencja co scipy.signal.dlsim (x[k] to stan SPRZED kroku k).
            wyniki[i] = float((self._model_C @ x + self._model_D * u_delayed)[0, 0])
            x = self._model_A @ x + self._model_B * u_delayed
        # Na iterację: C@x + D*u (~2n FLOPs) + A@x + B*u (~2n^2+2n FLOPs), n = wymiar stanu.
        n = self._model_A.shape[0]
        self._dodaj_flopy(liczba_krokow * (2 * n * n + 4 * n + 1))
        return wyniki

    def _autotest_startowy(self, row_data):
        """
        Jednorazowy autotest PRZY STARCIE (patrz autotest() wyżej) - dopóki
        self.autotest_result is None, wymusza pełne grzanie i zbiera próbki do
        identyfikacji obiektu. Po zakończeniu (sukces LUB porażka, sprawdzane
        raz) buduje "cyfrowy bliźniak" grzałki (_zbuduj_model_z_autotestu) do
        użytku przez wywołującego - jeśli identyfikacja się nie powiedzie
        (fit_ok=False), model NIE powstaje i _model_zidentyfikowany zostaje
        False (wywołujący ma wtedy wrócić do zachowania bez cyfrowego
        bliźniaka, dokładnie jak przed jego dodaniem).

        Przeniesione tu (z pierwotnego funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy)
        żeby było dostępne dla KAŻDEGO kontrolera dziedziczącego KontrolerBazowy,
        nie tylko rodziny funkcji ryzyka - np. funkcja_nauka_kary_pid_blizniak.py/
        _ryzyko.py. Zero zmiany zachowania dla dotychczasowych użytkowników
        (KontrolerRyzykaBazowy nadal go dziedziczy, tylko już nie definiuje
        osobno).

        Zwraca True, dopóki autotest trwa (wywołujący ma wtedy zwrócić moc z
        tej metody i pominąć normalną logikę decyzyjną), False gdy jest już
        zakończony (w tym LUB w którymś z poprzednich wywołań) - wtedy
        wywołujący ma wykonać normalną logikę.
        """
        if self.autotest_result is not None:
            return False

        self._ostatnia_moc_autotestu, wynik = self.autotest(row_data)
        if wynik is not None and wynik['fit_ok']:
            # dt=self._dt_sterowania - cyfrowy bliźniak MUSI być dyskretyzowany
            # tym samym krokiem, w jakim faktycznie będzie odpytywany
            # (_krok_modelu wołane raz na każdą decyzję sterowania, nie raz na
            # sekundę fizyki) - inaczej jego wewnętrzny zegar rozjeżdżałby się
            # z rzeczywistym czasem przy kroku sterowania != 1s.
            self._zbuduj_model_z_autotestu(wynik['K'], wynik['T1'], wynik['T2'], wynik['L'],
                                            dt=self._dt_sterowania)
            # Autotest grzeje CAŁY czas trwania testu pełną mocą (100%) od stanu
            # zerowego (skok 0%->100%) - "przewijamy" świeżo zbudowanego
            # cyfrowego bliźniaka przez DOKŁADNIE ten sam profil mocy, żeby jego
            # stan (i linia opóźnienia) odpowiadał temu, co naprawdę dzieje się
            # z obiektem W TEJ CHWILI, zamiast zaczynać "na zimno" (co
            # fałszywie sugerowałoby zerowe ciepło resztkowe zaraz po
            # zakończeniu kilkugodzinnego grzania pełną mocą). Liczba kroków =
            # liczba RZECZYWISTYCH decyzji sterowania w czasie trwania testu
            # (duration_s sekund / dt_sterowania sekund na decyzję), nie liczba
            # sekund - każdy krok modelu pokrywa dt_sterowania sekund, nie 1s.
            liczba_krokow_przewijania = int(round(wynik['duration_s'] / self._dt_sterowania))
            for _ in range(liczba_krokow_przewijania):
                self._krok_modelu(100.0)
        return wynik is None
