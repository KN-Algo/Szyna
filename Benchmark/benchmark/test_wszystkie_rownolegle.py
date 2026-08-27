# test_wszystkie_rownolegle.py
#
# To samo co test_wszystkie_algorytmy_wszystkie_lokalizacje.py (WSZYSTKIE
# algorytmy x WSZYSTKIE lokalizacje), ale rozbite na niezależne zadania
# (lokalizacja, algorytm) uruchamiane RÓWNOLEGLE na wielu procesach naraz.
#
# Każde zadanie jest w PEŁNI samowystarczalne: samo wczytuje pogodę i samo
# liczy szybki przebieg normy jako referencję bezpiecznika - to drobny narzut
# (norma liczy się do 17x zamiast raz na lokalizację), za to ZERO zależności
# między zadaniami, więc skaluje się bezpiecznie do dowolnej liczby procesów
# bez żadnej współdzielonej pamięci/synchronizacji.
#
# LICZBA PROCESÓW: wykrywana automatycznie ze zmiennych środowiskowych typowych
# dla harmonogramów HPC (SLURM/PBS/LSF) - na superkomputerze os.cpu_count()
# zwraca liczbę rdzeni CAŁEGO WĘZŁA, nie liczbę faktycznie przydzieloną temu
# zadaniu, więc samo os.cpu_count() by tu nie wystarczyło. Można też nadpisać
# ręcznie przez LICZBA_WATKOW_NADPISANIE poniżej.
#
# UWAGA: w odróżnieniu od wersji sekwencyjnej ten skrypt NIE generuje wykresów
# PNG per lokalizacja (tylko CSV per (lokalizacja, algorytm) + PRZEGLAD_ZBIORCZY.csv
# + Excel) - to świadome uproszczenie, żeby skupić się na maksymalnej
# przepustowości obliczeniowej. Dane do wykresów są w zapisanych CSV, gdyby
# ktoś chciał je później dorysować.

import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER_POGODA = os.path.join(BASE_DIR, "Pogoda_pomiary_15_minut")

# Wszystkie poniższe stałe można nadpisać zmiennymi środowiskowymi - m.in. dlatego,
# że przy ProcessPoolExecutor w trybie 'spawn' (domyślny na Windows) każdy proces
# potomny NA NOWO importuje ten moduł ze źródła na dysku, więc zwykłe nadpisanie
# atrybutu modułu w procesie głównym (np. do celów testowych) NIE dotrze do
# procesów roboczych - zmienne środowiskowe są jedynym sposobem, który faktycznie
# działa przez tę granicę. Przydaje się to też na superkomputerze: harmonogram
# (np. skrypt SLURM) może dostroić parametry bez ruszania kodu.
FOLDER_WYNIKOW = os.environ.get(
    'SZYNA_FOLDER_WYNIKOW', os.path.join(BASE_DIR, "wyniki", "przeglad_wielu_lokalizacji"))
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)

# Budżet przełączeń DZIENNY, egzekwowany NA ŻYWO w trakcie symulacji przez
# każdy algorytm o wyjściu binarnym/dyskretnym (histereza, FL2/FL2v2/FL3) -
# wywodzi się z założonego budżetu ŻYCIOWEGO przekaźnika/styku (patrz
# BUDZET_PRZELACZEN_CALKOWITY niżej, używany tylko do raportowania w Excelu,
# nie do egzekwowania limitu na bieżąco). Dawniej 12/dzień - podniesione na
# wyraźne życzenie użytkownika.
MAX_SWITCHES_PER_DAY = int(os.environ.get('SZYNA_MAX_PRZELACZEN_DZIEN', '100'))

# Całkowity, ŻYCIOWY budżet przełączeń przekaźnika/styku (np. wg specyfikacji
# producenta) - używany WYŁĄCZNIE do raportowania w Excelu (zakładka
# "Zlozonosc_obliczeniowa"/kolumna budżetu) - pokazuje, jaki % tego budżetu
# zużywałby dany algorytm rocznie przy tempie przełączeń zaobserwowanym w tym
# przebiegu. NIE wpływa na symulację (to tylko analiza/interpretacja wyniku
# 'przelaczenia' już policzonego). Dotyczy WYŁĄCZNIE algorytmów o wyjściu
# binarnym/dyskretnym (typ w rejestrze inny niż PID/FL1) - dla algorytmów
# ciągłych liczba przełączeń nic nie mówi o zużyciu mechanicznym styku, więc
# ta metryka jest dla nich pomijana (patrz generuj_excel_podsumowanie.py).
BUDZET_PRZELACZEN_CALKOWITY = int(os.environ.get('SZYNA_BUDZET_PRZELACZEN', '500000'))

