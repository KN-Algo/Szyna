# testy/strojenie_fuzzy_2v2.py
#
# Przeszukanie nastaw silnika FL2v2 (funkcja_fuzzy_ryzyko_2v2_strojony.py) - na życzenie użytkownika
# (2026-09-28): "przeszukać nastawy dla fuzzy ryzyko 2v2, zrobić kopię, iteracyjnie sprawdzać
# poprawność tamtych nastaw na najzimniejszym terenie przez miesiąc".
#
# METODOLOGIA (koarse-to-fine, jak zapowiedziane w AGENTS.md "Strojenie progów (grid search)"):
#   Etap A (zgrubny, krótkie okno ~COARSE_DNI dni najzimniejszej pogody na LOKALIZACJA_STROJENIA):
#     pełna siatka 3 najważniejszych progów (prog_chlodno, ryzyko_wspolczynnik, ryzyko_prog_moc),
#     reszta na wartościach domyślnych (= oryginał fuzzy_ryzyko_2v2).
#   Etap B (dostrojenie, to samo krótkie okno): wokół najlepszego punktu z etapu A, siatka
#     pozostałych 3 progów (prog_mrozno, moc_low, moc_med).
#   Etap C (WALIDACJA, długie okno ~WALID_DNI dni = "miesiąc" najzimniejszej pogody, TA SAMA
#     lokalizacja): powtórzenie symulacji dla baseline + TOP_K najlepszych kandydatów z A+B na
#     długim oknie - to jest "iteracyjne sprawdzenie poprawności" z prośby użytkownika (krótkie
#     okno tylko przesiewa kandydatów, decyzja końcowa zapada na długim). Zwycięzca etapu C to
#     ostateczny wynik.
#
# OCENA (ta sama filozofia co reszta projektu - bezpieczeństwo NADRZĘDNE nad energią):
#   - kandydat "bezpieczny" = kara_bezpieczenstwa <= KARA_TOLERANCJA (prawie zero - szum numeryczny)
#   - wśród bezpiecznych: mniejsza energia_kwh = lepszy
#   - jeśli ŻADEN kandydat w danym oknie nie jest bezpieczny: mniejsza kara_bezpieczenstwa = lepszy
#     (nigdy nie wybieramy "taniego, ale niebezpiecznego" kandydata, gdy jest bezpieczniejsza opcja)
#   Symulacja liczona z TYM SAMYM bezpiecznikiem normy (snow_reference_mm/power_reference_pct) co w
#   głównym przeglądzie (fuzzy_ryzyko_2v2* ma 'bezpiecznik': True w rejestrze) - wynik strojenia jest
#   więc bezpośrednio porównywalny z tym, jak algorytm zachowa się w properym przebiegu.
#
# Lokalizacja: domyślnie ojmiakon (najzimniejsza w projekcie - patrz 10 najzimniejszych lokalizacji
# w innych skryptach), nadpisywalna SZYNA_STROJENIE_LOKALIZACJA.
#
# Wynik: testy/../wyniki/strojenie_fuzzy_2v2/{etap_a.csv, etap_b.csv, etap_c_walidacja.csv,
# zwyciezca.json} + wypisany na konsoli finałowy zestaw nastaw gotowy do wklejenia jako nowe
# wartości DOMYŚLNE w silniki_fuzzy.py (FL2V2_*_DOMYSLNY), jeśli użytkownik zdecyduje się je przyjąć.
#
# Uruchomienie (z katalogu Benchmark_crt/benchmark):
#   python testy/strojenie_fuzzy_2v2.py

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
FOLDER_WYNIKOW = os.path.join(BASE_DIR, 'wyniki', 'strojenie_fuzzy_2v2')
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)

NAZWA_ALGORYTMU = 'fuzzy_ryzyko_2v2_strojony'
LOKALIZACJA = os.environ.get('SZYNA_STROJENIE_LOKALIZACJA', 'ojmiakon_60min_2025')
SCIEZKA_CSV = os.path.join(FOLDER_POGODA, f'{LOKALIZACJA}.csv')
COARSE_DNI = int(os.environ.get('SZYNA_STROJENIE_DNI_ZGRUBNE', '10'))
WALID_DNI = int(os.environ.get('SZYNA_STROJENIE_DNI_WALIDACJA', '30'))  # "miesiąc" z prośby użytkownika
KROK_S = float(os.environ.get('SZYNA_KROK_S', '10.0'))
TOP_K_DO_WALIDACJI = int(os.environ.get('SZYNA_STROJENIE_TOP_K', '5'))
KARA_TOLERANCJA = 1.0  # °C*s - poniżej tego kara_bezpieczenstwa traktowana jako "bezpieczna" (szum numeryczny)
LICZBA_WATKOW = int(os.environ.get('SZYNA_LICZBA_WATKOW', str(max(1, os.cpu_count() - 1))))

