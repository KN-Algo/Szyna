# ==============================================================================
# TEST: WSZYSTKIE ALGORYTMY, JEDNA LOKALIZACJA - porównanie algorytmów sterowania
# ogrzewaniem rozjazdów na jednym pliku pogodowym.
#
# Rozszerzenie test_jeden_algorytm_jedna_lokalizacja.py: zamiast testować jeden
# wybrany algorytm, uruchamia WSZYSTKIE algorytmy z Algorytmy/rejestr_algorytmow.py
# na tej samej symulacji fizycznej (symulacja_fizyczna.py) i porównuje wyniki.
#
# WAŻNE: algorytm_z_normy jest URUCHAMIANY JAKO PIERWSZY i traktowany jako
# WYZNACZNIK dopuszczalnej ilości śniegu na szynie - "nasze" algorytmy
# (risk_function, risk_function_pid) dostają jego przebieg grubości śniegu jako
# referencję i mają wbudowany bezpiecznik: NIE WOLNO im dopuścić do większej
# ilości śniegu na szynie w danej chwili niż miałby algorytm z normy (patrz
# parametr snow_reference_mm w symulacja_fizyczna.uruchom_kontroler).
#
# Wynik: CSV z historią każdego wariantu (Benchmark/benchmark/wyniki/) oraz
# wykresy porównawcze PNG (HRT, moc/energia skumulowana, śnieg, podsumowanie
# słupkowe zużycia energii i liczby przełączeń).
# ==============================================================================

import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # generujemy pliki PNG - nie wymaga interaktywnego okna
import matplotlib.pyplot as plt

import symulacja_fizyczna as fiz
from rejestr_algorytmow import ALGORYTMY, stworz_kontroler, podlega_bezpiecznikowi

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NAZWA_PLIKU_CSV = os.path.join(BASE_DIR, "Pogoda_pomiary_15_minut", "suwalki_15min_2023.csv")
FOLDER_WYNIKOW = os.path.join(BASE_DIR, "wyniki")
os.makedirs(FOLDER_WYNIKOW, exist_ok=True)

MAX_SWITCHES_PER_DAY = 12
NAZWA_ALGORYTMU_NORMY = 'algorytm_z_normy'  # wyznacznik dopuszczalnej ilości śniegu

# Kolor per algorytm generowany automatycznie z rejestru (a nie ręcznie wpisywany
# w słowniku) - przy 17+ algorytmach ręczny słownik gwarantowałby KeyError przy
# każdym nowym wpisie w rejestr_algorytmow.py.
_PALETA = plt.get_cmap('tab20').colors
COLORS = {nazwa: _PALETA[i % len(_PALETA)] for i, nazwa in enumerate(ALGORYTMY)}


