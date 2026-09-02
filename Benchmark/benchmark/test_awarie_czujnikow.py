# test_awarie_czujnikow.py
#
# KRÓTKI test odporności wszystkich algorytmów na AWARIE CZUJNIKÓW - na JEDNEJ
# reprezentatywnej lokalizacji symuluje kilka rodzajów uszkodzenia odczytu
# (bias, szum biały, rozłączenie/zamrożenie ostatniej wartości) na dwóch
# czujnikach (HRT - szyna ogrzewana, bezpośrednio steruje większością
# algorytmów; AT - powietrze, zasila prognozy Kalmana) i sprawdza, jak każdy
# algorytm sobie z tym radzi.
#
# WAŻNE: awaria dotyczy WYŁĄCZNIE tego, co WIDZI kontroler (patrz
# symulacja_fizyczna.uruchom_kontroler, parametr fault_injector) - PRAWDZIWA
# fizyka (rzeczywista temperatura szyny, model śniegu/lodu) liczy się zawsze
# poprawnie z NIEZAFAŁSZOWANYCH wartości. To dokładnie odwzorowuje realną
# awarię czujnika: rzeczywistość dalej się dzieje normalnie, tylko sterownik
# o niej nie wie i podejmuje decyzje na złych danych.
#
# Uruchomienie: python test_awarie_czujnikow.py
# Sterowanie (te same konwencje co test_wszystkie_rownolegle.py):
#   SZYNA_LOKALIZACJA_AWARIE   - która lokalizacja (domyślnie abisko_60min_2021)
#   SZYNA_MAX_DNI_AWARIE       - ile dni okna (domyślnie 10 - wystarczy, żeby
#                                 awaria typu "rozłączenie" (w połowie okna)
#                                 miała czas się objawić, a test zostaje szybki)
#   SZYNA_LICZBA_WATKOW        - jak w test_wszystkie_rownolegle.py
#   SZYNA_FOLDER_WYNIKOW_AWARIE - folder wyników (domyślnie wyniki/awarie_czujnikow)

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
    'SZYNA_FOLDER_WYNIKOW_AWARIE', os.path.join(BASE_DIR, "wyniki", "awarie_czujnikow"))
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)

LOKALIZACJA = os.environ.get('SZYNA_LOKALIZACJA_AWARIE', 'abisko_60min_2021')
MAX_DNI = int(os.environ.get('SZYNA_MAX_DNI_AWARIE', '10'))
KROK_SYMULACJI_S = float(os.environ.get('SZYNA_KROK_S', '10.0'))
MAX_SWITCHES_PER_DAY = 100

_watkow_env = os.environ.get('SZYNA_LICZBA_WATKOW')
LICZBA_WATKOW_NADPISANIE = int(_watkow_env) if _watkow_env else None

# --- PARAMETRY AWARII (patrz nagłówek pliku - uzgodnione z użytkownikiem jako
# wystarczające na start; łatwo dołożyć kolejne czujniki/typy poniżej). ---
BIAS_C = 5.0
SZUM_STD_C = 2.0
SZUM_SEED = 42


def wykryj_liczbe_watkow():
    if LICZBA_WATKOW_NADPISANIE:
        return LICZBA_WATKOW_NADPISANIE
    for zmienna in ('SLURM_CPUS_PER_TASK', 'SLURM_JOB_CPUS_PER_NODE', 'PBS_NP', 'NSLOTS', 'LSB_DJOB_NUMPROC'):
        wartosc = os.environ.get(zmienna)
        if wartosc:
            try:
                liczba = int(str(wartosc).split('(')[0].split(',')[0])
                if liczba > 0:
                    return liczba
            except ValueError:
                continue
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def _zrob_bias(pole, offset):
    def _injector(row, index):
        r = dict(row)
        r[pole] = r[pole] + offset
        return r
    return _injector


def _zrob_szum(pole, std):
    rng = np.random.default_rng(SZUM_SEED)

    def _injector(row, index):
        r = dict(row)
        r[pole] = r[pole] + float(rng.normal(0.0, std))
        return r
    return _injector


def _zrob_rozlaczenie(pole, krok_awarii):
    """Od `krok_awarii` w przód kontroler widzi ZAMROŻONĄ wartość sprzed awarii (typowa awaria "martwego" czujnika)."""
    stan = {'wartosc': None}

    def _injector(row, index):
        r = dict(row)
        if index >= krok_awarii:
            if stan['wartosc'] is None:
                stan['wartosc'] = row[pole]
            r[pole] = stan['wartosc']
        return r
    return _injector


def zbuduj_scenariusze(total_steps):
    """Zwraca {nazwa_scenariusza: fault_injector_albo_None}. None = brak awarii (baseline/referencja)."""
    krok_polowa = total_steps // 2
    return {
        'brak_awarii': None,
        'HRT_bias': _zrob_bias('HRT_temp_grzana', BIAS_C),
        'HRT_szum': _zrob_szum('HRT_temp_grzana', SZUM_STD_C),
        'HRT_rozlaczenie': _zrob_rozlaczenie('HRT_temp_grzana', krok_polowa),
        'AT_bias': _zrob_bias('AT_temp_powietrza', BIAS_C),
        'AT_szum': _zrob_szum('AT_temp_powietrza', SZUM_STD_C),
        'AT_rozlaczenie': _zrob_rozlaczenie('AT_temp_powietrza', krok_polowa),
    }