NAZWA_ALGORYTMU_NORMY = 'algorytm_z_normy'

# None = cały zakres każdego pliku (patrz uzasadnienie w wersji sekwencyjnej -
# test_wszystkie_algorytmy_wszystkie_lokalizacje.py). Ustaw zmienną środowiskową
# SZYNA_MAX_DNI (np. 7), żeby ograniczyć się do najzimniejszego wycinka i skrócić
# czas/dysk - przydatne zwłaszcza do szybkich testów całego potoku.
_max_dni_env = os.environ.get('SZYNA_MAX_DNI')
MAX_DNI_NA_LOKALIZACJE = int(_max_dni_env) if _max_dni_env else None

# Co ile sekund zapisujemy przebieg do CSV (patrz symulacja_fizyczna.przygotuj_do_zapisu) -
# statystyki i tak liczone są z pełnej rozdzielczości 1s przed tym zmniejszeniem.
ZAPISZ_CO_N_SEKUND = int(os.environ.get('SZYNA_ZAPISZ_CO_N_SEKUND', '60'))

# Ustaw zmienną środowiskową SZYNA_LICZBA_WATKOW, żeby wymusić konkretną liczbę
# procesów zamiast autodetekcji (przydatne, gdy z jakiegoś powodu nie chcesz
# używać wszystkich wykrytych rdzeni).
_watkow_env = os.environ.get('SZYNA_LICZBA_WATKOW')
LICZBA_WATKOW_NADPISANIE = int(_watkow_env) if _watkow_env else None

# Opcjonalny filtr do szybkich testów: lista nazw algorytmów oddzielona przecinkami
# w SZYNA_ALGORYTMY (np. "algorytm_z_normy,risk_function_pid"). Puste/nieustawione
# = wszystkie algorytmy z rejestru (normalne, pełne uruchomienie).
_algorytmy_env = os.environ.get('SZYNA_ALGORYTMY')
ALGORYTMY_FILTR = (
    {a.strip() for a in _algorytmy_env.split(',') if a.strip()} if _algorytmy_env else None
)

# Opcjonalny filtr do szybkich testów: lista nazw lokalizacji (bez .csv) oddzielona
# przecinkami w SZYNA_LOKALIZACJE. Puste/nieustawione = wszystkie znalezione pliki.
_lokalizacje_env = os.environ.get('SZYNA_LOKALIZACJE')
LOKALIZACJE_FILTR = (
    {l.strip() for l in _lokalizacje_env.split(',') if l.strip()} if _lokalizacje_env else None
)

# Analiza wrażliwości na niepewność modelu obiektu (transmitancja GRZANIA,
# SOPDT K/T1/T2/L - patrz symulacja_fizyczna.przygotuj_modele_stanowe) - procentowe
# zaburzenie PRAWDZIWEGO obiektu symulowanego (nie założeń żadnego algorytmu).
# Domyślnie 0.0 (brak zaburzenia = zachowanie identyczne jak przed dodaniem tej
# funkcji). SZYNA_SCENARIUSZ to czysto opisowa etykieta (do kolumny 'scenariusz'
# w wynikach) - nie wpływa na obliczenia, ułatwia tylko późniejsze filtrowanie/
# porównanie wielu przebiegów w jednym pliku, gdyby ktoś je scalił.
PERTURBACJA_K_PCT = float(os.environ.get('SZYNA_PERTURB_K', '0.0'))
PERTURBACJA_T1_PCT = float(os.environ.get('SZYNA_PERTURB_T1', '0.0'))
PERTURBACJA_T2_PCT = float(os.environ.get('SZYNA_PERTURB_T2', '0.0'))
PERTURBACJA_L_PCT = float(os.environ.get('SZYNA_PERTURB_L', '0.0'))
SCENARIUSZ_ETYKIETA = os.environ.get('SZYNA_SCENARIUSZ', 'nominal')

# Krok symulacji/sterowania [s] - domyślnie 10s (NIE 1s): decyzja sterowania i
# fizyka liczone są co tyle sekund zamiast co sekundę. Zweryfikowane, że przy
# tej samej fizyce (K_H/T1_H/T2_H/L_H) i tym samym autoteście wynik energetyczny
# zmienia się o ułamek procenta (~0.02% w testach), za to symulacja jest ~13x
# szybsza - bezpośrednio adresuje ciasny budżet CPU-godzin na klastrze. Ustaw
# SZYNA_KROK_S=1, żeby wrócić do dawnej rozdzielczości 1-sekundowej (np. do
# odtworzenia/porównania z wynikami sprzed tej zmiany).
KROK_SYMULACJI_S = float(os.environ.get('SZYNA_KROK_S', '10.0'))

