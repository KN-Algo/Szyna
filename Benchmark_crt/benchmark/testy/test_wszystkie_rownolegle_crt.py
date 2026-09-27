# testy/test_szyna_zimna_crt.py
#
# WARIANT test_wszystkie_rownolegle.py (oryginał NIETKNIĘTY, dalej obsługuje
# WSZYSTKIE 49 algorytmów na WSZYSTKICH lokalizacjach ze starą fizyką) - na
# życzenie użytkownika (2026-09-25): uruchamia TYLKO 4 nowe algorytmy
# ("wyznacznikiem jest szyna zimna", patrz Algorytmy/algorytm_z_zmienionym_na_crt/)
# na 10 NAJZIMNIEJSZYCH lokalizacjach, korzystając z NOWEGO rdzenia fizyki
# symulacja_fizyczna.py (transmitancje AT->CRT i moc->ΔHRT zidentyfikowane
# z realnych danych Wrocław Popowice - patrz Identyfikacja/notatki_identyfikacja/
# wyniki.md), zamiast starych stałych main_test.py.
#
# 10 najzimniejszych lokalizacji (ranking wg średniej temperatury powietrza w
# całym pliku, 2026-09-25 - patrz historia sesji): ojmiakon, jakuck, norylsk,
# old_crow, yellowknife, fairbanks, mohe, sodankyla, kiruna, harbin.
#
# Domyślnie dolicza też algorytm_z_normy (referencja/bezpiecznik, jak zawsze) -
# to piąty algorytm w wynikach, ale nie wlicza się do "4 nowych".
#
# Ta sama logika wznawiania/równoległości/CSV/Excela co w
# test_wszystkie_rownolegle.py (kod współdzielony przez kopię - nie importuje
# stamtąd, żeby obie ścieżki mogły się rozwijać niezależnie bez ryzyka
# rozjechania się przy przyszłych zmianach jednej z nich).
#
# Uruchomienie (z katalogu Benchmark/benchmark, z aktywnym środowiskiem
# z numpy/pandas/scipy/numba/openpyxl):
#   python testy/test_szyna_zimna_crt.py
#
# Na końcu Excel z generuj_excel_podsumowanie.py (nazwany domyślnie
# Podsumowanie_wynikow.xlsx) jest KOPIOWANY (nie przenoszony - oryginał
# zostaje, gdyby coś inne go czytało) do Podsumowanie_calkowite_zmienione_crt.xlsx
# w tym samym folderze.

import os
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmark/ (rodzic testy/)
sys.path.insert(0, BASE_DIR)  # symulacja_fizyczna.py mieszka w benchmark/
sys.path.insert(0, os.path.join(BASE_DIR, 'generatory_excel'))  # import generuj_excel_podsumowanie niżej
FOLDER_POGODA = os.path.join(BASE_DIR, "Pogoda_pomiary_15_minut")

# --- Domyślne 4 nowe algorytmy (patrz Algorytmy/algorytm_z_zmienionym_na_crt/) -
# nadpisywalne przez SZYNA_ALGORYTMY, jak w test_wszystkie_rownolegle.py. ---
_ALGORYTMY_CRT_DOMYSLNE = (
    'fuzzy_ryzyko_2v2_crt_progi,fuzzy_ryzyko_2v2_crt_pelny,'
    'fuzzy_ryzyko_2v2_opad_crt_progi,fuzzy_ryzyko_2v2_opad_crt_pelny'
)
_algorytmy_env = os.environ.get('SZYNA_ALGORYTMY', _ALGORYTMY_CRT_DOMYSLNE)
ALGORYTMY_FILTR = {a.strip() for a in _algorytmy_env.split(',') if a.strip()}

# --- Domyślnie 10 najzimniejszych lokalizacji (patrz nagłówek pliku) -
# nadpisywalne przez SZYNA_LOKALIZACJE. ---
_LOKALIZACJE_10_NAJZIMNIEJSZYCH = (
    'ojmiakon_60min_2025,jakuck_60min_2025,norylsk_60min_2025,old_crow_60min_2025,'
    'yellowknife_60min_2025,fairbanks_60min_2025,mohe_60min_2025,sodankyla_60min_2025,'
    'kiruna_60min_2025,harbin_60min_2025'
)
_lokalizacje_env = os.environ.get('SZYNA_LOKALIZACJE', _LOKALIZACJE_10_NAJZIMNIEJSZYCH)
LOKALIZACJE_FILTR = {l.strip() for l in _lokalizacje_env.split(',') if l.strip()}

