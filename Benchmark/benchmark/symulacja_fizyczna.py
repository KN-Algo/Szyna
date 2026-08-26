# ==============================================================================
# WSPÓLNY RDZEŃ SYMULACJI FIZYCZNEJ (transmitancje pogoda/grzanie + model śniegu)
#
# Używany przez:
#   - test_jeden_algorytm_jedna_lokalizacja.py            - JEDEN algorytm, JEDNA lokalizacja + GUI
#   - test_wszystkie_algorytmy_jedna_lokalizacja.py       - WSZYSTKIE algorytmy, JEDNA lokalizacja
#   - test_wszystkie_algorytmy_wszystkie_lokalizacje.py   - WSZYSTKIE algorytmy, WSZYSTKIE lokalizacje (sekwencyjnie)
#   - test_wszystkie_rownolegle.py                        - to samo co wyżej, ale na wielu procesach naraz
#
# Trzymanie tej logiki w jednym miejscu gwarantuje, że wszystkie trzy skrypty
# symulują dokładnie tę samą fizykę (transmitancje zidentyfikowane w
# Identyfikacja_obiektu/ + SnowClimPhysicalModel) i różnią się WYŁĄCZNIE
# algorytmem decyzyjnym.
# ==============================================================================

import os
import sys
import time
import pandas as pd
import numpy as np
from scipy import signal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
sys.path.insert(0, os.path.join(BASE_DIR, 'Model_sniegu_SnowClim'))

from snowclim_physical_model import SnowClimPhysicalModel  # noqa: E402

SUWALKI_LATITUDE_DEG = 54.1
MOC_ZAMIANOWA_GRZALKI_KW = 14.0

# --- PARAMETRY MODELU OBIEKTU (identyczne jak main_test.py) ---
K_W = 1.09075872; T1_W = 5771.977521; TZ_W = 780.0337376
K_H = 51.1163668; T1_H = 1120.914508; T2_H = 2450.968465; L_H = 1194.184089

TF_WEATHER = signal.TransferFunction([K_W * TZ_W, K_W], [T1_W, 1])
TF_HEATING = signal.TransferFunction([K_H * 0.0, K_H], np.polymul([T1_H, 1], [T2_H, 1]).tolist())


# SnowClimPhysicalModel.update() oczekuje "sekund słońca w oknie 900s" jako wewnętrznej,
# stałej skali (patrz Model_sniegu_SnowClim/snowclim_physical_model.py) - niezależnej od
# natywnej rozdzielczości źródła danych. Dlatego naslonecznienie_sekundy jest tu zawsze
# przeskalowywane do tego okna, niezależnie czy źródło jest 15-minutowe czy godzinowe.
REFERENCYJNY_KROK_NASLONECZNIENIA_S = 900.0


def wykryj_krok_natywny_s(df, kolumna_czasu='Timestamp'):
    """
    Wykrywa natywny krok czasowy danych [s] jako medianę odstępów między kolejnymi
    znacznikami czasu. Mediana (a nie np. pierwsza różnica) jest odporna na
    pojedyncze braki/duplikaty w danych źródłowych.
    """
    roznice_s = df[kolumna_czasu].diff().dropna().dt.total_seconds()
    krok_s = float(roznice_s.median())
    if not krok_s or krok_s <= 0:
        raise ValueError("Nie udało się wykryć natywnego kroku czasowego danych pogodowych (krok <= 0).")
    return krok_s


