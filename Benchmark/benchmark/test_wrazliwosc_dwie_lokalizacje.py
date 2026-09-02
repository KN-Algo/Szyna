# test_wrazliwosc_dwie_lokalizacje.py
#
# Pogłębiona analiza wrażliwości na niepewność modelu obiektu (transmitancja
# GRZANIA, SOPDT K/T1/T2/L) NA DWÓCH reprezentatywnych, skrajnych lokalizacjach:
#   - abisko_60min_2024   - najwięcej opadu/śniegu ze wszystkich 43 lokalizacji
#                             (patrz analiza w rozmowie: 1425 mm śniegu/5 lat,
#                             1.89 mm/dzień - zdecydowany lider)
#   - ojmiakon_60min_2024 - najzimniejsza lokalizacja (śr. -35.6°C, min -59.1°C)
#
# W ODRÓŻNIENIU od slurm_wrazliwosc_transmitancji.sh (8 scenariuszy, PEŁNY
# przegląd 43 lokalizacje x wszystkie algorytmy, jeden scenariusz na
# uruchomienie skryptu przez SZYNA_PERTURB_*) - ten skrypt liczy CAŁĄ MACIERZ
# scenariuszy w JEDNYM uruchomieniu, na tylko 2 lokalizacjach, i DODATKOWO:
#
#   1) Szerszy zestaw zaburzeń: K i OPÓŹNIENIE (L) osobno i w kombinacji, plus
#      T1, na dwóch poziomach (+10%/+20%) - 14 scenariuszy transmitancji
#      (nominal + 6 pojedynczych + 6 par + 1 potrójny K+L+T1 @ +20%).
#   2) KAŻDY z nich powtórzony też z BIAŁYM SZUMEM pomiarowym na HRT i CRT
#      (te same czujniki, z których autotest identyfikuje obiekt) - 28
#      scenariuszy-wariantów łącznie na lokalizację.
#   3) JAKOŚĆ AUTOTESTU: dla algorytmów adaptacyjnych (autotest startowy)
#      porównuje ZIDENTYFIKOWANE K/T1/L z PRAWDZIWYMI (zaburzonymi) wartościami
#      obiektu - pokazuje czy/jak bardzo szum psuje identyfikację.
#
# Sens: algorytmy ADAPTACYJNE (autotest + cyfrowy bliźniak) same identyfikują
# PRAWDZIWY (zaburzony, ew. zaszumiony) obiekt z pomiarów, więc POWINNY się do
# niego dostroić - algorytmy NIEADAPTACYJNE (stałe nastawy) nie wiedzą o
# zaburzeniu. To pokazuje: (a) która strategia jest odporniejsza na
# niepewność/dryf parametrów obiektu, (b) jak degraduje się JAKOŚĆ SAMEJ
# IDENTYFIKACJI pod wpływem szumu czujników.
#
# KOSZT: 2 lokalizacje x 28 scenariuszy-wariantów x N algorytmów - domyślnie
# okno 45 dni (SZYNA_MAX_DNI_WRAZ, najzimniejszy wycinek każdej lokalizacji -
# patrz symulacja_fizyczna.wybierz_najzimniejsze_okno) zamiast pełnego zakresu,
# żeby dać się policzyć LOKALNIE w rozsądnym czasie. Pełny zakres dat (151 dni)
# jest ~3.3x droższy - do tego polecany SLURM (patrz slurm_wrazliwosc_2lok.sh).
# Checkpoint/resume jak w test_wszystkie_rownolegle.py (SZYNA_WZNOW=1 domyślnie).
#
# Sterowanie (zmienne środowiskowe):
#   SZYNA_LOKALIZACJE_WRAZ      - lista lokalizacji, domyślnie "abisko_60min_2024,ojmiakon_60min_2024"
#   SZYNA_MAX_DNI_WRAZ          - okno dni na lokalizację (domyślnie 45, najzimniejszy wycinek)
#   SZYNA_KROK_S                - krok symulacji/sterowania [s] (domyślnie 10.0, jak reszta projektu)
#   SZYNA_LICZBA_WATKOW         - liczba procesów (jak reszta projektu)
#   SZYNA_FOLDER_WYNIKOW_WRAZ   - folder wyników (domyślnie wyniki/wrazliwosc_2lokalizacje)
#   SZYNA_WZNOW                 - wznawianie przerwanego przebiegu (domyślnie 1)
#   SZYNA_SCENARIUSZE_WRAZ      - filtr nazw scenariuszy (przecinki), domyślnie wszystkie 14
#
# Uruchomienie: python test_wrazliwosc_dwie_lokalizacje.py

