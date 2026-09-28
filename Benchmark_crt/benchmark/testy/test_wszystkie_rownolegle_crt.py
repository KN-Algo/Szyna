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
import re
import shutil
import sys
from datetime import datetime
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

# Jeden proces = jeden rdzeń. Bez tego każdy z N procesów roboczych może odpalić własne
# wątki BLAS/OpenMP (numpy/scipy) i przy 128 procesach na 128 rdzeniach dochodzi do
# przeciążenia (tysiące wątków walczących o rdzenie) - wolniej, nie szybciej. MUSI być
# ustawione PRZED importem numpy/pandas; setdefault pozwala nadpisać z zewnątrz.
for _zmienna_watkow in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                        'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ.setdefault(_zmienna_watkow, '1')

import numpy as np
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
# Wartość WSZYSTKIE = cały rejestr algorytmów (None = bez filtra).
ALGORYTMY_FILTR = (None if _algorytmy_env.strip().upper() == 'WSZYSTKIE'
                   else {a.strip() for a in _algorytmy_env.split(',') if a.strip()})

# --- Domyślnie 10 najzimniejszych lokalizacji (patrz nagłówek pliku) -
# nadpisywalne przez SZYNA_LOKALIZACJE. ---
_LOKALIZACJE_10_NAJZIMNIEJSZYCH = (
    'ojmiakon_60min_2025,jakuck_60min_2025,norylsk_60min_2025,old_crow_60min_2025,'
    'yellowknife_60min_2025,fairbanks_60min_2025,mohe_60min_2025,sodankyla_60min_2025,'
    'kiruna_60min_2025,harbin_60min_2025'
)
_lokalizacje_env = os.environ.get('SZYNA_LOKALIZACJE', _LOKALIZACJE_10_NAJZIMNIEJSZYCH)
# Wartość WSZYSTKIE = wszystkie pliki z Pogoda_pomiary_15_minut/ (None = bez filtra).
LOKALIZACJE_FILTR = (None if _lokalizacje_env.strip().upper() == 'WSZYSTKIE'
                     else {l.strip() for l in _lokalizacje_env.split(',') if l.strip()})

# Folder wyników nosi w nazwie datę i godzinę uruchomienia (na życzenie użytkownika,
# 2026-09-28), np. przeglad_szyna_zimna_crt_2026-09-28_10-40. Jeśli podana nazwa
# (SZYNA_FOLDER_WYNIKOW) JUŻ kończy się takim znacznikiem, jest używana bez zmian -
# tak wznawia się przerwany przebieg (podaj pełną nazwę istniejącego folderu z datą).
_FOLDER_WYNIKOW_BAZA = os.environ.get(
    'SZYNA_FOLDER_WYNIKOW', os.path.join(BASE_DIR, "wyniki", "przeglad_szyna_zimna_crt"))
if re.search(r'_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}$', _FOLDER_WYNIKOW_BAZA.rstrip('\\/')):
    FOLDER_WYNIKOW = _FOLDER_WYNIKOW_BAZA
else:
    FOLDER_WYNIKOW = f"{_FOLDER_WYNIKOW_BAZA.rstrip(chr(92) + '/')}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}"
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)
# Procesy robocze (ProcessPoolExecutor, Windows: spawn) importują ten moduł od nowa -
# przypięcie pełnej nazwy w środowisku sprawia, że dziedziczą TEN SAM folder z datą
# (inaczej po zmianie minuty utworzyłyby własny, inny folder).
os.environ['SZYNA_FOLDER_WYNIKOW'] = FOLDER_WYNIKOW
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