def wybierz_najzimniejsze_okno(sciezka_csv, dni):
    """
    Wyszukuje w RAW pliku (bez interpolacji do 1s - szybko, bo to tylko kilka
    tysięcy wierszy niezależnie od rozdzielczości) okno `dni` dni z najniższą
    średnią temperaturą powietrza. Pliki pogodowe są już wycięte do sezonu
    zimowego (XI-III), ale ten sezon nie jest jednorodnie zimny - np. początek
    listopada bywa jeszcze ciepły (kilka/kilkanaście °C) - branie okna "od
    początku pliku" przy skróconym przeglądzie mogłoby więc trafić na fragment,
    w którym ŻADEN algorytm nigdy nie musiał grzać, co czyni porównanie
    bezwartościowym. Szukanie najzimniejszego okna gwarantuje, że testujemy
    algorytmy w warunkach, w których faktycznie muszą podjąć decyzję.

    Zwraca (poczatek_ts, koniec_ts).
    """
    df = pd.read_csv(sciezka_csv, sep=',', usecols=lambda c: c in ('Timestamp', 'data_czas', 'temperatura_powietrza_C'))
    if 'data_czas' in df.columns:
        df = df.rename(columns={'data_czas': 'Timestamp'})
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df.sort_values('Timestamp').drop_duplicates(subset='Timestamp').set_index('Timestamp')

    srednia_kroczaca = df['temperatura_powietrza_C'].rolling(f'{dni}D').mean()
    koniec = srednia_kroczaca.idxmin()
    poczatek = koniec - pd.Timedelta(days=dni)
    return poczatek, koniec


def wczytaj_pogode_1s(sciezka_csv, max_dni=None, zakres_dat=None):
    """
    Wczytuje DOWOLNY plik CSV z danymi pogodowymi (kolumny: data_czas/Timestamp,
    temperatura_powietrza_C, punkt_rosy_C, opad_mm, wiatr_m_s[, naslonecznienie_sekundy])
    i sprowadza go do wspólnego kroku 1-sekundowego - niezależnie od tego, czy dane
    wejściowe są natywnie 15-minutowe, godzinowe, czy jakiekolwiek inne. Rozdzielczość
    źródła jest wykrywana automatycznie (mediana odstępów między znacznikami czasu),
    więc ta sama funkcja obsługuje dowolne nowe dane pogodowe bez zmian.

    zakres_dat: opcjonalnie krotka (poczatek_ts, koniec_ts) ograniczająca dane do
    konkretnego okna czasowego (obcięcie PRZED interpolacją do 1s) - patrz
    wybierz_najzimniejsze_okno(). Ma pierwszeństwo przed max_dni.

    max_dni: opcjonalnie ogranicza dane do PIERWSZYCH N dni pliku źródłowego.
    UWAGA: pliki sezonowe (XI-III) nie są jednorodnie zimne (początek listopada
    bywa jeszcze ciepły) - "pierwsze N dni" może więc trafić na fragment bez
    realnego mrozu/śniegu, w którym żaden algorytm nigdy nie musiał grzać. Do
    reprezentatywnego skrócenia okresu użyj raczej zakres_dat z
    wybierz_najzimniejsze_okno() - max_dni zostaje jako prosty, szybki wariant
    tam, gdzie ta reprezentatywność nie ma znaczenia (np. szybki smoke test).

    Przeliczenia zależne od wykrytego kroku źródłowego (żeby wynik był poprawny
    fizycznie niezależnie od rozdzielczości wejścia):
      - opad_mm: to SUMA opadu w oknie źródłowym (np. 15 min albo 1h) - dzielimy przez
        długość tego okna w sekundach, żeby dostać poprawną chwilową intensywność [mm/s].
      - naslonecznienie_sekundy: to liczba sekund słońca W OKNIE ŹRÓDŁOWYM (do 900 dla
        danych 15-minutowych, do 3600 dla godzinowych z Open-Meteo/ERA5-Land) -
        przeskalowujemy ją na wspólną skalę REFERENCYJNY_KROK_NASLONECZNIENIA_S, na
        której pracuje SnowClimPhysicalModel - bez tego dane godzinowe dawałyby
        ułamek nasłonecznienia nawet 4x za duży (i błędnie przycinany do 100% w modelu).
    """
    print(f"Wczytywanie danych pogodowych: {sciezka_csv}")
    df_zrodlo = pd.read_csv(sciezka_csv, sep=',')
    if 'data_czas' in df_zrodlo.columns:
        df_zrodlo.rename(columns={'data_czas': 'Timestamp'}, inplace=True)
    df_zrodlo['Timestamp'] = pd.to_datetime(df_zrodlo['Timestamp'])
    df_zrodlo = df_zrodlo.sort_values('Timestamp').drop_duplicates(subset='Timestamp')

    if zakres_dat is not None:
        poczatek, koniec = zakres_dat
        df_zrodlo = df_zrodlo[(df_zrodlo['Timestamp'] >= poczatek) & (df_zrodlo['Timestamp'] <= koniec)]
        print(f"Ograniczono do okna {poczatek} -> {koniec}.")
    elif max_dni is not None:
        granica = df_zrodlo['Timestamp'].iloc[0] + pd.Timedelta(days=max_dni)
        df_zrodlo = df_zrodlo[df_zrodlo['Timestamp'] < granica]
        print(f"Ograniczono do pierwszych {max_dni} dni pliku źródłowego.")

    krok_zrodlowy_s = wykryj_krok_natywny_s(df_zrodlo)
    print(f"Wykryty natywny krok danych źródłowych: {krok_zrodlowy_s:.0f} s "
          f"({krok_zrodlowy_s / 60:.1f} min) - interpolacja do 1 sekundy...")

    df_zrodlo = df_zrodlo.set_index('Timestamp')
    df_1s = df_zrodlo.resample('1s').asfreq()
    for col in ['temperatura_powietrza_C', 'punkt_rosy_C', 'wiatr_m_s']:
        df_1s[col] = df_1s[col].interpolate(method='linear')

    df_1s['opad_mm'] = df_1s['opad_mm'].ffill() / krok_zrodlowy_s

    if 'naslonecznienie_sekundy' in df_1s.columns:
        df_1s['naslonecznienie_sekundy'] = (
            df_1s['naslonecznienie_sekundy'].interpolate(method='linear')
            * (REFERENCYJNY_KROK_NASLONECZNIENIA_S / krok_zrodlowy_s)
        )

    df_1s.reset_index(inplace=True)
    print(f"Zagęszczono bazę. Liczba próbek 1-sekundowych: {len(df_1s)}\n")
    return df_1s