import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER_POGODA = os.path.join(BASE_DIR, "Pogoda_pomiary_15_minut")
FOLDER_WYNIKOW = os.environ.get(
    'SZYNA_FOLDER_WYNIKOW_WRAZ', os.path.join(BASE_DIR, "wyniki", "wrazliwosc_2lokalizacje"))
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)

_lok_env = os.environ.get('SZYNA_LOKALIZACJE_WRAZ')
LOKALIZACJE = [l.strip() for l in _lok_env.split(',')] if _lok_env else \
    ['abisko_60min_2024', 'ojmiakon_60min_2024']

MAX_DNI = int(os.environ.get('SZYNA_MAX_DNI_WRAZ', '45'))
KROK_SYMULACJI_S = float(os.environ.get('SZYNA_KROK_S', '10.0'))
MAX_SWITCHES_PER_DAY = 100

_watkow_env = os.environ.get('SZYNA_LICZBA_WATKOW')
LICZBA_WATKOW_NADPISANIE = int(_watkow_env) if _watkow_env else None

WZNAWIAJ_PRZERWANE = os.environ.get('SZYNA_WZNOW', '1') != '0'

_scen_env = os.environ.get('SZYNA_SCENARIUSZE_WRAZ')
SCENARIUSZE_FILTR = {s.strip() for s in _scen_env.split(',') if s.strip()} if _scen_env else None

_algorytmy_env = os.environ.get('SZYNA_ALGORYTMY')
ALGORYTMY_FILTR = {a.strip() for a in _algorytmy_env.split(',') if a.strip()} if _algorytmy_env else None

# --- SZUM POMIAROWY (biały, na HRT i CRT - te same czujniki z których autotest
# identyfikuje SOPDT: y = HRT - CRT) - patrz test_awarie_czujnikow.py, ten sam
# mechanizm/rząd wielkości (SZUM_STD_C=2.0). Nakładany na KAŻDY scenariusz
# transmitancji (na życzenie użytkownika - pokazuje najgorszy realistyczny
# przypadek: zaburzony obiekt + zaszumione czujniki jednocześnie). ---
SZUM_STD_C = 2.0
SZUM_SEED = 42

# --- MACIERZ SCENARIUSZY TRANSMITANCJI (K, opóźnienie L, T1 - pojedynczo i w
# kombinacjach, do +20%) - (perturb_k_pct, perturb_t1_pct, perturb_l_pct). ---
SCENARIUSZE_TRANSMITANCJI = {
    'nominal':          (0.0, 0.0, 0.0),
    'K_plus10':         (10.0, 0.0, 0.0),
    'K_plus20':         (20.0, 0.0, 0.0),
    'L_plus10':         (0.0, 0.0, 10.0),
    'L_plus20':         (0.0, 0.0, 20.0),
    'T1_plus10':        (0.0, 10.0, 0.0),
    'T1_plus20':        (0.0, 20.0, 0.0),
    'K10_L10':          (10.0, 0.0, 10.0),
    'K20_L20':          (20.0, 0.0, 20.0),
    'K10_T1_10':        (10.0, 10.0, 0.0),
    'K20_T1_20':        (20.0, 20.0, 0.0),
    'L10_T1_10':        (0.0, 10.0, 10.0),
    'L20_T1_20':        (0.0, 20.0, 20.0),
    'K20_L20_T1_20':    (20.0, 20.0, 20.0),
}
if SCENARIUSZE_FILTR is not None:
    SCENARIUSZE_TRANSMITANCJI = {k: v for k, v in SCENARIUSZE_TRANSMITANCJI.items() if k in SCENARIUSZE_FILTR}


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


def _zrob_szum_dwoch_czujnikow(std, seed):
    """Biały szum NIEZALEŻNY na HRT i CRT (dwa osobne generatory z różnym seedem,
    żeby błędy obu czujników nie były sztucznie skorelowane)."""
    rng_hrt = np.random.default_rng(seed)
    rng_crt = np.random.default_rng(seed + 1)

    def _injector(row, index):
        r = dict(row)
        r['HRT_temp_grzana'] = r['HRT_temp_grzana'] + float(rng_hrt.normal(0.0, std))
        r['CRT_temp_niegrzana'] = r['CRT_temp_niegrzana'] + float(rng_crt.normal(0.0, std))
        return r
    return _injector


