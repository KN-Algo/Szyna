# testy/strojenie_modele_adaptacyjne.py
#
# Przeszukanie hiperparametrów trzech "obiekt się adaptuje" algorytmów (model_obiektu_rls.py -
# WSPÓLNY żywy model RLS, 2026-10-02) - na życzenie użytkownika: "skrypt robiący dobór nastaw
# do PIDów, ADRC, MPC itd, żeby później je skalibrować i wystawić do testów". Do odpalenia
# LOKALNIE przez użytkownika (python testy/strojenie_modele_adaptacyjne.py) - NIE uruchamiany
# automatycznie z resztą przeglądu.
#
# METODOLOGIA (ta sama co testy/strojenie_fuzzy_2v2.py - koarse-to-fine):
#   Etap A (zgrubny, krótkie okno COARSE_DNI dni najzimniejszej pogody): pełna siatka
#     hiperparametrów KAŻDEGO z 3 algorytmów, osobno.
#   Etap B (WALIDACJA, dłuższe okno WALID_DNI dni, TA SAMA lokalizacja): baseline (wartości
#     DOMYŚLNE z samych plików algorytmów) + TOP_K_DO_WALIDACJI najlepszych z etapu A.
#   (Bez osobnego "etapu C dostrajania" jak w fuzzy - każdy algorytm tu ma TYLKO 3-5
#   hiperparametrów, jedna pełna siatka na raz wystarcza na pierwszy przebieg).
#
# OCENA: TA SAMA filozofia co wszędzie w projekcie - bezpieczeństwo NADRZĘDNE nad energią.
#   kandydat "bezpieczny" = kara_bezpieczenstwa <= KARA_TOLERANCJA; wśród bezpiecznych,
#   mniejsza energia_kwh wygrywa; jeśli ŻADEN bezpieczny - mniejsza kara wygrywa.
#   Symulacja z TYM SAMYM bezpiecznikiem normy (snow_reference_mm/power_reference_pct) co w
#   głównym przeglądzie (wszystkie 3 mają 'bezpiecznik': True w rejestrze).
#
# WSKAŹNIK POSTĘPU: każda policzona kombinacja wypisuje linię "[algorytm etap i/N] ...
# (upłynęło X.X min z Y.Y min całości)" - ten sam format co strojenie_fuzzy_2v2.py, plus
# całkowity szacowany czas na podstawie już policzonych kombinacji (aktualizowany na żywo).
#
# Lokalizacja: domyślnie ojmiakon (najzimniejsza w projekcie), nadpisywalna
# SZYNA_STROJENIE_LOKALIZACJA. Wynik: wyniki/strojenie_modele_adaptacyjne/
# {<algorytm>_etap_a.csv, <algorytm>_etap_b_walidacja.csv}, zwyciezcy.json.
#
# Uruchomienie (z katalogu Benchmark_crt/benchmark):
#   python testy/strojenie_modele_adaptacyjne.py

import io
import itertools
import json
import os
import sys
import time
from contextlib import redirect_stdout
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
FOLDER_POGODA = os.path.join(BASE_DIR, 'Pogoda_pomiary_15_minut')
FOLDER_WYNIKOW = os.path.join(BASE_DIR, 'wyniki', 'strojenie_modele_adaptacyjne')
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)

LOKALIZACJA = os.environ.get('SZYNA_STROJENIE_LOKALIZACJA', 'ojmiakon_60min_2025')
SCIEZKA_CSV = os.path.join(FOLDER_POGODA, f'{LOKALIZACJA}.csv')
COARSE_DNI = int(os.environ.get('SZYNA_STROJENIE_DNI_ZGRUBNE', '2'))
WALID_DNI = int(os.environ.get('SZYNA_STROJENIE_DNI_WALIDACJA', '15'))
KROK_S = float(os.environ.get('SZYNA_KROK_S', '10.0'))
TOP_K_DO_WALIDACJI = int(os.environ.get('SZYNA_STROJENIE_TOP_K', '3'))
KARA_TOLERANCJA = 1.0  # °C*s - poniżej tego kara_bezpieczenstwa traktowana jako "bezpieczna" (szum numeryczny)
LICZBA_WATKOW = int(os.environ.get('SZYNA_LICZBA_WATKOW', str(max(1, os.cpu_count() - 1))))