def przygotuj_modele_stanowe(dt=1.0):
    """Zwraca (A_wd,B_wd,C_wd,D_wd, A_hd,B_hd,C_hd,D_hd, punkty_opoznienia)."""
    sys_w = signal.tf2ss(TF_WEATHER.num, TF_WEATHER.den)
    A_wd, B_wd, C_wd, D_wd, _ = signal.cont2discrete(sys_w, dt, method='zoh')
    sys_h = signal.tf2ss(TF_HEATING.num, TF_HEATING.den)
    A_hd, B_hd, C_hd, D_hd, _ = signal.cont2discrete(sys_h, dt, method='zoh')
    punkty_opoznienia = int(round(L_H))
    return A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia


def wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt=1.0):
    """CRT (składowa czysto pogodowa, niezależna od grzania) dla całej serii AT naraz."""
    _, hrt_weather_all, _ = signal.dlsim((A_wd, B_wd, C_wd, D_wd, dt), at_array)
    return hrt_weather_all.flatten()


def _get_power(controller, row, method_name):
    result = getattr(controller, method_name)(row)
    if isinstance(result, tuple):
        return result[0]
    return result


def uruchom_kontroler(name, controller, method_name, df_1s, hrt_weather_all,
                       A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=1.0,
                       snow_reference_mm=None, power_reference_pct=None, print_progress=True):
    """
    Uruchamia pełną symulację (transmitancja grzania + SnowClimPhysicalModel)
    sterowaną przez podany kontroler, krok po kroku (1 s).

    snow_reference_mm / power_reference_pct: opcjonalne tablice (jeden element
    na krok symulacji) z grubością śniegu [mm] i mocą grzania [%] wyznaczonymi
    WCZEŚNIEJ przez algorytm_z_normy dla tych samych danych pogodowych. Jeśli
    podane, działają jako BEZPIECZNIK ("envelope protection", typowy wzorzec
    nadzoru bezpieczeństwa nad optymalizującym algorytmem): w każdym kroku, w
    którym istnieje śnieg (u nas LUB u normy), wymuszamy
    moc = max(moc_z_kontrolera, moc_normy_w_tym_kroku).

    Dlaczego "lustrzanie mocy", a nie prostsze "wymuś 100%, gdy dogonimy normę"?
    Obiekt ma bezwładność i opóźnienie transportowe (SOPDT, patrz autotest: L≈1194s,
    T1≈1121s, T2≈2451s) - reagowanie DOPIERO po zrównaniu się grubości śniegu z
    normą oznacza, że nasza szyna jest już "w tyle" cieplnie i przez pewien czas
    fizycznie nie da się dogonić normy, co prowadzi do przejściowego przekroczenia.
    Odpowiedź obiektu na moc grzania jest liniowa i monotoniczna (nieujemna
    odpowiedź impulsowa układu SOPDT), więc pilnowanie mocy >= moc_normy przez CAŁY
    czas trwania śniegu (a nie dopiero po przekroczeniu) gwarantuje - przy identycznej
    pogodzie/opadzie po obu stronach - że nasza grubość śniegu nie wyprzedzi normy.
    Kosztem jest to, że w okresach śniegu zużycie energii jest RÓWNE normie (nie
    gorsze, ale i niekoniecznie lepsze) - oszczędności zostają w pełni zachowane
    poza śniegiem (suchy mróz, ochrona przed -10°C).

    Zwraca: (df_historia, statystyki_dict, tablica_grubosci_sniegu_mm, tablica_mocy_pct)
    """
    if print_progress:
        print(f"--- Symulacja wariantu: {name} ---")
    ice_model = SnowClimPhysicalModel(latitude_deg=SUWALKI_LATITUDE_DEG)

    at_array = df_1s['temperatura_powietrza_C'].to_numpy()
    dew_array = df_1s['punkt_rosy_C'].to_numpy()
    wind_array = df_1s['wiatr_m_s'].to_numpy()
    solar_array = df_1s['naslonecznienie_sekundy'].to_numpy()
    precip_values = df_1s['opad_mm'].to_numpy()
    timestamps = df_1s['Timestamp'].tolist()

    x_h = np.zeros((A_hd.shape[0], 1))
    current_hrt = 0.7
    snow_depth_history = np.zeros(len(df_1s))
    power_history = np.zeros(len(df_1s))

    # Wyniki per krok jako PREALOKOWANE tablice numpy - NIE lista słowników
    # Pythona jak poprzednio. Na pełnym zakresie dat (~13 mln kroków/lokalizację)
    # lista słowników (9 pól, boxed floaty) mierzyła realnie ~9.4GB szczytowo NA
    # JEDNO zadanie (zmierzone bezpośrednio - stąd OOM na klastrze przy 48
    # równoległych procesach i za ciasno dobranym --mem). Tablice numpy dają
    # dokładnie te same wartości przy ułamku tej pamięci (8 tablic float64 x
    # 13M x 8B ≈ 830MB zamiast ~9GB).
    hist_at = np.empty(len(df_1s))
    hist_hrt = np.empty(len(df_1s))
    hist_crt = np.empty(len(df_1s))
    hist_moc = np.empty(len(df_1s))
    hist_snieg = np.empty(len(df_1s))
    hist_lod = np.empty(len(df_1s))
    hist_precip_1s = np.empty(len(df_1s))
    hist_snow_1s = np.empty(len(df_1s))

    total_steps = len(df_1s)
    t0 = time.time()
    last_print_time = t0
    PROGRESS_BAR_WIDTH = 30
    PROGRESS_MIN_INTERVAL_S = 0.2  # Odświeżamy pasek maks. 5x/s - płynnie, ale bez zalewania terminala.
    switches = 0
    prev_power = None
    zabezpieczen_uzytych = 0

    # Maska "ochrona aktywna": nie tylko GDY jest już śnieg (u nas lub u normy),
    # ale też z WYPRZEDZENIEM o punkty_opoznienia kroków przed nadejściem śniegu
    # u normy. Obiekt ma opóźnienie transportowe (SOPDT) - bez tego wyprzedzenia
    # nasz stan cieplny x_h wchodziłby w zdarzenie śniegowe z innym "zapasem
    # ciepła" niż norma (bo wcześniej mogliśmy grzać inaczej niż ona), co dawało
    # niewielkie, przejściowe przekroczenia tuż po starcie opadu. Ponieważ to
    # symulacja offline (znamy całą przyszłą trajektorię normy), możemy zacząć
    # lustrzenie z wyprzedzeniem i uniknąć tego efektu niemal całkowicie.
    ochrona_aktywna = None
    if snow_reference_mm is not None:
        ma_snieg_normy = snow_reference_mm > 0.01
        ochrona_aktywna = ma_snieg_normy.copy()
        if punkty_opoznienia > 0:
            ochrona_aktywna[:-punkty_opoznienia] |= ma_snieg_normy[punkty_opoznienia:]

    for index in range(total_steps):
        ts = timestamps[index]
        at_temp = at_array[index]
        dew_point = dew_array[index]
        precip_1s = precip_values[index]

        hrt_weather_comp = hrt_weather_all[index]
        calculated_rh = max(0.0, min(100.0, 100.0 - 5.0 * (at_temp - dew_point)))

        snow_val = precip_1s if at_temp <= 0.0 else 0.0
        rain_val = precip_1s if at_temp > 0.0 else 0.0

        # Grubość śniegu SPRZED tego kroku (ta sama wartość, która trafia do
        # kontrolera jako 'SNIEG_GRUBOSC_MM' i - dla algorytmu z normy - jest
        # zapisywana jako przyszła wartość referencyjna dla innych algorytmów).
        snow_depth_mm_pre = ice_model.snow_depth_m * 1000.0
        snow_depth_history[index] = snow_depth_mm_pre

        row = {
            'Timestamp': ts,
            'CRT_temp_niegrzana': hrt_weather_comp,
            'HRT_temp_grzana': current_hrt,
            'AT_temp_powietrza': at_temp,
            'RH_wilgotnosc_wzgledna': round(calculated_rh, 1),
            'PRES_cisnienie': 1009.0,
            'PRECIP_opad': rain_val,
            'SNOW_snieg': snow_val,
            'PWR_L1': 0.0,
            'PWR_L2': 0.0,
            'SNIEG_GRUBOSC_MM': snow_depth_mm_pre,
            'PUNKT_ROSY_C': float(dew_point),
            'WIATR_M_S': float(wind_array[index]),
        }

        power_percent = _get_power(controller, row, method_name)

        if snow_reference_mm is not None and (snow_depth_mm_pre > 0.01 or ochrona_aktywna[index]):
            moc_normy = power_reference_pct[index]
            if moc_normy > power_percent:
                power_percent = moc_normy
                zabezpieczen_uzytych += 1

        power_history[index] = power_percent

        # u_delayed czytany wstecz z power_history zamiast osobnej listy
        # u_history - power_history[index] jest już zapisane (linia wyżej), a
        # index - punkty_opoznienia < index był zapisany we wcześniejszym
        # obiegu pętli, więc odczyt jest bezpieczny i identyczny co do wartości.
        if index >= punkty_opoznienia:
            u_delayed = power_history[index - punkty_opoznienia] / 100.0
        else:
            u_delayed = 0.0

        x_h = A_hd @ x_h + B_hd * u_delayed
        hrt_heating_comp = float((C_hd @ x_h + D_hd * u_delayed)[0, 0])

        current_hrt = hrt_weather_comp + hrt_heating_comp
        current_crt = hrt_weather_comp

        snow_mm, ice_mm = ice_model.update(
            ts, at_temp, dew_point, wind_array[index], 1009.0,
            precip_1s * dt, solar_array[index], current_hrt, dt=dt,
        )

        if prev_power is not None and (power_percent > 0) != (prev_power > 0):
            switches += 1
        prev_power = power_percent

        hist_at[index] = at_temp
        hist_hrt[index] = current_hrt
        hist_crt[index] = current_crt
        hist_moc[index] = power_percent
        hist_snieg[index] = snow_mm
        hist_lod[index] = ice_mm
        hist_precip_1s[index] = precip_1s
        hist_snow_1s[index] = snow_val

        if print_progress:
            is_last = index == total_steps - 1
            now = time.time()
            if is_last or (now - last_print_time) >= PROGRESS_MIN_INTERVAL_S:
                last_print_time = now
                pct = (index + 1) / total_steps * 100
                elapsed = now - t0
                eta = elapsed / pct * (100 - pct) if pct > 0 else 0
                filled = int(PROGRESS_BAR_WIDTH * pct / 100)
                bar = '#' * filled + '-' * (PROGRESS_BAR_WIDTH - filled)
                print(f"\r  [{name}] [{bar}] {pct:6.2f}% | upłynęło {elapsed:7.1f}s | ETA {eta:7.1f}s",
                      end='\n' if is_last else '', flush=True)

    df_hist = pd.DataFrame({
        'Timestamp': timestamps,
        'AT': hist_at,
        'HRT': hist_hrt,
        'CRT': hist_crt,
        'Moc_procent': hist_moc,
        'Snieg_mm': hist_snieg,
        'Lod_mm': hist_lod,
        'PRECIP_opad_1s': hist_precip_1s,
        'SNOW_snieg_1s': hist_snow_1s,
    })
    df_hist['Energia_kWh_1s'] = (df_hist['Moc_procent'] / 100.0) * MOC_ZAMIANOWA_GRZALKI_KW * (dt / 3600.0)
    df_hist['Energia_kWh_skumulowana'] = df_hist['Energia_kWh_1s'].cumsum()

    stats = {
        'name': name,
        'energia_kwh': df_hist['Energia_kWh_1s'].sum(),
        'przelaczenia': switches,
        'dni': total_steps * dt / 86400.0,
        'srednia_moc_pct': df_hist['Moc_procent'].mean(),
        'max_snieg_mm': df_hist['Snieg_mm'].max(),
        'max_lod_mm': df_hist['Lod_mm'].max(),
        'godziny_ze_sniegiem': (df_hist['Snieg_mm'] > 0.0).sum() * dt / 3600.0,
        'min_hrt': df_hist['HRT'].min(),
        'max_hrt': df_hist['HRT'].max(),
        'zabezpieczen_normy_uzytych': zabezpieczen_uzytych,
    }
    if print_progress and snow_reference_mm is not None:
        print(f"  Bezpiecznik parytetu ze śniegiem z normy zadziałał {zabezpieczen_uzytych} razy.")

    return df_hist, stats, snow_depth_history, power_history


def przygotuj_do_zapisu(df_hist, co_n_sekund):
    """
    Zmniejsza rozdzielczość przebiegu (uśrednianie w oknach co_n_sekund) PRZED
    zapisem do CSV/wykresu. Statystyki (stats z uruchom_kontroler) są zawsze
    liczone WCZEŚNIEJ, z pełnej rozdzielczości 1s - to obniża TYLKO rozmiar
    zapisywanych przebiegów, nie dokładność żadnej statystyki. Współdzielona
    przez test_wszystkie_algorytmy_wszystkie_lokalizacje.py i
    test_wszystkie_rownolegle.py, żeby obie ścieżki (sekwencyjna i równoległa)
    zapisywały przebiegi identycznie.
    """
    if co_n_sekund <= 1:
        return df_hist
    return (df_hist.set_index('Timestamp')
                    .resample(f'{co_n_sekund}s').mean(numeric_only=True)
                    .reset_index())