def przetworz_zadanie(nazwa_lokalizacji, sciezka_csv, nazwa_algorytmu, nazwa_scenariusza, szum):
    """W pełni samowystarczalne (jak test_wszystkie_rownolegle.przetworz_kombinacje) - własne
    wczytanie pogody/model/norma per zadanie, zero zależności między zadaniami."""
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
        import symulacja_fizyczna as fiz
        from rejestr_algorytmow import stworz_kontroler, podlega_bezpiecznikowi

        perturb_k, perturb_t1, perturb_l = SCENARIUSZE_TRANSMITANCJI[nazwa_scenariusza]
        dt = KROK_SYMULACJI_S

        zakres_dat = fiz.wybierz_najzimniejsze_okno(sciezka_csv, MAX_DNI)
        df_1s = fiz.wczytaj_pogode_1s(sciezka_csv, zakres_dat=zakres_dat, dt=dt)
        A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(
            dt, k_h_pct=perturb_k, t1_h_pct=perturb_t1, l_h_pct=perturb_l,
        )
        at_array = df_1s['temperatura_powietrza_C'].to_numpy()
        hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)

        fault_injector = _zrob_szum_dwoch_czujnikow(SZUM_STD_C, SZUM_SEED) if szum else None

        kontroler_normy, metoda_normy = stworz_kontroler('algorytm_z_normy', max_switches_per_day=MAX_SWITCHES_PER_DAY)
        df_normy, stats_normy, snow_ref, power_ref = fiz.uruchom_kontroler(
            'algorytm_z_normy', kontroler_normy, metoda_normy, df_1s, hrt_weather_all,
            A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt, print_progress=False,
            fault_injector=fault_injector,
        )

        if nazwa_algorytmu == 'algorytm_z_normy':
            stats, kontroler = stats_normy, kontroler_normy
        else:
            czy_bezpiecznik = podlega_bezpiecznikowi(nazwa_algorytmu)
            kontroler, metoda = stworz_kontroler(nazwa_algorytmu, max_switches_per_day=MAX_SWITCHES_PER_DAY)
            _, stats, _, _ = fiz.uruchom_kontroler(
                nazwa_algorytmu, kontroler, metoda, df_1s, hrt_weather_all,
                A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt,
                snow_reference_mm=snow_ref if czy_bezpiecznik else None,
                power_reference_pct=power_ref if czy_bezpiecznik else None,
                print_progress=False, fault_injector=fault_injector,
            )

        stats = dict(stats)
        stats['lokalizacja'] = nazwa_lokalizacji
        stats['scenariusz'] = nazwa_scenariusza
        stats['perturb_k_pct'] = perturb_k
        stats['perturb_t1_pct'] = perturb_t1
        stats['perturb_l_pct'] = perturb_l
        stats['szum'] = bool(szum)

        # --- JAKOŚĆ AUTOTESTU: porównanie zidentyfikowanych K/T1/L z PRAWDZIWYMI
        # (zaburzonymi) wartościami obiektu - tylko dla algorytmów adaptacyjnych,
        # które w ogóle wykonują autotest (autotest_result is not None). ---
        autotest_result = getattr(kontroler, 'autotest_result', None)
        prawdziwe_k = fiz.K_H * (1.0 + perturb_k / 100.0)
        prawdziwe_t1 = fiz.T1_H * (1.0 + perturb_t1 / 100.0)
        prawdziwe_l = fiz.L_H * (1.0 + perturb_l / 100.0)
        if autotest_result is not None and autotest_result.get('fit_ok'):
            stats['autotest_fit_ok'] = True
            stats['autotest_r_squared'] = autotest_result['r_squared']
            stats['autotest_K'] = autotest_result['K']
            stats['autotest_T1'] = autotest_result['T1']
            stats['autotest_T2'] = autotest_result['T2']
            stats['autotest_L'] = autotest_result['L']
            stats['blad_identyfikacji_K_pct'] = (autotest_result['K'] - prawdziwe_k) / prawdziwe_k * 100.0
            stats['blad_identyfikacji_T1_pct'] = (autotest_result['T1'] - prawdziwe_t1) / prawdziwe_t1 * 100.0
            stats['blad_identyfikacji_L_pct'] = (
                (autotest_result['L'] - prawdziwe_l) / prawdziwe_l * 100.0 if prawdziwe_l > 1e-6 else None
            )
        elif autotest_result is not None:
            stats['autotest_fit_ok'] = False
        else:
            stats['autotest_fit_ok'] = None  # algorytm nieadaptacyjny - brak autotestu w ogóle

        return nazwa_lokalizacji, nazwa_algorytmu, nazwa_scenariusza, szum, stats, None
    except Exception:
        return nazwa_lokalizacji, nazwa_algorytmu, nazwa_scenariusza, szum, None, traceback.format_exc()


