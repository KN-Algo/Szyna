# ==============================================================================
# TEST: WSZYSTKIE ALGORYTMY, WSZYSTKIE LOKALIZACJE - duży przegląd wszystkich
# algorytmów (Algorytmy/rejestr_algorytmow.py) na WSZYSTKICH dostępnych
# plikach pogodowych (Pogoda_pomiary_15_minut/*.csv).
#
# Dla każdej lokalizacji/pliku pogodowego:
#   - uruchamia algorytm_z_normy jako pierwszy (wyznacznik dopuszczalnej ilości
#     śniegu - patrz symulacja_fizyczna.uruchom_kontroler),
#   - potem pozostałe algorytmy z rejestru (risk_function* z bezpiecznikiem
#     parytetu ze śniegiem względem normy),
#   - zapisuje CSV z pełną historią + wykresy przebiegów dla tej lokalizacji,
#   - dopisuje wiersz do zbiorczej tabeli statystyk (energia, przełączenia,
#     max śnieg, max HRT) - PO KAŻDEJ lokalizacji, żeby postęp był widoczny
#     na bieżąco, nawet jeśli któryś plik zawiedzie w trakcie.
#
# Na końcu generuje jedną dużą tabelę zbiorczą (PRZEGLAD_ZBIORCZY.csv) oraz
# wykres słupkowy porównujący wszystkie lokalizacje x algorytmy naraz.
# ==============================================================================

import os
import traceback
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import symulacja_fizyczna as fiz
from rejestr_algorytmow import ALGORYTMY, stworz_kontroler, podlega_bezpiecznikowi
import generuj_excel_podsumowanie

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER_POGODA = os.path.join(BASE_DIR, "Pogoda_pomiary_15_minut")
FOLDER_WYNIKOW = os.path.join(BASE_DIR, "wyniki", "przeglad_wielu_lokalizacji")
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)

MAX_SWITCHES_PER_DAY = 100  # budżet dzienny wywiedziony z życiowego budżetu przekaźnika (~500 000) - patrz test_wszystkie_rownolegle.py
NAZWA_ALGORYTMU_NORMY = 'algorytm_z_normy'

# Co ile sekund zapisujemy przebieg do CSV/wykresu (statystyki w PRZEGLAD_ZBIORCZY.csv
# liczone są ZAWSZE z pełnej rozdzielczości 1s wewnątrz uruchom_kontroler - to
# obniża TYLKO rozmiar zapisywanych przebiegów, nie dokładność żadnej statystyki).
# Przy 17 algorytmach x 43 lokalizacjach pełna rozdzielczość 1s dawałaby ~55-60GB
# (zmierzone: ~80MB na plik x 731 plików) - 60s (1 min) to ~60x mniej miejsca,
# a dla 7-dniowego okna nadal >10 tys. punktów na wykres/algorytm - więcej niż
# potrzeba do czytelnego przebiegu włącz/wyłącz. Ustaw na 1, żeby wrócić do
# pełnej rozdzielczości (jak w pozostałych dwóch skryptach testowych).
ZAPISZ_CO_N_SEKUND = 60

# None = bierzemy CAŁY zakres każdego pliku (pełne sezony XI-III, nie tylko
# najzimniejszy wycinek) - patrz symulacja_fizyczna.wczytaj_pogode_1s(zakres_dat=...).
# Przy 17 algorytmach x 43 lokalizacjach (w tym ~40 stacji z ~5-miesięcznym,
# godzinowym sezonem) to ok. 6.5-7 DÓB ciągłego liczenia (zmierzone empirycznie:
# ~554s na 500 tys. kroków dla wszystkich 17 algorytmów łącznie, x ~540 mln
# kroków sumarycznie po wszystkich lokalizacjach). Ustaw z powrotem na liczbę
# dni (np. 7), żeby ograniczyć się do najzimniejszego wycinka i skrócić czas.
MAX_DNI_NA_LOKALIZACJE = None

# WSZYSTKIE pliki pogodowe z folderu (dowolna rozdzielczość - suwalki/wroclaw
# 15-minutowe, stacje ERA5-Land godzinowe) - nazwa lokalizacji to nazwa pliku
# bez rozszerzenia, więc nowe pliki dorzucone do folderu trafiają do przeglądu
# automatycznie, bez zmian w tym skrypcie.
PLIKI_POGODOWE = {
    os.path.splitext(nazwa_pliku)[0]: os.path.join(FOLDER_POGODA, nazwa_pliku)
    for nazwa_pliku in sorted(os.listdir(FOLDER_POGODA))
    if nazwa_pliku.endswith('.csv')
}