# --- Definicje 3 algorytmów: nazwa w rejestrze, wartości DOMYŚLNE (= zachowanie "bez
# strojenia", dokładnie jak w pliku źródłowym algorytmu) i siatka hiperparametrów do
# przeszukania. MPC ma dziś tylko 1 wystawiony hiperparametr (lam_zapominania) - reszta
# maszynerii MPC (wagi kosztu) jest WSPÓLNA dla całej rodziny MPC w mpc_wspolne.py, nie
# per-instancja, więc zostaje poza zakresem tego pierwszego przebiegu. ---
ALGORYTMY = {
    'risk_function_model_adaptacyjny': {
        'domyslne': dict(hrt_target_c=5.0, kp_tempo_podejscia=1.0 / 600.0,
                          pi_kc_korekta_percent=0.8, pi_ti_korekta_s=1800.0, lam_zapominania=0.999),
        'siatka': {
            'hrt_target_c': [3.0, 5.0, 7.0],
            'kp_tempo_podejscia': [1.0 / 300.0, 1.0 / 600.0, 1.0 / 1200.0],
            'lam_zapominania': [0.995, 0.999, 0.9999],
        },
    },
    'risk_function_adrc_model_adaptacyjny': {
        'domyslne': dict(hrt_target_c=5.0, omega_c=0.01, omega_o=0.05, lam_zapominania=0.999),
        'siatka': {
            'hrt_target_c': [3.0, 5.0, 7.0],
            'omega_c': [0.005, 0.01, 0.02],
            'omega_o': [0.02, 0.05, 0.1],
        },
    },
    'mpc_model_adaptacyjny': {
        'domyslne': dict(lam_zapominania=0.999),
        'siatka': {
            'lam_zapominania': [0.99, 0.995, 0.999, 0.9995, 0.9999],
        },
    },
}


def _rozgrzej_numba():
    print('Rozgrzewanie kompilacji numba (JIT)...')
    import numpy as np
    import symulacja_fizyczna as fiz
    from rejestr_algorytmow import stworz_kontroler
    n = 2000
    dt = 1.0
    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, opoz = fiz.przygotuj_modele_stanowe(dt)
    at_array = np.full(n, -10.0)
    w = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)
    df_1s = pd.DataFrame({
        'Timestamp': pd.date_range('2024-01-01', periods=n, freq='1s'),
        'temperatura_powietrza_C': at_array, 'punkt_rosy_C': at_array - 2.0,
        'wiatr_m_s': np.full(n, 2.0), 'opad_mm': np.zeros(n), 'naslonecznienie_sekundy': np.zeros(n),
    })
    for nazwa in ALGORYTMY:
        k, m = stworz_kontroler(nazwa, max_switches_per_day=20)
        fiz.uruchom_kontroler(nazwa, k, m, df_1s, w, A_hd, B_hd, C_hd, D_hd, opoz, dt=dt, print_progress=False)
    print('Gotowe.\n')


def _przygotuj_okno(dni):
    import symulacja_fizyczna as fiz
    with redirect_stdout(io.StringIO()):
        zakres = fiz.wybierz_najzimniejsze_okno(SCIEZKA_CSV, dni)
        df = fiz.wczytaj_pogode_1s(SCIEZKA_CSV, zakres_dat=zakres, dt=KROK_S)
    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, opoz = fiz.przygotuj_modele_stanowe(KROK_S)
    w = fiz.wylicz_skladowa_pogodowa(df['temperatura_powietrza_C'].to_numpy(), A_wd, B_wd, C_wd, D_wd, KROK_S)
    with redirect_stdout(io.StringIO()):
        from rejestr_algorytmow import stworz_kontroler
        k_normy, m_normy = stworz_kontroler('algorytm_z_normy', max_switches_per_day=100)
        _, _, snow_ref, power_ref = fiz.uruchom_kontroler(
            'algorytm_z_normy', k_normy, m_normy, df, w, A_hd, B_hd, C_hd, D_hd, opoz, dt=KROK_S, print_progress=False)
    return zakres, df, w, (A_hd, B_hd, C_hd, D_hd, opoz), snow_ref, power_ref