def main():
    liczba_watkow = wykryj_liczbe_watkow()
    print(f"Analiza wrażliwości transmitancji + szumu: {len(LOKALIZACJE)} lokalizacji "
          f"({', '.join(LOKALIZACJE)}), {len(SCENARIUSZE_TRANSMITANCJI)} scenariuszy x 2 (szum tak/nie), "
          f"okno {MAX_DNI} dni, krok {KROK_SYMULACJI_S:g}s, {liczba_watkow} procesów.\n")

    sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
    from rejestr_algorytmow import ALGORYTMY
    nazwy_algorytmow = list(ALGORYTMY)
    if ALGORYTMY_FILTR is not None:
        nazwy_algorytmow = [a for a in nazwy_algorytmow if a in ALGORYTMY_FILTR]

    zadania = [
        (lok, os.path.join(FOLDER_POGODA, f"{lok}.csv"), alg, scen, szum)
        for lok in LOKALIZACJE
        for alg in nazwy_algorytmow
        for scen in SCENARIUSZE_TRANSMITANCJI
        for szum in (False, True)
    ]
    liczba_zadan_ogolem = len(zadania)
    print(f"Łącznie {liczba_zadan_ogolem} zadań ({len(LOKALIZACJE)} lokalizacji x {len(nazwy_algorytmow)} "
          f"algorytmów x {len(SCENARIUSZE_TRANSMITANCJI)} scenariuszy x 2 warianty szumu).\n")

    wyniki = []
    sciezka_zbiorczy = os.path.join(FOLDER_WYNIKOW, "WRAZLIWOSC_ZBIORCZY.csv")
    if WZNAWIAJ_PRZERWANE and os.path.exists(sciezka_zbiorczy):
        try:
            df_poprzedni = pd.read_csv(sciezka_zbiorczy)
            wyniki = df_poprzedni.to_dict('records')
            gotowe = {(w['lokalizacja'], w['name'], w['scenariusz'], bool(w['szum'])) for w in wyniki}
            zadania = [z for z in zadania if (z[0], z[2], z[3], z[4]) not in gotowe]
            print(f"WZNOWIENIE: znaleziono {len(gotowe)} gotowych zadań z poprzedniego przebiegu - "
                  f"liczą się tylko brakujące {len(zadania)}/{liczba_zadan_ogolem}.\n")
        except Exception:
            print(f"UWAGA: nie udało się wczytać {sciezka_zbiorczy} do wznowienia - liczę wszystko od zera.\n")
            wyniki = []

    if not zadania:
        print("Wszystkie zadania już wykonane w poprzednim przebiegu - nic do policzenia.")
        return

    bledy = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=liczba_watkow) as executor:
        futures = {executor.submit(przetworz_zadanie, lok, sciezka, alg, scen, szum): (lok, alg, scen, szum)
                   for lok, sciezka, alg, scen, szum in zadania}

        zakonczone = 0
        for future in as_completed(futures):
            nazwa_lokalizacji, nazwa_algorytmu, nazwa_scenariusza, szum, stats, blad = future.result()
            zakonczone += 1
            elapsed_min = (time.time() - t0) / 60.0
            etykieta = f"{nazwa_lokalizacji}/{nazwa_algorytmu}/{nazwa_scenariusza}{'+szum' if szum else ''}"

            if blad is not None:
                bledy.append((etykieta, blad))
                print(f"[{zakonczone}/{len(zadania)}] BŁĄD {etykieta} (upłynęło {elapsed_min:.1f} min):\n{blad}")
            else:
                wyniki.append(stats)
                print(f"[{zakonczone}/{len(zadania)}] OK {etykieta} energia={stats['energia_kwh']:.1f} kWh "
                      f"(upłynęło {elapsed_min:.1f} min)")

            pd.DataFrame(wyniki).to_csv(sciezka_zbiorczy, index=False)

    calkowity_czas_min = (time.time() - t0) / 60.0
    print(f"\nZakończono w {calkowity_czas_min:.1f} min. Sukcesy: {len(wyniki)}/{liczba_zadan_ogolem}. "
          f"Błędy w TYM przebiegu: {len(bledy)}.")
    if bledy:
        print("Zadania zakończone błędem:")
        for etykieta, _ in bledy:
            print(f"  - {etykieta}")

    print(f"\nGotowe. Wyniki w: {sciezka_zbiorczy}")
    print("Uruchom generuj_excel_wrazliwosc.py, żeby zbudować podsumowanie Excel.")


if __name__ == '__main__':
    main()