# Wznawianie przerwanego przebiegu (np. po wyczerpaniu limitu czasu/pamięci na
# klastrze albo awarii węzła) - domyślnie WŁĄCZONE: jeśli w FOLDER_WYNIKOW
# istnieje już PRZEGLAD_ZBIORCZY.csv z POPRZEDNIEGO (niedokończonego) przebiegu
# w TYM SAMYM folderze/scenariuszu, wczytujemy go i pomijamy zadania
# (lokalizacja, algorytm), które już w nim są - liczą się TYLKO brakujące.
# Nic z poprzedniego przebiegu nie ginie (stare wyniki trafiają do finalnego
# CSV razem z nowymi). Ustaw SZYNA_WZNOW=0, żeby wymusić przeliczenie WSZYSTKIEGO
# od zera nawet jeśli częściowe wyniki już istnieją (np. po zmianie kodu
# algorytmów, gdy stare wyniki są już nieaktualne).
WZNAWIAJ_PRZERWANE = os.environ.get('SZYNA_WZNOW', '1') != '0'


def wykryj_liczbe_watkow():
    """
    Ile procesów roboczych możemy realnie odpalić. Sprawdza NAJPIERW zmienne
    środowiskowe typowe dla harmonogramów zadań HPC, bo na superkomputerze
    zadanie zwykle dostaje tylko WYCINEK rdzeni węzła, a os.cpu_count() (albo
    nawet os.sched_getaffinity) może tego nie odzwierciedlać w zależności od
    tego, jak dokładnie skonfigurowany jest dany klaster. Dopiero gdy żadna
    z tych zmiennych nie jest ustawiona, wraca do lokalnego wykrywania rdzeni.
    """
    if LICZBA_WATKOW_NADPISANIE:
        print(f"Liczba wątków nadpisana ręcznie: {LICZBA_WATKOW_NADPISANIE}")
        return LICZBA_WATKOW_NADPISANIE

    for zmienna in ('SLURM_CPUS_PER_TASK', 'SLURM_JOB_CPUS_PER_NODE', 'PBS_NP',
                     'NSLOTS', 'LSB_DJOB_NUMPROC'):
        wartosc = os.environ.get(zmienna)
        if wartosc:
            # SLURM_JOB_CPUS_PER_NODE bywa w formie "32(x2)" przy wielu węzłach
            # albo "16,16" - bierzemy pierwszą liczbę jako bezpieczny dolny wariant.
            try:
                liczba = int(str(wartosc).split('(')[0].split(',')[0])
                if liczba > 0:
                    print(f"Wykryto limit rdzeni ze zmiennej {zmienna}={wartosc} -> {liczba} procesów")
                    return liczba
            except ValueError:
                continue

    try:
        liczba = len(os.sched_getaffinity(0))  # dokładniej odzwierciedla limity cgroup/kontenera (tylko Linux)
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
    """
    Kompiluje WSZYSTKIE funkcje @njit RAZ w procesie głównym, PRZED odpaleniem
    puli procesów. Bez tego kilkadziesiąt/kilkaset procesów mogłoby próbować
    skompilować (i zapisać na dysk) te same funkcje JEDNOCZEŚNIE przy
    pierwszym starcie - numba jest na to generalnie odporna, ale przy dużej
    równoległości (zwłaszcza na sieciowym systemie plików $HOME na klastrze)
    to tania, bezpieczna przezorność: worker-procesy znajdą już gotowy cache
    na dysku zamiast rywalizować o jego zapis.
    """
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
    kontroler, metoda = stworz_kontroler('risk_function_pid', max_switches_per_day=12)
    fiz.uruchom_kontroler('rozgrzewka', kontroler, metoda, df_1s, hrt_weather_all,
                           A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt, print_progress=False)
    print("Gotowe.\n")