def przetworz_kombinacje(nazwa_algorytmu, nazwa_scenariusza):
    """W pełni samowystarczalna (jak test_wszystkie_rownolegle.przetworz_kombinacje) - własne wczytanie
    pogody/przeliczenie normy per zadanie, zero zależności między zadaniami."""
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
        import symulacja_fizyczna as fiz
        from rejestr_algorytmow import stworz_kontroler, podlega_bezpiecznikowi

        sciezka_csv = os.path.join(FOLDER_POGODA, f"{LOKALIZACJA}.csv")
        zakres_dat = fiz.wybierz_najzimniejsze_okno(sciezka_csv, MAX_DNI)
        dt = KROK_SYMULACJI_S
        df_1s = fiz.wczytaj_pogode_1s(sciezka_csv, zakres_dat=zakres_dat, dt=dt)
        A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(dt)
        at_array = df_1s['temperatura_powietrza_C'].to_numpy()
        hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)

        scenariusze = zbuduj_scenariusze(len(df_1s))
        fault_injector = scenariusze[nazwa_scenariusza]

        kontroler_normy, metoda_normy = stworz_kontroler('algorytm_z_normy', max_switches_per_day=MAX_SWITCHES_PER_DAY)
        df_normy, stats_normy, snow_ref, power_ref = fiz.uruchom_kontroler(
            'algorytm_z_normy', kontroler_normy, metoda_normy, df_1s, hrt_weather_all,
            A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt, print_progress=False,
        )

        if nazwa_algorytmu == 'algorytm_z_normy':
            stats = stats_normy
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
        stats['algorytm'] = nazwa_algorytmu
        stats['scenariusz_awarii'] = nazwa_scenariusza
        return nazwa_algorytmu, nazwa_scenariusza, stats, None
    except Exception:
        return nazwa_algorytmu, nazwa_scenariusza, None, traceback.format_exc()


def main():
    liczba_watkow = wykryj_liczbe_watkow()
    print(f"Test awaryjności czujników: lokalizacja={LOKALIZACJA}, {MAX_DNI} dni, krok={KROK_SYMULACJI_S:g}s, "
          f"{liczba_watkow} procesów.\n")

    sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
    from rejestr_algorytmow import ALGORYTMY

    nazwy_scenariuszy = list(zbuduj_scenariusze(1).keys())  # tylko nazwy - total_steps nieistotny na tym etapie
    zadania = [(alg, scen) for alg in ALGORYTMY for scen in nazwy_scenariuszy]
    print(f"Łącznie {len(zadania)} zadań ({len(ALGORYTMY)} algorytmów x {len(nazwy_scenariuszy)} scenariuszy awarii).\n")

    wyniki = []
    bledy = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=liczba_watkow) as executor:
        futures = {executor.submit(przetworz_kombinacje, alg, scen): (alg, scen) for alg, scen in zadania}
        zakonczone = 0
        for future in as_completed(futures):
            nazwa_algorytmu, nazwa_scenariusza, stats, blad = future.result()
            zakonczone += 1
            elapsed_min = (time.time() - t0) / 60.0
            if blad is not None:
                bledy.append((nazwa_algorytmu, nazwa_scenariusza, blad))
                print(f"[{zakonczone}/{len(zadania)}] BŁĄD {nazwa_algorytmu}/{nazwa_scenariusza} "
                      f"(upłynęło {elapsed_min:.1f} min):\n{blad}")
            else:
                wyniki.append(stats)
                print(f"[{zakonczone}/{len(zadania)}] OK {nazwa_algorytmu}/{nazwa_scenariusza} "
                      f"energia={stats['energia_kwh']:.1f} kWh max_hrt={stats['max_hrt']:.1f}°C "
                      f"(upłynęło {elapsed_min:.1f} min)")

    print(f"\nZakończono w {(time.time() - t0) / 60.0:.1f} min. Sukcesy: {len(wyniki)}/{len(zadania)}. Błędy: {len(bledy)}.")

    if wyniki:
        df = pd.DataFrame(wyniki)
        kolumny = ['algorytm', 'scenariusz_awarii', 'energia_kwh', 'przelaczenia', 'max_snieg_mm',
                   'max_lod_mm', 'max_hrt', 'min_hrt', 'srednia_moc_pct', 'flops_rzeczywiste',
                   'iae', 'ise', 'itae']
        kolumny = [k for k in kolumny if k in df.columns]
        df = df[kolumny]
        sciezka_csv = os.path.join(FOLDER_WYNIKOW, "AWARIE_ZBIORCZY.csv")
        df.to_csv(sciezka_csv, index=False)
        print(f"Zapisano: {sciezka_csv}")

        try:
            import generuj_excel_awarie
            generuj_excel_awarie.main(sciezka_csv, os.path.join(FOLDER_WYNIKOW, "Podsumowanie_awarii.xlsx"))
        except Exception:
            print("\n!!! BŁĄD przy generowaniu Podsumowanie_awarii.xlsx - CSV jest bezpieczny !!!")
            traceback.print_exc()

    print(f"\nGotowe. Wszystkie pliki w folderze: {FOLDER_WYNIKOW}")


if __name__ == '__main__':
    main()