# Kolor per algorytm generowany automatycznie z rejestru - przy 17+ algorytmach
# ręczny słownik gwarantowałby KeyError przy każdym nowym wpisie w rejestrze.
_PALETA = plt.get_cmap('tab20').colors
COLORS = {nazwa: _PALETA[i % len(_PALETA)] for i, nazwa in enumerate(ALGORYTMY)}


def zapisz_wykresy_lokalizacji(nazwa_lokalizacji, df_1s, at_array, results, stats_list):
    fig, axes = plt.subplots(4, 1, figsize=(16, 18), sharex=True)

    ax = axes[0]
    ax.plot(df_1s['Timestamp'], at_array, color='black', linewidth=0.6, alpha=0.4, label='AT (powietrze)')
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['HRT'], color=COLORS[name], linewidth=0.8, label=f'HRT {name}')
    ax.set_ylabel('Temperatura [°C]')
    ax.set_title(f'{nazwa_lokalizacji}: Temperatura szyny ogrzewanej (HRT)')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    ax = axes[1]
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['Moc_procent'], color=COLORS[name], linewidth=0.6, label=name, alpha=0.8)
    ax.set_ylabel('Moc grzania [%]')
    ax.set_title('Sterowanie mocą grzania w czasie')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    ax = axes[2]
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['Energia_kWh_skumulowana'], color=COLORS[name], linewidth=1.3, label=name)
    ax.set_ylabel('Energia skumulowana [kWh]')
    ax.set_title('Zużycie energii w czasie (skumulowane)')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    ax = axes[3]
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['Snieg_mm'], color=COLORS[name], linewidth=0.9, label=f'Śnieg {name}')
    ax.set_ylabel('Grubość śniegu [mm]')
    ax.set_xlabel('Czas')
    ax.set_title('Zaleganie śniegu (algorytm_z_normy = górny wyznacznik dopuszczalnej ilości)')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    plt.tight_layout()
    fig_path = os.path.join(FOLDER_WYNIKOW, f"{nazwa_lokalizacji}_przebiegi.png")
    plt.savefig(fig_path, dpi=100)
    plt.close(fig)
    print(f"  Zapisano wykres: {fig_path}")

    fig2, (bx1, bx2) = plt.subplots(1, 2, figsize=(14, 5))
    names = [s['name'] for s in stats_list]
    energie = [s['energia_kwh'] for s in stats_list]
    przelaczenia = [s['przelaczenia'] for s in stats_list]
    bar_colors = [COLORS[n] for n in names]

    bx1.bar(names, energie, color=bar_colors)
    bx1.set_ylabel('Zużyta energia [kWh]')
    bx1.set_title(f'{nazwa_lokalizacji}: Całkowite zużycie energii')
    bx1.tick_params(axis='x', rotation=20)
    bx1.grid(True, axis='y', linestyle=':', alpha=0.5)

    bx2.bar(names, przelaczenia, color=bar_colors)
    bx2.set_ylabel('Liczba przełączeń')
    bx2.set_title(f'{nazwa_lokalizacji}: Całkowita liczba przełączeń')
    bx2.tick_params(axis='x', rotation=20)
    bx2.grid(True, axis='y', linestyle=':', alpha=0.5)

    plt.tight_layout()
    fig_path2 = os.path.join(FOLDER_WYNIKOW, f"{nazwa_lokalizacji}_podsumowanie.png")
    plt.savefig(fig_path2, dpi=100)
    plt.close(fig2)
    print(f"  Zapisano wykres: {fig_path2}")


def _przygotuj_do_zapisu(df_hist, co_n_sekund=ZAPISZ_CO_N_SEKUND):
    return fiz.przygotuj_do_zapisu(df_hist, co_n_sekund)