# Wartości domyślne (= oryginał fuzzy_ryzyko_2v2) - baseline, ZAWSZE w gridzie jako punkt odniesienia.
DOMYSLNE = dict(prog_chlodno=3.0, prog_mrozno=6.0, prog_goraco=9.0,
                ryzyko_wspolczynnik=3.0, ryzyko_prog_bonus=8.0, ryzyko_prog_moc=5.0,
                moc_low=25.0, moc_med=60.0)

# --- Etap A: 3 najważniejsze progi, reszta na domyślnych ---
SIATKA_A = {
    'prog_chlodno': [2.0, 3.0, 4.0],
    'ryzyko_wspolczynnik': [2.0, 3.0, 4.0],
    'ryzyko_prog_moc': [3.0, 5.0, 7.0],
}

# --- Etap B: pozostałe 3 progi, wokół zwycięzcy etapu A ---
SIATKA_B = {
    'prog_mrozno': [5.0, 6.0, 8.0],
    'moc_low': [20.0, 25.0, 30.0],
    'moc_med': [50.0, 60.0, 70.0],
}


def _rozgrzej_numba():
    print('Rozgrzewanie kompilacji numba (JIT)...')
    import numpy as np
    import symulacja_fizyczna as fiz
    from rejestr_algorytmow import stworz_kontroler
    n = 2000
    dt = 1.0
    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, opoz = fiz.przygotuj_modele_stanowe(dt)
    at_array = __import__('numpy').full(n, -10.0)
    w = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)
    df_1s = pd.DataFrame({
        'Timestamp': pd.date_range('2024-01-01', periods=n, freq='1s'),
        'temperatura_powietrza_C': at_array, 'punkt_rosy_C': at_array - 2.0,
        'wiatr_m_s': np.full(n, 2.0), 'opad_mm': np.zeros(n), 'naslonecznienie_sekundy': np.zeros(n),
    })
    k, m = stworz_kontroler(NAZWA_ALGORYTMU, max_switches_per_day=20)
    fiz.uruchom_kontroler('rozgrzewka', k, m, df_1s, w, A_hd, B_hd, C_hd, D_hd, opoz, dt=dt, print_progress=False)
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


def _uruchom_kombinacje(nazwa_etapu, nastawy, df, w, modele_hd, snow_ref, power_ref):
    import symulacja_fizyczna as fiz
    from rejestr_algorytmow import stworz_kontroler
    A_hd, B_hd, C_hd, D_hd, opoz = modele_hd
    try:
        with redirect_stdout(io.StringIO()):
            k, m = stworz_kontroler(NAZWA_ALGORYTMU, max_switches_per_day=20, **nastawy)
            _, stats, _, _ = fiz.uruchom_kontroler(
                NAZWA_ALGORYTMU, k, m, df, w, A_hd, B_hd, C_hd, D_hd, opoz, dt=KROK_S,
                snow_reference_mm=snow_ref, power_reference_pct=power_ref, print_progress=False)
        wynik = dict(nastawy)
        wynik.update({'etap': nazwa_etapu, 'energia_kwh': stats['energia_kwh'],
                      'kara_bezpieczenstwa': stats['kara_bezpieczenstwa'],
                      'kara_bezpieczenstwa_hrt': stats.get('kara_bezpieczenstwa_hrt'),
                      'kara_bezpieczenstwa_crt': stats.get('kara_bezpieczenstwa_crt'),
                      'max_snieg_mm': stats['max_snieg_mm'], 'min_hrt': stats['min_hrt'],
                      'przelaczenia': stats['przelaczenia'], 'blad': None})
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


def _uzupelnij_z_domyslnych(czesciowe):
    pelne = dict(DOMYSLNE)
    pelne.update(czesciowe)
    return pelne