def main():
    df_1s = fiz.wczytaj_pogode_1s(NAZWA_PLIKU_CSV)
    dt = 1.0

    print("Konwersja modeli transmitancyjnych do przestrzeni stanów...")
    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(dt)

    print("Wyliczanie wpływu środowiska (składowa CRT) - wspólna dla wszystkich wariantów...")
    at_array = df_1s['temperatura_powietrza_C'].to_numpy()
    hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)

    # --- 1. NAJPIERW algorytm z normy - jest wyznacznikiem dopuszczalnej ilości śniegu. ---
    kontroler_normy, metoda_normy = stworz_kontroler(NAZWA_ALGORYTMU_NORMY, max_switches_per_day=MAX_SWITCHES_PER_DAY)
    df_normy, stats_normy, snow_reference_mm, power_reference_pct = fiz.uruchom_kontroler(
        NAZWA_ALGORYTMU_NORMY, kontroler_normy, metoda_normy, df_1s, hrt_weather_all,
        A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt, snow_reference_mm=None,
    )
    out_csv = os.path.join(FOLDER_WYNIKOW, f"porownanie_{NAZWA_ALGORYTMU_NORMY}.csv")
    df_normy.to_csv(out_csv, index=False)
    print(f"  Zapisano: {out_csv}")

    results = {NAZWA_ALGORYTMU_NORMY: df_normy}
    stats_list = [stats_normy]

    # --- 2. Pozostałe algorytmy z rejestru. ---
    for nazwa in ALGORYTMY:
        if nazwa == NAZWA_ALGORYTMU_NORMY:
            continue

        # "Nasze" (inteligentne) algorytmy dostają śnieg+moc z normy jako bezpiecznik
        # parytetu - nie mogą go przekroczyć w żadnej chwili (patrz pole 'bezpiecznik'
        # w rejestr_algorytmow.py). compute_control i algorytm_z_normy są wyłączone.
        czy_bezpiecznik = podlega_bezpiecznikowi(nazwa)
        referencja_sniegu = snow_reference_mm if czy_bezpiecznik else None
        referencja_mocy = power_reference_pct if czy_bezpiecznik else None

        kontroler, metoda = stworz_kontroler(nazwa, max_switches_per_day=MAX_SWITCHES_PER_DAY)
        df_hist, stats, _, _ = fiz.uruchom_kontroler(
            nazwa, kontroler, metoda, df_1s, hrt_weather_all,
            A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt,
            snow_reference_mm=referencja_sniegu, power_reference_pct=referencja_mocy,
        )
        out_csv = os.path.join(FOLDER_WYNIKOW, f"porownanie_{nazwa}.csv")
        df_hist.to_csv(out_csv, index=False)
        print(f"  Zapisano: {out_csv}")

        results[nazwa] = df_hist
        stats_list.append(stats)

    stats_df = pd.DataFrame(stats_list)
    stats_csv = os.path.join(FOLDER_WYNIKOW, "porownanie_podsumowanie.csv")
    stats_df.to_csv(stats_csv, index=False)

    print("\n" + "=" * 100)
    print("PODSUMOWANIE PORÓWNANIA ALGORYTMÓW")
    print("=" * 100)
    for s in stats_list:
        przelaczen_na_dobe = s['przelaczenia'] / max(s['dni'], 1e-6)
        print(f"{s['name']:<20} | energia={s['energia_kwh']:8.2f} kWh | przełączenia={s['przelaczenia']:5d} "
              f"({przelaczen_na_dobe:5.2f}/dobę) | śr.moc={s['srednia_moc_pct']:5.1f}% | "
              f"max_śnieg={s['max_snieg_mm']:7.2f} mm | max_lód={s['max_lod_mm']:6.2f} mm | "
              f"HRT [{s['min_hrt']:6.2f}, {s['max_hrt']:6.2f}] °C | bezpiecznik×{s['zabezpieczen_normy_uzytych']}")
    print("=" * 100)

    # ==========================================================================
    # WYKRESY PORÓWNAWCZE
    # ==========================================================================
    fig, axes = plt.subplots(4, 1, figsize=(16, 18), sharex=True)

    ax = axes[0]
    ax.plot(df_1s['Timestamp'], at_array, color='black', linewidth=0.8, alpha=0.4, label='AT (powietrze)')
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['HRT'], color=COLORS[name], linewidth=1.0, label=f'HRT {name}')
    ax.set_ylabel('Temperatura [°C]')
    ax.set_title('Temperatura szyny ogrzewanej (HRT) dla poszczególnych algorytmów')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    ax = axes[1]
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['Moc_procent'], color=COLORS[name], linewidth=0.8, label=name, alpha=0.8)
    ax.set_ylabel('Moc grzania [%]')
    ax.set_title('Sterowanie mocą grzania w czasie')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    ax = axes[2]
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['Energia_kWh_skumulowana'], color=COLORS[name], linewidth=1.5, label=name)
    ax.set_ylabel('Energia skumulowana [kWh]')
    ax.set_title('Zużycie energii w czasie (skumulowane)')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    ax = axes[3]
    for name, df_hist in results.items():
        ax.plot(df_hist['Timestamp'], df_hist['Snieg_mm'], color=COLORS[name], linewidth=1.0, label=f'Śnieg {name}')
    ax.set_ylabel('Grubość śniegu [mm]')
    ax.set_xlabel('Czas')
    ax.set_title('Zaleganie śniegu na szynie dla poszczególnych algorytmów\n(algorytm_z_normy = górny wyznacznik dopuszczalnej ilości)')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, linestyle=':', alpha=0.5)

    plt.tight_layout()
    fig_path1 = os.path.join(FOLDER_WYNIKOW, "porownanie_przebiegi.png")
    plt.savefig(fig_path1, dpi=110)
    plt.close(fig)
    print(f"Zapisano wykres: {fig_path1}")

    # --- Podsumowanie słupkowe: energia i przełączenia ---
    fig2, (bx1, bx2) = plt.subplots(1, 2, figsize=(14, 5))
    names = [s['name'] for s in stats_list]
    energie = [s['energia_kwh'] for s in stats_list]
    przelaczenia = [s['przelaczenia'] for s in stats_list]
    bar_colors = [COLORS[n] for n in names]

    bx1.bar(names, energie, color=bar_colors)
    bx1.set_ylabel('Zużyta energia [kWh]')
    bx1.set_title('Całkowite zużycie energii')
    bx1.tick_params(axis='x', rotation=20)
    bx1.grid(True, axis='y', linestyle=':', alpha=0.5)

    bx2.bar(names, przelaczenia, color=bar_colors)
    bx2.set_ylabel('Liczba przełączeń grzania (0%<->reszta)')
    bx2.set_title('Całkowita liczba przełączeń')
    bx2.tick_params(axis='x', rotation=20)
    bx2.grid(True, axis='y', linestyle=':', alpha=0.5)

    plt.tight_layout()
    fig_path2 = os.path.join(FOLDER_WYNIKOW, "porownanie_podsumowanie.png")
    plt.savefig(fig_path2, dpi=110)
    plt.close(fig2)
    print(f"Zapisano wykres: {fig_path2}")

    print("\nGotowe. Pliki CSV i PNG znajdują się w folderze wyniki/.")


if __name__ == '__main__':
    main()