def uruchom_dla_lokalizacji(nazwa_lokalizacji, sciezka_csv):
    print(f"\n{'=' * 100}\nLOKALIZACJA: {nazwa_lokalizacji}  ({sciezka_csv})\n{'=' * 100}")

    # Bierzemy NAJZIMNIEJSZE okno z pliku (nie "pierwsze N dni") - sezon XI-III
    # nie jest jednorodnie zimny (np. początek listopada bywa jeszcze ciepły),
    # a porównanie algorytmów ma sens tylko tam, gdzie faktycznie muszą grzać.
    zakres_dat = None
    if MAX_DNI_NA_LOKALIZACJE is not None:
        zakres_dat = fiz.wybierz_najzimniejsze_okno(sciezka_csv, MAX_DNI_NA_LOKALIZACJE)
        print(f"Najzimniejsze okno ({MAX_DNI_NA_LOKALIZACJE} dni): {zakres_dat[0]} -> {zakres_dat[1]}")

    df_1s = fiz.wczytaj_pogode_1s(sciezka_csv, zakres_dat=zakres_dat)
    dt = 1.0

    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(dt)
    at_array = df_1s['temperatura_powietrza_C'].to_numpy()
    hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)

    kontroler_normy, metoda_normy = stworz_kontroler(NAZWA_ALGORYTMU_NORMY, max_switches_per_day=MAX_SWITCHES_PER_DAY)
    df_normy, stats_normy, snow_reference_mm, power_reference_pct = fiz.uruchom_kontroler(
        NAZWA_ALGORYTMU_NORMY, kontroler_normy, metoda_normy, df_1s, hrt_weather_all,
        A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt,
    )
    stats_normy['lokalizacja'] = nazwa_lokalizacji
    df_normy_zapis = _przygotuj_do_zapisu(df_normy)
    df_normy_zapis.to_csv(os.path.join(FOLDER_WYNIKOW, f"{nazwa_lokalizacji}_{NAZWA_ALGORYTMU_NORMY}.csv"), index=False)

    results = {NAZWA_ALGORYTMU_NORMY: df_normy_zapis}
    stats_list = [stats_normy]

    for nazwa in ALGORYTMY:
        if nazwa == NAZWA_ALGORYTMU_NORMY:
            continue

        # Jeden wadliwy algorytm NIE MOŻE zabrać wyników pozostałych 16 dla tej
        # lokalizacji - przy wielodniowym, bezobsługowym przebiegu (superkomputer)
        # strata całej (nawet kilkunastogodzinnej) lokalizacji z powodu jednego
        # algorytmu byłaby zbyt kosztowna. Lokalizacja kończy się błędem tylko,
        # gdy zawiedzie algorytm_z_normy (bo bez niego bezpiecznik nie ma czego
        # pilnować) - to jest łapane wyżej, w main().
        try:
            czy_bezpiecznik = podlega_bezpiecznikowi(nazwa)
            referencja_sniegu = snow_reference_mm if czy_bezpiecznik else None
            referencja_mocy = power_reference_pct if czy_bezpiecznik else None

            kontroler, metoda = stworz_kontroler(nazwa, max_switches_per_day=MAX_SWITCHES_PER_DAY)
            df_hist, stats, _, _ = fiz.uruchom_kontroler(
                nazwa, kontroler, metoda, df_1s, hrt_weather_all,
                A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt,
                snow_reference_mm=referencja_sniegu, power_reference_pct=referencja_mocy,
            )
        except Exception:
            print(f"\n!!! BŁĄD przy algorytmie '{nazwa}' dla lokalizacji {nazwa_lokalizacji} - "
                  f"pomijam TYLKO ten algorytm, kontynuuję z pozostałymi !!!")
            traceback.print_exc()
            continue

        stats['lokalizacja'] = nazwa_lokalizacji
        df_hist_zapis = _przygotuj_do_zapisu(df_hist)
        df_hist_zapis.to_csv(os.path.join(FOLDER_WYNIKOW, f"{nazwa_lokalizacji}_{nazwa}.csv"), index=False)

        results[nazwa] = df_hist_zapis
        stats_list.append(stats)

    df_1s_wykres = _przygotuj_do_zapisu(df_1s[['Timestamp', 'temperatura_powietrza_C']])
    zapisz_wykresy_lokalizacji(nazwa_lokalizacji, df_1s_wykres, df_1s_wykres['temperatura_powietrza_C'].to_numpy(), results, stats_list)

    print(f"\n--- PODSUMOWANIE: {nazwa_lokalizacji} ---")
    for s in stats_list:
        przelaczen_na_dobe = s['przelaczenia'] / max(s['dni'], 1e-6)
        print(f"  {s['name']:<20} | energia={s['energia_kwh']:9.2f} kWh | przełączenia={s['przelaczenia']:5d} "
              f"({przelaczen_na_dobe:5.2f}/dobę) | max_śnieg={s['max_snieg_mm']:7.2f} mm | "
              f"max_lód={s['max_lod_mm']:6.2f} mm | max_HRT={s['max_hrt']:6.2f} °C")

    return stats_list