# --- Podział pracy na wiele węzłów klastra (SLURM job array) ---
# Jeden węzeł to max ~128 rdzeni. Żeby użyć więcej, zleć N węzłów jako tablicę zadań:
# każdy dostaje SZYNA_SHARD_INDEKS=0..N-1 i SZYNA_SHARD_LICZBA=N, liczy swój wycinek zadań
# do WSPÓLNEGO folderu wyników (wspólny dysk), a osobne zadanie scalające
# (SZYNA_TYLKO_SCAL=1) składa części i generuje Excel. Domyślnie 0/1 = zwykły przebieg.
SHARD_LICZBA = max(1, int(os.environ.get('SZYNA_SHARD_LICZBA', '1')))
SHARD_INDEKS = int(os.environ.get('SZYNA_SHARD_INDEKS', '0'))
TYLKO_SCAL = os.environ.get('SZYNA_TYLKO_SCAL', '0') == '1'
# Ile sekund proces roboczy czeka na normę-referencję liczoną przez INNY węzeł, zanim
# policzy ją sam (zabezpieczenie przed zawieszeniem, gdy tamten węzeł padnie).
CZAS_OCZEKIWANIA_REF_S = float(os.environ.get('SZYNA_CZEKAJ_NA_REF_S', '180'))
# Referencje normy to ~50 MB na lokalizację przy pełnym sezonie (~2 GB dla 44) - na klastrze
# idą razem z ciężkimi CSV (SZYNA_FOLDER_CSV_SZCZEGOLOWE, np. dysk PD), nie do katalogu domowego.
FOLDER_REF_NORMY = os.path.join(FOLDER_CSV_SZCZEGOLOWE, '_referencje_normy')

# Orientacyjny koszt zadania (względny) do kolejności "najdłuższe najpierw" (LPT) - dzięki
# temu ciężkie MPC/PID startują na początku, a lekkie fuzzy dobijają ogon i wszystkie
# rdzenie kończą mniej więcej razem. Pomiary z klastra (poprzedni przegląd): norma ~70 s,
# fuzzy ~180 s, PID ~490 s; MPC dodatkowo kilka razy wolniejsze od PID.
_KOSZT_WEDLUG_SLOWA = (('mpc', 8.0), ('kaskad', 5.0), ('pid', 4.0), ('adrc', 4.0), ('nauka', 3.0),
                       ('fuzzy', 2.0), ('norma', 1.0), ('histereza', 1.0))


def koszt_zadania(nazwa_algorytmu):
    nazwa = nazwa_algorytmu.lower()
    for slowo, koszt in _KOSZT_WEDLUG_SLOWA:
        if slowo in nazwa:
            return koszt
    return 3.0


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


def _sciezka_referencji(nazwa_lokalizacji):
    # Klucz zawiera krok i zakres dat - referencja liczona dla innych parametrów nie może
    # być cicho użyta (folder jest dodatkowo per przebieg, ale to tania asekuracja).
    klucz = f"{nazwa_lokalizacji}_dt{KROK_SYMULACJI_S:g}_dni{MAX_DNI_NA_LOKALIZACJE}"
    return os.path.join(FOLDER_REF_NORMY, f"{klucz}.npz")


def _zapisz_referencje(nazwa_lokalizacji, snow_ref, power_ref):
    # Zapis atomowy (plik tymczasowy + os.replace): drugi węzeł/proces czytający w tym
    # samym czasie widzi albo cały plik, albo żaden - nigdy połowę.
    sciezka = _sciezka_referencji(nazwa_lokalizacji)
    os.makedirs(FOLDER_REF_NORMY, exist_ok=True)
    tymczasowy = f"{sciezka}.{os.getpid()}.tmp.npz"
    np.savez(tymczasowy, snow=np.asarray(snow_ref), power=np.asarray(power_ref))
    os.replace(tymczasowy, sciezka)


def _wczytaj_referencje(nazwa_lokalizacji, czekaj_s=0.0):
    sciezka = _sciezka_referencji(nazwa_lokalizacji)
    deadline = time.time() + czekaj_s
    while True:
        if os.path.exists(sciezka):
            try:
                with np.load(sciezka) as dane:
                    return dane['snow'], dane['power']
            except Exception:
                pass  # plik w trakcie podmiany / uszkodzony - spróbuj jeszcze raz albo policz sam
        if time.time() >= deadline:
            return None
        time.sleep(5.0)


def _przygotuj_symulacje(sciezka_csv):
    sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
    import symulacja_fizyczna as fiz

    zakres_dat = None
    if MAX_DNI_NA_LOKALIZACJE is not None:
        zakres_dat = fiz.wybierz_najzimniejsze_okno(sciezka_csv, MAX_DNI_NA_LOKALIZACJE)

    dt = KROK_SYMULACJI_S
    df_1s = fiz.wczytaj_pogode_1s(sciezka_csv, zakres_dat=zakres_dat, dt=dt)
    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(dt)
    at_array = df_1s['temperatura_powietrza_C'].to_numpy()
    hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)
    return fiz, df_1s, hrt_weather_all, (A_hd, B_hd, C_hd, D_hd, punkty_opoznienia), dt