def przetworz_kombinacje(nazwa_lokalizacji, sciezka_csv, nazwa_algorytmu):
    """
    Uruchamiana w OSOBNYM PROCESIE - w pełni samowystarczalna (własne importy,
    własne wczytanie pogody, własne przeliczenie normy jako referencji
    bezpiecznika). Zwraca (nazwa_lokalizacji, nazwa_algorytmu, stats albo None,
    treść_błędu albo None) - nigdy nie rzuca wyjątku na zewnątrz, żeby jedno
    wadliwe zadanie nie ubiło całej puli procesów.
    """
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
        import symulacja_fizyczna as fiz
        from rejestr_algorytmow import stworz_kontroler, podlega_bezpiecznikowi

        zakres_dat = None
        if MAX_DNI_NA_LOKALIZACJE is not None:
            zakres_dat = fiz.wybierz_najzimniejsze_okno(sciezka_csv, MAX_DNI_NA_LOKALIZACJE)

        dt = KROK_SYMULACJI_S
        df_1s = fiz.wczytaj_pogode_1s(sciezka_csv, zakres_dat=zakres_dat, dt=dt)
        A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(
            dt, k_h_pct=PERTURBACJA_K_PCT, t1_h_pct=PERTURBACJA_T1_PCT,
            t2_h_pct=PERTURBACJA_T2_PCT, l_h_pct=PERTURBACJA_L_PCT,
        )
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

            # Rodzina "uczenia z kar" (funkcja_nauka_kary_wspolna.py) loguje
            # KAŻDĄ aktualizację _czynnik_nauczony (raz/dobę) do
            # kontroler.historia_uczenia - zapisujemy to OSOBNO (nie do
            # głównego CSV, bo ma inną granulację czasową - raz/dobę, nie
            # raz/krok) do zakładki "Uczenie_adaptacyjne" w Excelu.
            historia_uczenia = getattr(kontroler, 'historia_uczenia', None)
            if historia_uczenia:
                df_uczenie = pd.DataFrame(historia_uczenia)
                df_uczenie.insert(0, 'algorytm', nazwa_algorytmu)
                df_uczenie.insert(0, 'lokalizacja', nazwa_lokalizacji)
                df_uczenie.to_csv(
                    os.path.join(FOLDER_WYNIKOW, f"{nazwa_lokalizacji}_{nazwa_algorytmu}_uczenie.csv"),
                    index=False,
                )

        stats = dict(stats)
        stats['lokalizacja'] = nazwa_lokalizacji
        stats['scenariusz'] = SCENARIUSZ_ETYKIETA
        stats['perturb_k_pct'] = PERTURBACJA_K_PCT
        stats['perturb_t1_pct'] = PERTURBACJA_T1_PCT
        stats['perturb_t2_pct'] = PERTURBACJA_T2_PCT
        stats['perturb_l_pct'] = PERTURBACJA_L_PCT
        df_zapis = fiz.przygotuj_do_zapisu(df_wynik, ZAPISZ_CO_N_SEKUND)
        # Etykieta scenariusza w nazwie pliku - żeby różne scenariusze (analiza
        # wrażliwości) mogły bezpiecznie współdzielić ten sam FOLDER_WYNIKOW bez
        # nadpisywania się nawzajem (domyślnie 'nominal', czyli identyczna nazwa
        # jak przed dodaniem analizy wrażliwości - zero zmian w zwykłym użyciu).
        przedrostek = f"{nazwa_lokalizacji}_{nazwa_algorytmu}" if SCENARIUSZ_ETYKIETA == 'nominal' \
            else f"{nazwa_lokalizacji}_{nazwa_algorytmu}_{SCENARIUSZ_ETYKIETA}"
        df_zapis.to_csv(os.path.join(FOLDER_WYNIKOW, f"{przedrostek}.csv"), index=False)

        return nazwa_lokalizacji, nazwa_algorytmu, stats, None
    except Exception:
        return nazwa_lokalizacji, nazwa_algorytmu, None, traceback.format_exc()