def zapisz_wykres_zbiorczy(df_wszystkie):
    lokalizacje = list(df_wszystkie['lokalizacja'].unique())
    algorytmy = list(ALGORYTMY.keys())

    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    metryki = [
        ('energia_kwh', 'Zużyta energia [kWh]', axes[0, 0]),
        ('przelaczenia', 'Liczba przełączeń', axes[0, 1]),
        ('max_snieg_mm', 'Maksymalna grubość śniegu [mm]', axes[1, 0]),
        ('max_hrt', 'Maksymalna temperatura HRT [°C]', axes[1, 1]),
    ]

    width = 0.8 / len(algorytmy)
    x = np.arange(len(lokalizacje))

    for kolumna, tytul, ax in metryki:
        for i, nazwa_alg in enumerate(algorytmy):
            wartosci = []
            for lok in lokalizacje:
                wiersz = df_wszystkie[(df_wszystkie['lokalizacja'] == lok) & (df_wszystkie['name'] == nazwa_alg)]
                wartosci.append(wiersz[kolumna].iloc[0] if len(wiersz) else 0)
            ax.bar(x + i * width, wartosci, width, label=nazwa_alg, color=COLORS.get(nazwa_alg))
        ax.set_xticks(x + width * (len(algorytmy) - 1) / 2)
        ax.set_xticklabels(lokalizacje, rotation=15)
        ax.set_ylabel(tytul)
        ax.set_title(tytul)
        ax.grid(True, axis='y', linestyle=':', alpha=0.5)
        ax.legend(fontsize=8)

    plt.tight_layout()
    fig_path = os.path.join(FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.png")
    plt.savefig(fig_path, dpi=110)
    plt.close(fig)
    print(f"\nZapisano zbiorczy wykres: {fig_path}")


def main():
    wszystkie_statystyki = []

    for nazwa_lokalizacji, sciezka in PLIKI_POGODOWE.items():
        try:
            stats_list = uruchom_dla_lokalizacji(nazwa_lokalizacji, sciezka)
            wszystkie_statystyki.extend(stats_list)
        except Exception:
            print(f"\n!!! BŁĄD przy przetwarzaniu {nazwa_lokalizacji} - pomijam, kontynuuję dalej !!!")
            traceback.print_exc()
            continue

        # Zapisujemy zbiorczą tabelę PO KAŻDEJ lokalizacji - postęp widoczny na bieżąco.
        df_wszystkie = pd.DataFrame(wszystkie_statystyki)
        df_wszystkie.to_csv(os.path.join(FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.csv"), index=False)

    if not wszystkie_statystyki:
        print("Brak wyników - wszystkie lokalizacje zakończyły się błędem.")
        return

    df_wszystkie = pd.DataFrame(wszystkie_statystyki)
    kolumny = ['lokalizacja', 'name', 'energia_kwh', 'przelaczenia', 'max_snieg_mm', 'max_lod_mm', 'max_hrt', 'min_hrt',
               'srednia_moc_pct', 'godziny_ze_sniegiem', 'zabezpieczen_normy_uzytych', 'dni', 'flops_rzeczywiste']
    kolumny = [k for k in kolumny if k in df_wszystkie.columns]
    df_wszystkie = df_wszystkie[kolumny]
    df_wszystkie.to_csv(os.path.join(FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.csv"), index=False)

    print("\n" + "=" * 110)
    print("TABELA ZBIORCZA - WSZYSTKIE LOKALIZACJE x ALGORYTMY")
    print("=" * 110)
    for lok in df_wszystkie['lokalizacja'].unique():
        print(f"\n--- {lok} ---")
        sub = df_wszystkie[df_wszystkie['lokalizacja'] == lok]
        for _, r in sub.iterrows():
            print(f"  {r['name']:<20} | energia={r['energia_kwh']:9.2f} kWh | przełączenia={r['przelaczenia']:5.0f} | "
                  f"max_śnieg={r['max_snieg_mm']:7.2f} mm | max_HRT={r['max_hrt']:6.2f} °C")
    print("=" * 110)

    zapisz_wykres_zbiorczy(df_wszystkie)

    # Excel z tej samej PRZEGLAD_ZBIORCZY.csv, którą właśnie zapisaliśmy powyżej -
    # w try/except, żeby ewentualny problem z generowaniem xlsx (np. brak openpyxl
    # na innej maszynie) nie zniweczył wielogodzinnych wyników z samej symulacji.
    try:
        generuj_excel_podsumowanie.main()
    except Exception:
        print("\n!!! BŁĄD przy generowaniu Podsumowanie_wynikow.xlsx - CSV/PNG są bezpieczne, "
              "spróbuj uruchomić generuj_excel_podsumowanie.py osobno !!!")
        traceback.print_exc()

    print(f"\nGotowe. Wszystkie pliki CSV, PNG i Excel w folderze: {FOLDER_WYNIKOW}")


if __name__ == '__main__':
    main()