def _wykonaj_siatke(nazwa_etapu, kombinacje, dane_okna, t0):
    df, w, modele_hd, snow_ref, power_ref = dane_okna
    wyniki = []
    with ProcessPoolExecutor(max_workers=LICZBA_WATKOW) as executor:
        futures = {executor.submit(_uruchom_kombinacje, nazwa_etapu, kmb, df, w, modele_hd, snow_ref, power_ref): kmb
                   for kmb in kombinacje}
        for i, future in enumerate(as_completed(futures), 1):
            wynik = future.result()
            wyniki.append(wynik)
            elapsed = (time.time() - t0) / 60.0
            if wynik['blad'] is not None:
                print(f"[{nazwa_etapu} {i}/{len(kombinacje)}] BŁĄD (upłynęło {elapsed:.1f} min):\n{wynik['blad']}")
            else:
                print(f"[{nazwa_etapu} {i}/{len(kombinacje)}] energia={wynik['energia_kwh']:.1f} kWh  "
                      f"kara={wynik['kara_bezpieczenstwa']:.0f}  {kombinacje_do_opisu(wynik)} (upłynęło {elapsed:.1f} min)")
    return sorted(wyniki, key=_klucz_sortowania)


def kombinacje_do_opisu(w):
    return ' '.join(f"{k}={w[k]:g}" for k in DOMYSLNE if k in w)