def _uruchom_norme(fiz, df_1s, hrt_weather_all, modele_hd, dt):
    from rejestr_algorytmow import stworz_kontroler
    A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = modele_hd
    kontroler_normy, metoda_normy = stworz_kontroler(NAZWA_ALGORYTMU_NORMY, max_switches_per_day=MAX_SWITCHES_PER_DAY)
    return fiz.uruchom_kontroler(
        NAZWA_ALGORYTMU_NORMY, kontroler_normy, metoda_normy, df_1s, hrt_weather_all,
        A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt, print_progress=False,
    )


def przetworz_kombinacje(nazwa_lokalizacji, sciezka_csv, nazwa_algorytmu):
    """Jedno zadanie (lokalizacja, algorytm).

    Norma (algorytm_z_normy) jest liczona RAZ na lokalizację (faza 1) i jej trajektoria
    (śnieg + moc) trafia do pliku .npz; pozostałe algorytmy tylko ją wczytują, zamiast
    liczyć normę od nowa w każdym zadaniu (wcześniej ok. 15% czasu CPU szło na to samo
    obliczenie powtarzane ~50 razy na lokalizację). Algorytmy bez bezpiecznika w ogóle
    nie potrzebują normy. Gdy pliku brak (inny węzeł nie zdążył / padł), zadanie liczy
    normę samo - wynik jest ten sam, tylko drożej.
    """
    try:
        t_start_zadania = time.time()
        fiz, df_1s, hrt_weather_all, modele_hd, dt = _przygotuj_symulacje(sciezka_csv)
        A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = modele_hd
        from rejestr_algorytmow import stworz_kontroler, podlega_bezpiecznikowi

        if nazwa_algorytmu == NAZWA_ALGORYTMU_NORMY:
            df_wynik, stats, snow_ref, power_ref = _uruchom_norme(fiz, df_1s, hrt_weather_all, modele_hd, dt)
            _zapisz_referencje(nazwa_lokalizacji, snow_ref, power_ref)
        else:
            czy_bezpiecznik = podlega_bezpiecznikowi(nazwa_algorytmu)
            snow_ref = power_ref = None
            if czy_bezpiecznik:
                ref = _wczytaj_referencje(nazwa_lokalizacji, czekaj_s=CZAS_OCZEKIWANIA_REF_S if SHARD_LICZBA > 1 else 0.0)
                if ref is None:
                    _, _, snow_ref, power_ref = _uruchom_norme(fiz, df_1s, hrt_weather_all, modele_hd, dt)
                    _zapisz_referencje(nazwa_lokalizacji, snow_ref, power_ref)
                else:
                    snow_ref, power_ref = ref
            kontroler, metoda = stworz_kontroler(nazwa_algorytmu, max_switches_per_day=MAX_SWITCHES_PER_DAY)
            df_wynik, stats, _, _ = fiz.uruchom_kontroler(
                nazwa_algorytmu, kontroler, metoda, df_1s, hrt_weather_all,
                A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt,
                snow_reference_mm=snow_ref,
                power_reference_pct=power_ref,
                print_progress=False,
            )

        stats = dict(stats)
        stats['lokalizacja'] = nazwa_lokalizacji
        stats['scenariusz'] = SCENARIUSZ_ETYKIETA
        # Czas rdzenia zużyty na to zadanie (sekundy) - realny koszt CPU do planowania budżetu.
        stats['czas_zadania_s'] = round(time.time() - t_start_zadania, 1)
        df_zapis =fiz.przygotuj_do_zapisu(df_wynik, ZAPISZ_CO_N_SEKUND)
        if ZAPISZ_CSV_SZCZEGOLOWE:
            df_zapis.to_csv(
                os.path.join(FOLDER_CSV_SZCZEGOLOWE, f"{nazwa_lokalizacji}_{nazwa_algorytmu}.csv"), index=False)

        return nazwa_lokalizacji, nazwa_algorytmu, stats, None
    except Exception:
        return nazwa_lokalizacji, nazwa_algorytmu, None, traceback.format_exc()


def _pliki_zbiorcze():
    return sorted(
        os.path.join(FOLDER_WYNIKOW, n) for n in os.listdir(FOLDER_WYNIKOW)
        if n.startswith('PRZEGLAD_ZBIORCZY') and n.endswith('.csv'))