FOLDER_WYNIKOW = os.environ.get(
    'SZYNA_FOLDER_WYNIKOW', os.path.join(BASE_DIR, "wyniki", "przeglad_szyna_zimna_crt"))
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)
FOLDER_CSV_SZCZEGOLOWE = os.environ.get('SZYNA_FOLDER_CSV_SZCZEGOLOWE', FOLDER_WYNIKOW)
os.makedirs(FOLDER_CSV_SZCZEGOLOWE, exist_ok=True)

NAZWA_EXCEL_FINALNY = 'Podsumowanie_calkowite_zmienione_crt.xlsx'

MAX_SWITCHES_PER_DAY = int(os.environ.get('SZYNA_MAX_PRZELACZEN_DZIEN', '100'))
NAZWA_ALGORYTMU_NORMY = 'algorytm_z_normy'

_max_dni_env = os.environ.get('SZYNA_MAX_DNI')
MAX_DNI_NA_LOKALIZACJE = int(_max_dni_env) if _max_dni_env else None

ZAPISZ_CO_N_SEKUND = int(os.environ.get('SZYNA_ZAPISZ_CO_N_SEKUND', '600'))

_watkow_env = os.environ.get('SZYNA_LICZBA_WATKOW')
LICZBA_WATKOW_NADPISANIE = int(_watkow_env) if _watkow_env else None

SCENARIUSZ_ETYKIETA = 'nominal_crt'  # stała etykieta w wynikach - odróżnia ten przebieg od starej fizyki
ZAPISZ_CSV_SZCZEGOLOWE = os.environ.get('SZYNA_ZAPISZ_CSV_SZCZEGOLOWE', '1') != '0'
KROK_SYMULACJI_S = float(os.environ.get('SZYNA_KROK_S', '10.0'))
WZNAWIAJ_PRZERWANE = os.environ.get('SZYNA_WZNOW', '1') != '0'


def wykryj_liczbe_watkow():
    if LICZBA_WATKOW_NADPISANIE:
        print(f"Liczba wątków nadpisana ręcznie: {LICZBA_WATKOW_NADPISANIE}")
        return LICZBA_WATKOW_NADPISANIE
    for zmienna in ('SLURM_CPUS_PER_TASK', 'SLURM_JOB_CPUS_PER_NODE', 'PBS_NP', 'NSLOTS', 'LSB_DJOB_NUMPROC'):
        wartosc = os.environ.get(zmienna)
        if wartosc:
            try:
                liczba = int(str(wartosc).split('(')[0].split(',')[0])
                if liczba > 0:
                    print(f"Wykryto limit rdzeni ze zmiennej {zmienna}={wartosc} -> {liczba} procesów")
                    return liczba
            except ValueError:
                continue
    try:
        liczba = len(os.sched_getaffinity(0))
        print(f"Wykryto {liczba} procesów przez os.sched_getaffinity (limit cgroup/kontenera)")
        return liczba
    except AttributeError:
        liczba = os.cpu_count() or 1
        print(f"Wykryto {liczba} procesów przez os.cpu_count()")
        return liczba


def znajdz_pliki_pogodowe():
    return {
        os.path.splitext(nazwa_pliku)[0]: os.path.join(FOLDER_POGODA, nazwa_pliku)
        for nazwa_pliku in sorted(os.listdir(FOLDER_POGODA))
        if nazwa_pliku.endswith('.csv')
    }


def _rozgrzej_numba():
    print("Rozgrzewanie kompilacji numba (JIT) w procesie głównym...")
    sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
    import numpy as np
    import symulacja_fizyczna as fiz
    from rejestr_algorytmow import stworz_kontroler

    n = 2000
    dt = 1.0
    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(dt)
    at_array = np.full(n, -5.0)
    hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)
    df_1s = pd.DataFrame({
        'Timestamp': pd.date_range('2024-01-01', periods=n, freq='1s'),
        'temperatura_powietrza_C': at_array,
        'punkt_rosy_C': at_array - 2.0,
        'wiatr_m_s': np.full(n, 2.0),
        'opad_mm': np.zeros(n),
        'naslonecznienie_sekundy': np.zeros(n),
    })
    kontroler, metoda = stworz_kontroler('fuzzy_ryzyko_2v2_crt_pelny', max_switches_per_day=20)
    fiz.uruchom_kontroler('rozgrzewka', kontroler, metoda, df_1s, hrt_weather_all,
                           A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt, print_progress=False)
    print("Gotowe.\n")