def main():
    liczba_watkow = wykryj_liczbe_watkow()
    _rozgrzej_numba()

    pliki_pogodowe = znajdz_pliki_pogodowe()
    if LOKALIZACJE_FILTR is not None:
        pliki_pogodowe = {k: v for k, v in pliki_pogodowe.items() if k in LOKALIZACJE_FILTR}
    sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
    from rejestr_algorytmow import ALGORYTMY

    nazwy_algorytmow = list(ALGORYTMY)
    if ALGORYTMY_FILTR is not None:
        nazwy_algorytmow = [a for a in nazwy_algorytmow if a in ALGORYTMY_FILTR]

    if (PERTURBACJA_K_PCT, PERTURBACJA_T1_PCT, PERTURBACJA_T2_PCT, PERTURBACJA_L_PCT) != (0.0, 0.0, 0.0, 0.0):
        print(f"UWAGA: aktywna PERTURBACJA transmitancji grzania (scenariusz '{SCENARIUSZ_ETYKIETA}') - "
              f"K{PERTURBACJA_K_PCT:+.1f}% T1{PERTURBACJA_T1_PCT:+.1f}% T2{PERTURBACJA_T2_PCT:+.1f}% "
              f"L{PERTURBACJA_L_PCT:+.1f}% - analiza wrażliwości, NIE nominalny przebieg.")
    if MAX_DNI_NA_LOKALIZACJE is not None:
        print(f"UWAGA: SZYNA_MAX_DNI={MAX_DNI_NA_LOKALIZACJE} - ograniczony zakres dat (tryb testowy).")
    if LOKALIZACJE_FILTR is not None or ALGORYTMY_FILTR is not None:
        print(f"UWAGA: filtr lokalizacji/algorytmów aktywny (tryb testowy) - "
              f"{len(pliki_pogodowe)} lokalizacji, {len(nazwy_algorytmow)} algorytmów.")

    zadania = [
        (lokalizacja, sciezka, algorytm)
        for lokalizacja, sciezka in pliki_pogodowe.items()
        for algorytm in nazwy_algorytmow
    ]
    print(f"Łącznie {len(zadania)} zadań ({len(pliki_pogodowe)} lokalizacji x {len(ALGORYTMY)} algorytmów) "
          f"na {liczba_watkow} procesach.\n")

    # --- WZNOWIENIE: jeśli PRZEGLAD_ZBIORCZY.csv z poprzedniego (niedokończonego)
    # przebiegu już istnieje w tym folderze, wczytujemy jego wiersze jako już
    # gotowe i pomijamy odpowiadające im zadania - liczą się TYLKO braki. ---
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
            print(f"WZNOWIENIE: znaleziono {len(gotowe_pary)} gotowych zadań z poprzedniego przebiegu "
                  f"({sciezka_zbiorczy}) - liczą się tylko brakujące {len(zadania)}/{liczba_przed}.\n")
        except Exception:
            print(f"UWAGA: nie udało się wczytać {sciezka_zbiorczy} do wznowienia - liczę wszystko od zera.\n")
            wyniki = []

    if not zadania:
        print("Wszystkie zadania już wykonane w poprzednim przebiegu (SZYNA_WZNOW=1) - nic do policzenia, "
              "tylko odświeżam Excel z istniejącego PRZEGLAD_ZBIORCZY.csv.")
        try:
            import generuj_excel_podsumowanie
            generuj_excel_podsumowanie.main()
        except Exception:
            traceback.print_exc()
        return

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

            # Zapisujemy zbiorczą tabelę co jakiś czas - postęp widoczny na bieżąco,
            # nawet jeśli przebieg zostanie przerwany w połowie.
            if zakonczone % 10 == 0 or zakonczone == len(zadania):
                pd.DataFrame(wyniki).to_csv(os.path.join(FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.csv"), index=False)

    calkowity_czas_min = (time.time() - t0) / 60.0
    print(f"\nZakończono w {calkowity_czas_min:.1f} min. Sukcesy: {len(wyniki)}/{liczba_zadan_ogolem} "
          f"(w tym {len(wyniki) - (zakonczone - len(bledy))} wznowionych z poprzedniego przebiegu). "
          f"Błędy w TYM przebiegu: {len(bledy)}.")
    if bledy:
        print("Lokalizacje/algorytmy zakończone błędem:")
        for lok, alg, _ in bledy:
            print(f"  - {lok} / {alg}")

    if not wyniki:
        print("Brak wyników - wszystkie zadania zakończyły się błędem.")
        return

    df_wszystkie = pd.DataFrame(wyniki)
    kolumny = ['lokalizacja', 'name', 'scenariusz', 'perturb_k_pct', 'perturb_t1_pct', 'perturb_t2_pct',
               'perturb_l_pct', 'energia_kwh', 'przelaczenia', 'max_snieg_mm', 'max_lod_mm', 'max_hrt', 'min_hrt',
               'srednia_moc_pct', 'godziny_ze_sniegiem', 'zabezpieczen_normy_uzytych', 'dni', 'flops_rzeczywiste']
    kolumny = [k for k in kolumny if k in df_wszystkie.columns]
    df_wszystkie = df_wszystkie[kolumny]
    df_wszystkie.to_csv(os.path.join(FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.csv"), index=False)

    try:
        import generuj_excel_podsumowanie
        generuj_excel_podsumowanie.main()
    except Exception:
        print("\n!!! BŁĄD przy generowaniu Podsumowanie_wynikow.xlsx - CSV są bezpieczne, "
              "spróbuj uruchomić generuj_excel_podsumowanie.py osobno !!!")
        traceback.print_exc()

    print(f"\nGotowe. Wszystkie pliki CSV i Excel w folderze: {FOLDER_WYNIKOW}")


if __name__ == '__main__':
    main()