def _wczytaj_wyniki_z_plikow(sciezki):
    ramki = []
    for sciezka in sciezki:
        try:
            ramki.append(pd.read_csv(sciezka))
        except Exception:
            print(f"UWAGA: nie udało się wczytać {sciezka} - pomijam ten plik.")
    if not ramki:
        return []
    df = pd.concat(ramki, ignore_index=True)
    if 'lokalizacja' in df.columns and 'name' in df.columns:
        df = df.drop_duplicates(subset=['lokalizacja', 'name'], keep='last')
    return df.to_dict('records')


def _posortuj_kolumny(df_wszystkie):
    kolumny = ['lokalizacja', 'name', 'scenariusz', 'energia_kwh', 'przelaczenia', 'max_snieg_mm', 'max_lod_mm',
               'max_hrt', 'min_hrt', 'srednia_moc_pct', 'godziny_ze_sniegiem', 'zabezpieczen_normy_uzytych',
               'dni', 'flops_rzeczywiste', 'iae', 'ise', 'itae', 'kara_bezpieczenstwa', 'epizody_ponizej_floor',
               'epizody_powyzej_45c_hrt', 'czas_powyzej_45c_hrt_s']
    kolumny = [k for k in kolumny if k in df_wszystkie.columns]
    kolumny += [k for k in df_wszystkie.columns if k not in kolumny]
    return df_wszystkie[kolumny]


def _generuj_excel():
    try:
        # Zmienna MUSI być ustawiona PRZED importem - generator czyta ją w momencie importu
        # (wcześniej kolejność była odwrotna, przez co szukał CSV w domyślnym, złym folderze).
        os.environ['SZYNA_FOLDER_WYNIKOW'] = FOLDER_WYNIKOW
        os.environ['SZYNA_FOLDER_CSV_SZCZEGOLOWE'] = FOLDER_CSV_SZCZEGOLOWE
        import generuj_excel_podsumowanie
        generuj_excel_podsumowanie.main()
        # Generator zapisuje plik ze znacznikiem daty i godziny w nazwie (patrz
        # generuj_excel_podsumowanie.ZNACZNIK_CZASU) - kopia finalna dostaje ten sam znacznik.
        sciezka_excel_oryginalny = generuj_excel_podsumowanie.SCIEZKA_XLSX
        sciezka_excel_finalny = os.path.join(
            FOLDER_WYNIKOW, NAZWA_EXCEL_FINALNY.replace(
                '.xlsx', f'_{generuj_excel_podsumowanie.ZNACZNIK_CZASU}.xlsx'))
        if os.path.exists(sciezka_excel_oryginalny):
            shutil.copyfile(sciezka_excel_oryginalny, sciezka_excel_finalny)
            print(f"\nSkopiowano Excel do: {sciezka_excel_finalny}")
    except Exception:
        print(f"\n!!! BŁĄD przy generowaniu {NAZWA_EXCEL_FINALNY} - CSV jest bezpieczny, "
              "spróbuj uruchomić generatory_excel/generuj_excel_podsumowanie.py osobno !!!")
        traceback.print_exc()


def scal_czesci_i_wygeneruj_excel():
    """Tryb SZYNA_TYLKO_SCAL=1: składa PRZEGLAD_ZBIORCZY_czesc_*.csv z wszystkich węzłów."""
    pliki = _pliki_zbiorcze()
    print(f"Scalanie {len(pliki)} plików zbiorczych w {FOLDER_WYNIKOW}")
    wyniki = _wczytaj_wyniki_z_plikow(pliki)
    if not wyniki:
        print("Brak wyników do scalenia.")
        return
    df = _posortuj_kolumny(pd.DataFrame(wyniki))
    df.to_csv(os.path.join(FOLDER_WYNIKOW, 'PRZEGLAD_ZBIORCZY.csv'), index=False)
    print(f"Scalono: {len(df)} wyników ({df['lokalizacja'].nunique()} lokalizacji x "
          f"{df['name'].nunique()} algorytmów).")
    _generuj_excel()
    print(f"\nGotowe. Wszystkie pliki w folderze: {FOLDER_WYNIKOW}")