def przetworz_kombinacje(nazwa_lokalizacji, sciezka_csv, nazwa_algorytmu):
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
        import symulacja_fizyczna as fiz
        from rejestr_algorytmow import stworz_kontroler, podlega_bezpiecznikowi

        zakres_dat = None
        if MAX_DNI_NA_LOKALIZACJE is not None:
            zakres_dat = fiz.wybierz_najzimniejsze_okno(sciezka_csv, MAX_DNI_NA_LOKALIZACJE)

        dt = KROK_SYMULACJI_S
        df_1s = fiz.wczytaj_pogode_1s(sciezka_csv, zakres_dat=zakres_dat, dt=dt)
        A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(dt)
        at_array = df_1s['temperatura_powietrza_C'].to_numpy()
        hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)

        kontroler_normy, metoda_normy = stworz_kontroler(NAZWA_ALGORYTMU_NORMY, max_switches_per_day=MAX_SWITCHES_PER_DAY)
        df_normy, stats_normy, snow_ref, power_ref = fiz.uruchom_kontroler(
            NAZWA_ALGORYTMU_NORMY, kontroler_normy, metoda_normy, df_1s, hrt_weather_all,
            A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt, print_progress=False,
        )

        if nazwa_algorytmu == NAZWA_ALGORYTMU_NORMY:
            df_wynik, stats = df_normy, stats_normy
        else:
            czy_bezpiecznik = podlega_bezpiecznikowi(nazwa_algorytmu)
            kontroler, metoda = stworz_kontroler(nazwa_algorytmu, max_switches_per_day=MAX_SWITCHES_PER_DAY)
            df_wynik, stats, _, _ = fiz.uruchom_kontroler(
                nazwa_algorytmu, kontroler, metoda, df_1s, hrt_weather_all,
                A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt,
                snow_reference_mm=snow_ref if czy_bezpiecznik else None,
                power_reference_pct=power_ref if czy_bezpiecznik else None,
                print_progress=False,
            )

        stats = dict(stats)
        stats['lokalizacja'] = nazwa_lokalizacji
        stats['scenariusz'] = SCENARIUSZ_ETYKIETA
        df_zapis = fiz.przygotuj_do_zapisu(df_wynik, ZAPISZ_CO_N_SEKUND)
        if ZAPISZ_CSV_SZCZEGOLOWE:
            df_zapis.to_csv(
                os.path.join(FOLDER_CSV_SZCZEGOLOWE, f"{nazwa_lokalizacji}_{nazwa_algorytmu}.csv"), index=False)

        return nazwa_lokalizacji, nazwa_algorytmu, stats, None
    except Exception:
        return nazwa_lokalizacji, nazwa_algorytmu, None, traceback.format_exc()