def main():
    print('=' * 90)
    print(f'STROJENIE fuzzy_ryzyko_2v2 (silnik FL2v2) - lokalizacja: {LOKALIZACJA}')
    print(f'Etap A/B (zgrubny+dostrojenie): {COARSE_DNI} dni najzimniejszej pogody.')
    print(f'Etap C (walidacja): {WALID_DNI} dni najzimniejszej pogody (ta sama lokalizacja).')
    print(f'Procesów: {LICZBA_WATKOW}')
    print('=' * 90)
    _rozgrzej_numba()
    t0 = time.time()

    print(f'\nPrzygotowanie okna zgrubnego ({COARSE_DNI} dni)...')
    zakres_a, df_a, w_a, modele_a, snow_ref_a, power_ref_a = _przygotuj_okno(COARSE_DNI)
    print(f'Okno: {zakres_a[0]} -> {zakres_a[1]}')
    dane_a = (df_a, w_a, modele_a, snow_ref_a, power_ref_a)

    # baseline (nastawy domyślne = oryginał fuzzy_ryzyko_2v2) - zawsze liczony jako punkt odniesienia
    baseline_a = _wykonaj_siatke('baseline', [dict(DOMYSLNE)], dane_a, t0)[0]
    print(f"\nBASELINE (oryginał fuzzy_ryzyko_2v2) na oknie zgrubnym: energia={baseline_a['energia_kwh']:.1f} kWh, "
          f"kara={baseline_a['kara_bezpieczenstwa']:.0f}")

    # --- Etap A ---
    kombinacje_a = [_uzupelnij_z_domyslnych(dict(zip(SIATKA_A.keys(), wart)))
                    for wart in itertools.product(*SIATKA_A.values())]
    print(f'\nEtap A: {len(kombinacje_a)} kombinacji ({" x ".join(f"{len(v)}x{k}" for k, v in SIATKA_A.items())})')
    wyniki_a = _wykonaj_siatke('A', kombinacje_a, dane_a, t0)
    pd.DataFrame(wyniki_a).to_csv(os.path.join(FOLDER_WYNIKOW, 'etap_a.csv'), index=False)
    zwyciezca_a = wyniki_a[0]
    print(f"\nZwycięzca etapu A: {kombinacje_do_opisu(zwyciezca_a)}  "
          f"energia={zwyciezca_a['energia_kwh']:.1f} kWh  kara={zwyciezca_a['kara_bezpieczenstwa']:.0f}")

    # --- Etap B: dostrojenie pozostałych progów wokół zwycięzcy A ---
    baza_b = {k: zwyciezca_a[k] for k in SIATKA_A}  # 3 progi z etapu A zamrożone na zwycięskiej wartości
    kombinacje_b = [_uzupelnij_z_domyslnych({**baza_b, **dict(zip(SIATKA_B.keys(), wart))})
                    for wart in itertools.product(*SIATKA_B.values())]
    print(f'\nEtap B: {len(kombinacje_b)} kombinacji ({" x ".join(f"{len(v)}x{k}" for k, v in SIATKA_B.items())})')
    wyniki_b = _wykonaj_siatke('B', kombinacje_b, dane_a, t0)
    pd.DataFrame(wyniki_b).to_csv(os.path.join(FOLDER_WYNIKOW, 'etap_b.csv'), index=False)
    zwyciezca_b = wyniki_b[0]
    print(f"\nZwycięzca etapu B: {kombinacje_do_opisu(zwyciezca_b)}  "
          f"energia={zwyciezca_b['energia_kwh']:.1f} kWh  kara={zwyciezca_b['kara_bezpieczenstwa']:.0f}")

    # --- Etap C: WALIDACJA na długim (miesięcznym) oknie - baseline + top-K z A+B razem ---
    kandydaci = sorted(wyniki_a + wyniki_b, key=_klucz_sortowania)
    widziane = set()
    top_k = []
    for w in kandydaci:
        klucz = tuple(w[k] for k in DOMYSLNE)
        if klucz not in widziane:
            widziane.add(klucz)
            top_k.append({k: w[k] for k in DOMYSLNE})
        if len(top_k) >= TOP_K_DO_WALIDACJI:
            break
    kombinacje_c = [dict(DOMYSLNE)] + top_k  # baseline zawsze w walidacji, jako punkt odniesienia

    print(f'\nPrzygotowanie okna walidacyjnego ({WALID_DNI} dni)...')
    zakres_c, df_c, w_c, modele_c, snow_ref_c, power_ref_c = _przygotuj_okno(WALID_DNI)
    print(f'Okno: {zakres_c[0]} -> {zakres_c[1]}')
    dane_c = (df_c, w_c, modele_c, snow_ref_c, power_ref_c)
    print(f'\nEtap C (walidacja): {len(kombinacje_c)} kandydatów (baseline + top {len(top_k)} z etapów A/B)')
    wyniki_c = _wykonaj_siatke('C_walidacja', kombinacje_c, dane_c, t0)
    pd.DataFrame(wyniki_c).to_csv(os.path.join(FOLDER_WYNIKOW, 'etap_c_walidacja.csv'), index=False)

    zwyciezca_c = wyniki_c[0]
    baseline_c = next(w for w in wyniki_c if all(w[k] == DOMYSLNE[k] for k in DOMYSLNE))
    oszczednosc_pct = 100.0 * (1.0 - zwyciezca_c['energia_kwh'] / baseline_c['energia_kwh']) if baseline_c['energia_kwh'] else 0.0

    print('\n' + '=' * 90)
    print('WYNIK KOŃCOWY (po walidacji na długim oknie):')
    print(f"  Baseline (oryginał):  energia={baseline_c['energia_kwh']:.1f} kWh  kara={baseline_c['kara_bezpieczenstwa']:.0f}")
    print(f"  Zwycięzca:            energia={zwyciezca_c['energia_kwh']:.1f} kWh  kara={zwyciezca_c['kara_bezpieczenstwa']:.0f}"
          f"  ({oszczednosc_pct:+.1f}% energii vs baseline)")
    print(f"  Nastawy zwycięzcy: {kombinacje_do_opisu(zwyciezca_c)}")
    if zwyciezca_c['kara_bezpieczenstwa'] > KARA_TOLERANCJA:
        print('  UWAGA: nawet zwycięzca ma niezerową karę bezpieczeństwa - żaden przeszukany kandydat nie jest '
              'w pełni bezpieczny na oknie walidacyjnym. NIE traktować automatycznie jako gotowego do wdrożenia.')
    print('=' * 90)

    with open(os.path.join(FOLDER_WYNIKOW, 'zwyciezca.json'), 'w', encoding='utf-8') as f:
        json.dump({'lokalizacja': LOKALIZACJA, 'okno_zgrubne': [str(x) for x in zakres_a],
                   'okno_walidacja': [str(x) for x in zakres_c], 'baseline': baseline_c,
                   'zwyciezca': zwyciezca_c, 'top_k_walidowanych': kombinacje_c}, f, indent=2, ensure_ascii=False)

    calkowity_czas_min = (time.time() - t0) / 60.0
    print(f"\nCałość: {calkowity_czas_min:.1f} min. Wyniki w: {FOLDER_WYNIKOW}")


if __name__ == '__main__':
    main()