def main():
    if TYLKO_SCAL:
        scal_czesci_i_wygeneruj_excel()
        return

    liczba_watkow = wykryj_liczbe_watkow()
    if os.name == 'nt':
        liczba_watkow = min(liczba_watkow, 61)  # twardy limit ProcessPoolExecutor na Windows
    _rozgrzej_numba()

    pliki_pogodowe = {k: v for k, v in znajdz_pliki_pogodowe().items()
                      if LOKALIZACJE_FILTR is None or k in LOKALIZACJE_FILTR}
    brakujace_lok = (LOKALIZACJE_FILTR or set()) - set(pliki_pogodowe)
    if brakujace_lok:
        print(f"UWAGA: nie znaleziono plików pogodowych dla: {sorted(brakujace_lok)} - pomijam je.")

    sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
    from rejestr_algorytmow import ALGORYTMY
    nazwy_algorytmow = [a for a in ALGORYTMY if ALGORYTMY_FILTR is None or a in ALGORYTMY_FILTR]
    brakujace_alg = (ALGORYTMY_FILTR or set()) - set(nazwy_algorytmow)
    if brakujace_alg:
        print(f"UWAGA: nie znaleziono w rejestrze algorytmów: {sorted(brakujace_alg)} - pomijam je.")
    if NAZWA_ALGORYTMU_NORMY not in nazwy_algorytmow:
        nazwy_algorytmow.append(NAZWA_ALGORYTMU_NORMY)  # zawsze dolicz normę jako punkt odniesienia

    print(f"Fizyka: symulacja_fizyczna.py (transmitancje z realnych danych Wrocław Popowice).")
    print(f"Lokalizacje ({len(pliki_pogodowe)}): {sorted(pliki_pogodowe)}")
    print(f"Algorytmy ({len(nazwy_algorytmow)}): {nazwy_algorytmow}")
    if MAX_DNI_NA_LOKALIZACJE is not None:
        print(f"UWAGA: SZYNA_MAX_DNI={MAX_DNI_NA_LOKALIZACJE} - ograniczony zakres dat (tryb testowy).")

    # --- Przydział zadań. Wszystkie węzły liczą TĘ SAMĄ pełną listę w tej samej kolejności
    # (deterministycznie), więc każdy wie, które zadania są jego - bez komunikacji między
    # węzłami. Przydział robimy PRZED odfiltrowaniem gotowych, żeby wznowienie nie
    # przesuwało zadań między węzłami. ---
    lokalizacje_posortowane = sorted(pliki_pogodowe)
    algorytmy_zwykle = [a for a in nazwy_algorytmow if a != NAZWA_ALGORYTMU_NORMY]
    # Norma: właścicielem lokalizacji jest węzeł (indeks lokalizacji % liczba węzłów).
    zadania_normy = [(lok, pliki_pogodowe[lok], NAZWA_ALGORYTMU_NORMY)
                     for i, lok in enumerate(lokalizacje_posortowane) if i % SHARD_LICZBA == SHARD_INDEKS]
    # Reszta: najdłuższe najpierw (LPT), potem round-robin po węzłach - każdy węzeł dostaje
    # podobną mieszankę ciężkich i lekkich zadań.
    wszystkie_zwykle = sorted(
        ((lok, pliki_pogodowe[lok], alg) for lok in lokalizacje_posortowane for alg in algorytmy_zwykle),
        key=lambda z: (-koszt_zadania(z[2]), z[2], z[0]))
    zadania_zwykle = [z for i, z in enumerate(wszystkie_zwykle) if i % SHARD_LICZBA == SHARD_INDEKS]
    liczba_zadan_globalnie = len(lokalizacje_posortowane) * len(nazwy_algorytmow)

    if SHARD_LICZBA > 1:
        print(f"\nWĘZEŁ {SHARD_INDEKS + 1}/{SHARD_LICZBA}: {len(zadania_normy) + len(zadania_zwykle)} z "
              f"{liczba_zadan_globalnie} zadań przypada na ten węzeł.")
    sciezka_zbiorczy = os.path.join(
        FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.csv" if SHARD_LICZBA == 1
        else f"PRZEGLAD_ZBIORCZY_czesc_{SHARD_INDEKS:03d}.csv")

    wyniki = []
    gotowe_pary = set()
    if WZNAWIAJ_PRZERWANE:
        # Gotowe pary z WSZYSTKICH plików zbiorczych (także od innych węzłów / poprzedniego
        # podziału), a do wyników bierzemy: przy jednym węźle wszystko, przy shardach - tylko
        # własny plik (resztę scali tryb SZYNA_TYLKO_SCAL).
        wszystkie_dotychczasowe = _wczytaj_wyniki_z_plikow(_pliki_zbiorcze())
        gotowe_pary = {(w['lokalizacja'], w['name']) for w in wszystkie_dotychczasowe
                       if 'lokalizacja' in w and 'name' in w}
        if SHARD_LICZBA == 1:
            wyniki = wszystkie_dotychczasowe
        elif os.path.exists(sciezka_zbiorczy):
            wyniki = _wczytaj_wyniki_z_plikow([sciezka_zbiorczy])
        if gotowe_pary:
            print(f"WZNOWIENIE: znaleziono {len(gotowe_pary)} gotowych zadań z poprzedniego przebiegu.")

    # Faza 1: norma - liczona raz na lokalizację, zapisuje referencję dla reszty. Zadanie
    # wchodzi, gdy brakuje wyniku normy ALBO pliku referencji (wtedy wynik nie jest dopisywany
    # drugi raz, tylko odtwarzana referencja).
    faza1 = [z for z in zadania_normy
             if (z[0], z[2]) not in gotowe_pary or not os.path.exists(_sciezka_referencji(z[0]))]
    faza2 = [z for z in zadania_zwykle if (z[0], z[2]) not in gotowe_pary]
    print(f"\nDo policzenia: {len(faza1)} zadań normy (faza 1) + {len(faza2)} zadań pozostałych algorytmów "
          f"(faza 2) na {liczba_watkow} procesach.\n")

    bledy = []
    if faza1 or faza2:
        t0 = time.time()
        zakonczone = 0
        liczba_do_zrobienia = len(faza1) + len(faza2)

        def wykonaj_faze(executor, zadania_fazy):
            nonlocal zakonczone
            futures = {executor.submit(przetworz_kombinacje, lok, sciezka, alg): (lok, alg)
                       for lok, sciezka, alg in zadania_fazy}
            for future in as_completed(futures):
                nazwa_lokalizacji, nazwa_algorytmu, stats, blad = future.result()
                zakonczone += 1
                elapsed_min = (time.time() - t0) / 60.0
                if blad is not None:
                    bledy.append((nazwa_lokalizacji, nazwa_algorytmu, blad))
                    print(f"[{zakonczone}/{liczba_do_zrobienia}] BŁĄD {nazwa_lokalizacji}/{nazwa_algorytmu} "
                          f"(upłynęło {elapsed_min:.1f} min):\n{blad}", flush=True)
                else:
                    if (nazwa_lokalizacji, nazwa_algorytmu) not in gotowe_pary:
                        wyniki.append(stats)
                        gotowe_pary.add((nazwa_lokalizacji, nazwa_algorytmu))
                    print(f"[{zakonczone}/{liczba_do_zrobienia}] OK {nazwa_lokalizacji}/{nazwa_algorytmu} "
                          f"energia={stats['energia_kwh']:.1f} kWh (upłynęło {elapsed_min:.1f} min)", flush=True)
                pd.DataFrame(wyniki).to_csv(sciezka_zbiorczy, index=False)

        with ProcessPoolExecutor(max_workers=liczba_watkow) as executor:
            if faza1:
                wykonaj_faze(executor, faza1)
            if faza2:
                wykonaj_faze(executor, faza2)

        calkowity_czas_min = (time.time() - t0) / 60.0
        print(f"\nZakończono w {calkowity_czas_min:.1f} min. Wyniki w pliku: {len(wyniki)} "
              f"(zadań globalnie: {liczba_zadan_globalnie}). Błędy w TYM przebiegu: {len(bledy)}.")
        if bledy:
            print("Lokalizacje/algorytmy zakończone błędem:")
            for lok, alg, _ in bledy:
                print(f"  - {lok} / {alg}")
    else:
        print("Wszystkie zadania już wykonane w poprzednim przebiegu - nic do policzenia.")

    if not wyniki:
        print("Brak wyników - wszystkie zadania zakończyły się błędem.")
        return

    df_wszystkie = _posortuj_kolumny(pd.DataFrame(wyniki))
    df_wszystkie.to_csv(sciezka_zbiorczy, index=False)

    if SHARD_LICZBA > 1:
        print(f"\nCzęść {SHARD_INDEKS + 1}/{SHARD_LICZBA} gotowa: {sciezka_zbiorczy}\n"
              "Excel powstanie po scaleniu części (zadanie z SZYNA_TYLKO_SCAL=1).")
        return

    _generuj_excel()
    print(f"\nGotowe. Wszystkie pliki w folderze: {FOLDER_WYNIKOW}")


if __name__ == '__main__':
    main()