def main():
    liczba_watkow = wykryj_liczbe_watkow()
    _rozgrzej_numba()

    pliki_pogodowe = {k: v for k, v in znajdz_pliki_pogodowe().items() if k in LOKALIZACJE_FILTR}
    brakujace_lok = LOKALIZACJE_FILTR - set(pliki_pogodowe)
    if brakujace_lok:
        print(f"UWAGA: nie znaleziono plików pogodowych dla: {sorted(brakujace_lok)} - pomijam je.")

    sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
    from rejestr_algorytmow import ALGORYTMY
    nazwy_algorytmow = [a for a in ALGORYTMY if a in ALGORYTMY_FILTR]
    brakujace_alg = ALGORYTMY_FILTR - set(nazwy_algorytmow)
    if brakujace_alg:
        print(f"UWAGA: nie znaleziono w rejestrze algorytmów: {sorted(brakujace_alg)} - pomijam je.")
    if NAZWA_ALGORYTMU_NORMY not in nazwy_algorytmow:
        nazwy_algorytmow.append(NAZWA_ALGORYTMU_NORMY)  # zawsze dolicz normę jako punkt odniesienia

    print(f"Fizyka: symulacja_fizyczna.py (transmitancje z realnych danych Wrocław Popowice).")
    print(f"Lokalizacje ({len(pliki_pogodowe)}): {sorted(pliki_pogodowe)}")
    print(f"Algorytmy ({len(nazwy_algorytmow)}): {nazwy_algorytmow}")
    if MAX_DNI_NA_LOKALIZACJE is not None:
        print(f"UWAGA: SZYNA_MAX_DNI={MAX_DNI_NA_LOKALIZACJE} - ograniczony zakres dat (tryb testowy).")

    zadania = [
        (lokalizacja, sciezka, algorytm)
        for lokalizacja, sciezka in pliki_pogodowe.items()
        for algorytm in nazwy_algorytmow
    ]
    print(f"\nŁącznie {len(zadania)} zadań ({len(pliki_pogodowe)} lokalizacji x {len(nazwy_algorytmow)} "
          f"algorytmów) na {liczba_watkow} procesach.\n")

    wyniki = []
    liczba_zadan_ogolem = len(zadania)
    sciezka_zbiorczy = os.path.join(FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.csv")
    if WZNAWIAJ_PRZERWANE and os.path.exists(sciezka_zbiorczy):
        try:
            df_poprzedni = pd.read_csv(sciezka_zbiorczy)
            wyniki = df_poprzedni.to_dict('records')
            gotowe_pary = {(w['lokalizacja'], w['name']) for w in wyniki if 'lokalizacja' in w and 'name' in w}
            liczba_przed = len(zadania)
            zadania = [z for z in zadania if (z[0], z[2]) not in gotowe_pary]
            print(f"WZNOWIENIE: znaleziono {len(gotowe_pary)} gotowych zadań z poprzedniego przebiegu - "
                  f"liczą się tylko brakujące {len(zadania)}/{liczba_przed}.\n")
        except Exception:
            print(f"UWAGA: nie udało się wczytać {sciezka_zbiorczy} do wznowienia - liczę wszystko od zera.\n")
            wyniki = []

    if zadania:
        bledy = []
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=liczba_watkow) as executor:
            futures = {executor.submit(przetworz_kombinacje, lok, sciezka, alg): (lok, alg)
                       for lok, sciezka, alg in zadania}
            zakonczone = 0
            for future in as_completed(futures):
                nazwa_lokalizacji, nazwa_algorytmu, stats, blad = future.result()
                zakonczone += 1
                elapsed_min = (time.time() - t0) / 60.0
                if blad is not None:
                    bledy.append((nazwa_lokalizacji, nazwa_algorytmu, blad))
                    print(f"[{zakonczone}/{len(zadania)}] BŁĄD {nazwa_lokalizacji}/{nazwa_algorytmu} "
                          f"(upłynęło {elapsed_min:.1f} min):\n{blad}")
                else:
                    wyniki.append(stats)
                    print(f"[{zakonczone}/{len(zadania)}] OK {nazwa_lokalizacji}/{nazwa_algorytmu} "
                          f"energia={stats['energia_kwh']:.1f} kWh (upłynęło {elapsed_min:.1f} min)")
                pd.DataFrame(wyniki).to_csv(sciezka_zbiorczy, index=False)

        calkowity_czas_min = (time.time() - t0) / 60.0
        print(f"\nZakończono w {calkowity_czas_min:.1f} min. Sukcesy: {len(wyniki)}/{liczba_zadan_ogolem}. "
              f"Błędy w TYM przebiegu: {len(bledy)}.")
        if bledy:
            print("Lokalizacje/algorytmy zakończone błędem:")
            for lok, alg, _ in bledy:
                print(f"  - {lok} / {alg}")
    else:
        print("Wszystkie zadania już wykonane w poprzednim przebiegu - nic do policzenia.")

    if not wyniki:
        print("Brak wyników - wszystkie zadania zakończyły się błędem.")
        return

    df_wszystkie = pd.DataFrame(wyniki)
    kolumny = ['lokalizacja', 'name', 'scenariusz', 'energia_kwh', 'przelaczenia', 'max_snieg_mm', 'max_lod_mm',
               'max_hrt', 'min_hrt', 'srednia_moc_pct', 'godziny_ze_sniegiem', 'zabezpieczen_normy_uzytych',
               'dni', 'flops_rzeczywiste', 'iae', 'ise', 'itae', 'kara_bezpieczenstwa', 'epizody_ponizej_floor',
               'epizody_powyzej_45c_hrt', 'czas_powyzej_45c_hrt_s']
    kolumny = [k for k in kolumny if k in df_wszystkie.columns]
    kolumny += [k for k in df_wszystkie.columns if k not in kolumny]
    df_wszystkie = df_wszystkie[kolumny]
    df_wszystkie.to_csv(sciezka_zbiorczy, index=False)

    try:
        import generuj_excel_podsumowanie
        os.environ['SZYNA_FOLDER_WYNIKOW'] = FOLDER_WYNIKOW  # generuj_excel_podsumowanie czyta stąd
        generuj_excel_podsumowanie.main()
        sciezka_excel_oryginalny = os.path.join(FOLDER_WYNIKOW, "Podsumowanie_wynikow.xlsx")
        sciezka_excel_finalny = os.path.join(FOLDER_WYNIKOW, NAZWA_EXCEL_FINALNY)
        if os.path.exists(sciezka_excel_oryginalny):
            shutil.copyfile(sciezka_excel_oryginalny, sciezka_excel_finalny)
            print(f"\nSkopiowano Excel do: {sciezka_excel_finalny}")
    except Exception:
        print(f"\n!!! BŁĄD przy generowaniu {NAZWA_EXCEL_FINALNY} - CSV jest bezpieczny, "
              "spróbuj uruchomić generatory_excel/generuj_excel_podsumowanie.py osobno !!!")
        traceback.print_exc()

    print(f"\nGotowe. Wszystkie pliki w folderze: {FOLDER_WYNIKOW}")


if __name__ == '__main__':
    main()