def _uruchom_kombinacje(nazwa_algorytmu, nazwa_etapu, nastawy, df, w, modele_hd, snow_ref, power_ref):
    import symulacja_fizyczna as fiz
    from rejestr_algorytmow import stworz_kontroler
    A_hd, B_hd, C_hd, D_hd, opoz = modele_hd
    try:
        with redirect_stdout(io.StringIO()):
            k, m = stworz_kontroler(nazwa_algorytmu, max_switches_per_day=20, **nastawy)
            _, stats, _, _ = fiz.uruchom_kontroler(
                nazwa_algorytmu, k, m, df, w, A_hd, B_hd, C_hd, D_hd, opoz, dt=KROK_S,
                snow_reference_mm=snow_ref, power_reference_pct=power_ref, print_progress=False)
        wynik = dict(nastawy)
        wynik.update({'etap': nazwa_etapu, 'energia_kwh': stats['energia_kwh'],
                      'kara_bezpieczenstwa': stats['kara_bezpieczenstwa'],
                      'max_snieg_mm': stats.get('max_snieg_mm'), 'min_hrt': stats.get('min_hrt'),
                      'przelaczenia': stats.get('przelaczenia'), 'blad': None})
        return wynik
    except Exception:
        import traceback
        wynik = dict(nastawy)
        wynik.update({'etap': nazwa_etapu, 'energia_kwh': None, 'kara_bezpieczenstwa': None, 'blad': traceback.format_exc()})
        return wynik


def _klucz_sortowania(w):
    kara = w['kara_bezpieczenstwa']
    bezpieczny = kara is not None and kara <= KARA_TOLERANCJA
    if bezpieczny:
        return (0, w['energia_kwh'])
    return (1, kara if kara is not None else float('inf'))


_KLUCZE_STATYSTYK = ('etap', 'energia_kwh', 'kara_bezpieczenstwa', 'max_snieg_mm', 'min_hrt', 'przelaczenia', 'blad')


def _opis(w, domyslne=None):
    """Opisuje same hiperparametry kombinacji (pomija klucze statystyk wyniku). Gdy podano
    `domyslne`, kolejność/zbiór kluczy bierze z niego (spójne z resztą wywołań)."""
    klucze = domyslne.keys() if domyslne is not None else (k for k in w if k not in _KLUCZE_STATYSTYK)
    return ' '.join(f"{k}={w[k]:g}" for k in klucze if k in w)


def _wykonaj_siatke(nazwa_algorytmu, nazwa_etapu, kombinacje, dane_okna, t0, licznik_globalny, suma_globalna):
    df, w, modele_hd, snow_ref, power_ref = dane_okna
    wyniki = []
    with ProcessPoolExecutor(max_workers=LICZBA_WATKOW) as executor:
        futures = {executor.submit(_uruchom_kombinacje, nazwa_algorytmu, nazwa_etapu, kmb, df, w, modele_hd,
                                    snow_ref, power_ref): kmb for kmb in kombinacje}
        for i, future in enumerate(as_completed(futures), 1):
            wynik = future.result()
            wyniki.append(wynik)
            licznik_globalny[0] += 1
            elapsed = (time.time() - t0) / 60.0
            tempo = elapsed / licznik_globalny[0] if licznik_globalny[0] else 0.0
            eta_calosci = tempo * suma_globalna
            # --- WSKAŹNIK POSTĘPU: numer kombinacji w tym etapie + numer globalny/suma +
            # upłynięty czas + szacowany czas całości skryptu (aktualizowany na żywo z
            # dotychczasowego tempa) ---
            if wynik['blad'] is not None:
                print(f"[{nazwa_algorytmu}/{nazwa_etapu} {i}/{len(kombinacje)}] "
                      f"(globalnie {licznik_globalny[0]}/{suma_globalna}, {elapsed:.1f}/{eta_calosci:.1f} min) BŁĄD:\n{wynik['blad']}")
            else:
                print(f"[{nazwa_algorytmu}/{nazwa_etapu} {i}/{len(kombinacje)}] "
                      f"(globalnie {licznik_globalny[0]}/{suma_globalna}, {elapsed:.1f}/{eta_calosci:.1f} min) "
                      f"energia={wynik['energia_kwh']:.1f} kWh kara={wynik['kara_bezpieczenstwa']:.0f} "
                      f"{_opis(wynik)}")
    return sorted(wyniki, key=_klucz_sortowania)


def main():
    print('=' * 90)
    print(f'STROJENIE modeli adaptacyjnych (PID/ADRC/MPC + żywy model RLS) - lokalizacja: {LOKALIZACJA}')
    print(f'Etap A (zgrubny): {COARSE_DNI} dni najzimniejszej pogody.')
    print(f'Etap B (walidacja): {WALID_DNI} dni najzimniejszej pogody (ta sama lokalizacja).')
    print(f'Procesów: {LICZBA_WATKOW}')
    print('=' * 90)
    _rozgrzej_numba()
    t0 = time.time()

    kombinacje_a_per_alg = {}
    for nazwa_algorytmu, definicja in ALGORYTMY.items():
        siatka = definicja['siatka']
        domyslne = definicja['domyslne']
        # Każda kombinacja = pełny zestaw DOMYŚLNYCH nastaw z NADPISANYMI tylko tymi z
        # siatki - inaczej parametry spoza siatki (np. pi_kc_korekta_percent dla PID) by
        # zniknęły z wyniku, i etap B (walidacja) nie miałby ich skąd odtworzyć.
        kombinacje_a_per_alg[nazwa_algorytmu] = [
            {**domyslne, **dict(zip(siatka.keys(), wart))} for wart in itertools.product(*siatka.values())
        ]
    suma_globalna = sum(len(k) for k in kombinacje_a_per_alg.values()) + len(ALGORYTMY)  # + baseline'y etapu A
    licznik_globalny = [0]

    print(f'\nPrzygotowanie okna zgrubnego ({COARSE_DNI} dni)...')
    zakres_a, df_a, w_a, modele_a, snow_ref_a, power_ref_a = _przygotuj_okno(COARSE_DNI)
    print(f'Okno: {zakres_a[0]} -> {zakres_a[1]}')
    dane_a = (df_a, w_a, modele_a, snow_ref_a, power_ref_a)

    zwyciezcy_a = {}
    for nazwa_algorytmu, definicja in ALGORYTMY.items():
        domyslne = definicja['domyslne']
        print(f'\n--- {nazwa_algorytmu}: baseline (nastawy domyślne) ---')
        baseline = _wykonaj_siatke(nazwa_algorytmu, 'baseline', [dict(domyslne)], dane_a, t0,
                                    licznik_globalny, suma_globalna)[0]
        print(f"BASELINE {nazwa_algorytmu}: energia={baseline['energia_kwh']:.1f} kWh kara={baseline['kara_bezpieczenstwa']:.0f}")

        kombinacje_a = kombinacje_a_per_alg[nazwa_algorytmu]
        print(f'\n--- {nazwa_algorytmu}: etap A, {len(kombinacje_a)} kombinacji '
              f'({" x ".join(f"{len(v)}x{k}" for k, v in definicja["siatka"].items())}) ---')
        wyniki_a = _wykonaj_siatke(nazwa_algorytmu, 'A', kombinacje_a, dane_a, t0, licznik_globalny, suma_globalna)
        pd.DataFrame(wyniki_a).to_csv(os.path.join(FOLDER_WYNIKOW, f'{nazwa_algorytmu}_etap_a.csv'), index=False)
        zwyciezca_a = wyniki_a[0]
        print(f"Zwycięzca etapu A ({nazwa_algorytmu}): {_opis(zwyciezca_a, domyslne)} "
              f"energia={zwyciezca_a['energia_kwh']:.1f} kWh kara={zwyciezca_a['kara_bezpieczenstwa']:.0f}")
        zwyciezcy_a[nazwa_algorytmu] = {'baseline': baseline, 'wyniki_a': wyniki_a}

    # --- Etap B: WALIDACJA na dłuższym oknie - baseline + top-K z etapu A, per algorytm ---
    print(f'\nPrzygotowanie okna walidacyjnego ({WALID_DNI} dni)...')
    zakres_b, df_b, w_b, modele_b, snow_ref_b, power_ref_b = _przygotuj_okno(WALID_DNI)
    print(f'Okno: {zakres_b[0]} -> {zakres_b[1]}')
    dane_b = (df_b, w_b, modele_b, snow_ref_b, power_ref_b)

    kombinacje_b_per_alg = {}
    for nazwa_algorytmu, info in zwyciezcy_a.items():
        domyslne = ALGORYTMY[nazwa_algorytmu]['domyslne']
        widziane = set()
        top_k = []
        for wnk in info['wyniki_a']:
            klucz = tuple(wnk[k] for k in domyslne)
            if klucz not in widziane:
                widziane.add(klucz)
                top_k.append({k: wnk[k] for k in domyslne})
            if len(top_k) >= TOP_K_DO_WALIDACJI:
                break
        kombinacje_b_per_alg[nazwa_algorytmu] = [dict(domyslne)] + top_k

    suma_globalna_b = sum(len(k) for k in kombinacje_b_per_alg.values())
    licznik_globalny_b = [0]
    wyniki_koncowe = {}
    for nazwa_algorytmu, kombinacje_b in kombinacje_b_per_alg.items():
        domyslne = ALGORYTMY[nazwa_algorytmu]['domyslne']
        print(f'\n--- {nazwa_algorytmu}: etap B (walidacja), {len(kombinacje_b)} kandydatów (baseline + '
              f'top {len(kombinacje_b) - 1}) ---')
        wyniki_b = _wykonaj_siatke(nazwa_algorytmu, 'B_walidacja', kombinacje_b, dane_b, t0,
                                    licznik_globalny_b, suma_globalna_b)
        pd.DataFrame(wyniki_b).to_csv(os.path.join(FOLDER_WYNIKOW, f'{nazwa_algorytmu}_etap_b_walidacja.csv'), index=False)

        zwyciezca_b = wyniki_b[0]
        baseline_b = next(wnk for wnk in wyniki_b if all(wnk[k] == domyslne[k] for k in domyslne))
        oszczednosc_pct = (100.0 * (1.0 - zwyciezca_b['energia_kwh'] / baseline_b['energia_kwh'])
                            if baseline_b['energia_kwh'] else 0.0)
        wyniki_koncowe[nazwa_algorytmu] = {
            'baseline': baseline_b, 'zwyciezca': zwyciezca_b, 'oszczednosc_energii_pct': oszczednosc_pct,
            'kandydaci_walidowani': kombinacje_b,
        }
        print(f"\nWYNIK {nazwa_algorytmu}:")
        print(f"  Baseline:   energia={baseline_b['energia_kwh']:.1f} kWh kara={baseline_b['kara_bezpieczenstwa']:.0f}")
        print(f"  Zwycięzca:  energia={zwyciezca_b['energia_kwh']:.1f} kWh kara={zwyciezca_b['kara_bezpieczenstwa']:.0f}"
              f" ({oszczednosc_pct:+.1f}% energii vs baseline)")
        print(f"  Nastawy zwycięzcy: {_opis(zwyciezca_b, domyslne)}")
        if zwyciezca_b['kara_bezpieczenstwa'] > KARA_TOLERANCJA:
            print('  UWAGA: nawet zwycięzca ma niezerową karę bezpieczeństwa na oknie walidacyjnym - '
                  'NIE traktować automatycznie jako gotowego do wdrożenia.')

    with open(os.path.join(FOLDER_WYNIKOW, 'zwyciezcy.json'), 'w', encoding='utf-8') as f:
        json.dump({'lokalizacja': LOKALIZACJA, 'okno_zgrubne': [str(x) for x in zakres_a],
                   'okno_walidacja': [str(x) for x in zakres_b], 'wyniki': wyniki_koncowe},
                  f, indent=2, ensure_ascii=False)

    calkowity_czas_min = (time.time() - t0) / 60.0
    print('\n' + '=' * 90)
    print(f"Całość: {calkowity_czas_min:.1f} min. Wyniki w: {FOLDER_WYNIKOW}")
    print('=' * 90)


if __name__ == '__main__':
    main()
