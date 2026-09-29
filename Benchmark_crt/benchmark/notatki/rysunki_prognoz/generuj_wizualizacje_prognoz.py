# notatki/rysunki_prognoz/generuj_wizualizacje_prognoz.py
#
# Generuje dwa rysunki referencyjne opisane w notatki/rysunki_prognoz/AGENTS.md, na realnych danych
# pogodowych (Kraków, epizod śniegu 21-24.11.2025) - BEZ uruchamiania pełnej symulacji fizyki/sterowania
# (tylko wczytanie pogody + bezpośrednie odpytanie silników prognozy), więc jest to szybkie i lekkie:
#   05_prognoza_temperatury.png  - wachlarze prognozy Kalmana (AT: poziom+trend; CRT: fizyka+Kalman)
#                                  nałożone na prawdziwy przebieg, w kilku chwilach czasu
#   06_prognoza_opadow.png       - epizod opadu: rzeczywisty opad/temperatura + klasyfikacja intensywności
#                                  (0-3) prognozowana z wyprzedzeniem, zestawiona z "prawdą" (tymi samymi
#                                  progami co przewidywanie_opadow.algorytm_opadu używa do walidacji)
#
# "CRT" tutaj to WYŁĄCZNIE składowa pogodowa (fiz.wylicz_skladowa_pogodowa) - bez wkładu grzania (na tym
# oknie grzanie i tak nie jest symulowane) - w pełni wystarczające do zilustrowania silnika prognozy.
#
# Uruchomienie: python notatki/rysunki_prognoz/generuj_wizualizacje_prognoz.py

import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

KATALOG = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.normpath(os.path.join(KATALOG, '..', '..'))
sys.path.insert(0, BENCH)
sys.path.insert(0, os.path.join(BENCH, 'Algorytmy'))

import symulacja_fizyczna as fiz
from rdzen_kontrolera import KontrolerBazowy, RowData, STEP_SECONDS
from przewidywanie_opadow import przewidywanie_opadow as PrzewidywanieOpadow

# --- Paleta zgodna z notatki/rysunki/generuj_wizualizacje_modelu.py ---
HRT = '#2a78d6'      # tu: AT (powietrze) - ten sam slot co HRT w schemacie obiektu
CRT = '#eb6834'
POWIERZCHNIA = '#fcfcfb'
INK = '#0b0b0b'
INK2 = '#52514e'
MUTED = '#898781'
SIATKA = '#e1e0d9'
KOL_OPAD = '#c98500'
KOL_PROGNOZA = '#6b6a66'

LOKALIZACJA = 'krakow_60min_2025'
OKNO = (pd.Timestamp('2025-11-19 00:00'), pd.Timestamp('2025-11-24 00:00'))
DT = 300.0  # 5 min - wystarczające dla prognozy 15-minutowej, dużo taniej niż 10s fizyki


def wczytaj_okno():
    sciezka = os.path.join(BENCH, 'Pogoda_pomiary_15_minut', f'{LOKALIZACJA}.csv')
    df = fiz.wczytaj_pogode_1s(sciezka, zakres_dat=OKNO, dt=DT)
    A_wd, B_wd, C_wd, D_wd, _, _, _, _, _ = fiz.przygotuj_modele_stanowe(DT)
    crt = fiz.wylicz_skladowa_pogodowa(df['temperatura_powietrza_C'].to_numpy(), A_wd, B_wd, C_wd, D_wd, DT)
    df['crt'] = crt
    return df


def zbierz_prognozy(df, chwile_co_h=6):
    """Przepuszcza KontrolerBazowy przez cały wiersz danych, zbierając w wybranych chwilach czasu
    8-krokowe wachlarze prognozy AT (Kalman poziom+trend) i CRT (Kalman+fizyka), oraz prognozę opadu."""
    k = KontrolerBazowy()
    k._dt_sterowania = DT
    forecaster = PrzewidywanieOpadow(persistence_steps=1)

    krok_probek = int(round(chwile_co_h * 3600.0 / DT))
    wyniki = []
    for i, row in df.reset_index(drop=True).iterrows():
        reading = RowData(timestamp=row['Timestamp'], crt_temp=float(row['crt']),
                          hrt_temp=float(row['crt']), at_temp=float(row['temperatura_powietrza_C']))
        k._append_sensor_history(reading)
        # wymuszamy odswiezenie cache (inaczej co 300s i tak by sie odswiezylo - tu i tak dt=300s)
        k._forecast_cache_time_at = None
        k._forecast_cache_time_crt = None

        if i > 0 and i % krok_probek == 0:
            at_fore = k.temperature_prediction()
            crt_fore = k.crt_transmittance_prediction()
            future_at = at_fore if at_fore else [row['temperatura_powietrza_C']] * 8
            # opad_mm z wczytaj_pogode_1s to mm/s - przeskalowane do "mm w ostatnich 15 min" (STEP_SECONDS),
            # DOKŁADNIE jak w funkcja_ryzyka_wspolne._prognoza_intensywnosci_opadu (patrz poprawka 2026-09-29
            # w tamtym pliku - bez tego bramka "czy pada" w przewidywanie_opadow.py nigdy się nie otwiera).
            opad_fore = forecaster.predict_winter_precipitation(
                [float(row['opad_mm']) * STEP_SECONDS], future_at, float(row['punkt_rosy_C']), float(row.get('wiatr_m_s', 3.0)))
            wyniki.append({'t': row['Timestamp'], 'at_fore': list(at_fore), 'crt_fore': list(crt_fore),
                           'opad_fore': list(opad_fore)})
    return wyniki


def prawda_opadu(df):
    """Ground truth 0-3 - te same progi co przewidywanie_opadow.algorytm_opadu (sekcja walidacyjna), na
    opad_mm PRZESKALOWANYM x STEP_SECONDS (ta funkcja dostaje mm/s z wczytaj_pogode_1s, progi 0,35/1,0
    są kalibrowane na surowe mm z pliku - ta sama poprawka skali co w forecaster, patrz zbierz_prognozy)."""
    poziomy = np.zeros(len(df), dtype=int)
    opad = df['opad_mm'].to_numpy() * STEP_SECONDS
    at = df['temperatura_powietrza_C'].to_numpy()
    wiatr = df['wiatr_m_s'].to_numpy() if 'wiatr_m_s' in df.columns else np.full(len(df), 3.0)
    for i in range(len(df)):
        if opad[i] > 0.0001 and at[i] <= 1.0:
            if opad[i] <= 0.35:
                poziomy[i] = 1
            elif opad[i] <= 1.0:
                poziomy[i] = 2 if wiatr[i] < 6.0 else 3
            else:
                poziomy[i] = 3
    return poziomy


def _os(ax):
    ax.set_facecolor(POWIERZCHNIA)
    ax.grid(True, color=SIATKA, lw=0.8)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#c3c2b7')
    ax.tick_params(colors=INK2, labelsize=9)


def rysunek_temperatury(df, wachlarze):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True, gridspec_kw={'height_ratios': [1, 1]})
    fig.patch.set_facecolor(POWIERZCHNIA)
    fig.suptitle('Prognoza temperatury: wachlarze Kalmana na realnym oknie (Kraków, 19-24.11.2025)',
                 fontsize=14, fontweight='bold', color=INK, x=0.06, ha='left', y=0.985)
    fig.text(0.06, 0.945, 'Linia ciągła = pomiar. Przerywane "wachlarze" = prognoza 8x15 min (2h) wystawiona co 6 h.',
             fontsize=10, color=INK2, ha='left')
    for ax in (a1, a2):
        _os(ax)

    a1.plot(df['Timestamp'], df['temperatura_powietrza_C'], color=HRT, lw=1.8, label='AT (pomiar)')
    a2.plot(df['Timestamp'], df['crt'], color=CRT, lw=1.8, label='CRT - składowa pogodowa (pomiar)')

    for i, w in enumerate(wachlarze):
        t_fore = [w['t'] + pd.Timedelta(minutes=15 * (k + 1)) for k in range(8)]
        etykieta_at = 'prognoza AT (Kalman poziom+trend)' if i == 0 else None
        etykieta_crt = 'prognoza CRT (Kalman + fizyka)' if i == 0 else None
        a1.plot([w['t']] + t_fore, [df.loc[df['Timestamp'] == w['t'], 'temperatura_powietrza_C'].iloc[0]] + w['at_fore'],
                color=KOL_PROGNOZA, lw=1.3, ls='--', marker='o', ms=3, alpha=0.85, label=etykieta_at)
        a2.plot([w['t']] + t_fore, [df.loc[df['Timestamp'] == w['t'], 'crt'].iloc[0]] + w['crt_fore'],
                color=KOL_PROGNOZA, lw=1.3, ls='--', marker='o', ms=3, alpha=0.85, label=etykieta_crt)

    a1.set_ylabel('AT [°C]', color=INK2, fontsize=10)
    a2.set_ylabel('CRT [°C]', color=INK2, fontsize=10)
    a1.legend(loc='upper right', frameon=False, fontsize=9, labelcolor=INK)
    a2.legend(loc='upper right', frameon=False, fontsize=9, labelcolor=INK)
    a1.set_title('(a) Prognoza AT - generyczny Kalman poziom+trend', loc='left', fontsize=10.5, color=INK, pad=6)
    a2.set_title('(b) Prognoza CRT - Kalman z modelem procesu = fizyka (RMSE 2h zmierzone: 1,77°C)',
                 loc='left', fontsize=10.5, color=INK, pad=6)
    a2.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m\n%H:%M'))
    fig.text(0.06, 0.012, 'Dane: Kraków, epizod z realnymi opadami. "CRT" = wyłącznie składowa pogodowa (bez wkładu grzania - nieaktywnego w tym oknie).',
             fontsize=8, color=MUTED, ha='left')
    fig.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.08, hspace=0.28)
    fig.savefig(os.path.join(KATALOG, '05_prognoza_temperatury.png'), dpi=150, facecolor=POWIERZCHNIA)
    plt.close(fig)


def rysunek_opadu(df, wachlarze, prawda):
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(13, 10), sharex=True,
                                     gridspec_kw={'height_ratios': [1, 0.7, 0.9]})
    fig.patch.set_facecolor(POWIERZCHNIA)
    fig.suptitle('Prognoza opadu: klasyfikacja intensywności 0-3 na realnym epizodzie (Kraków)',
                 fontsize=14, fontweight='bold', color=INK, x=0.06, ha='left', y=0.985)
    fig.text(0.06, 0.945, 'Zmierzona globalnie (44 lokalizacje, oryginalny silnik): 80,1% skuteczność osłony, 81,3% trafność alarmu.',
             fontsize=10, color=INK2, ha='left')
    for ax in (a1, a2, a3):
        _os(ax)

    opad_15min = df['opad_mm'].to_numpy() * STEP_SECONDS  # z mm/s (loader) na "mm w ostatnich 15 min" - ta sama skala co próg 0,02 w przewidywanie_opadow.py
    a1.fill_between(df['Timestamp'], opad_15min, color=KOL_OPAD, alpha=0.35)
    a1.plot(df['Timestamp'], opad_15min, color=KOL_OPAD, lw=1.2)
    a1.set_ylabel('opad [mm/15min]', color=INK2, fontsize=10)
    a1.set_title('(a) Rzeczywisty opad', loc='left', fontsize=10.5, color=INK, pad=6)

    a2.plot(df['Timestamp'], df['temperatura_powietrza_C'], color=HRT, lw=1.4, label='AT')
    a2.axhline(-0.5, color=MUTED, lw=0.9, ls=':')
    a2.text(df['Timestamp'].iloc[2], -0.5, ' próg -0,5°C (poziom 1)', color=MUTED, fontsize=7.5, va='bottom')
    a2.set_ylabel('AT [°C]', color=INK2, fontsize=10)
    a2.set_title('(b) Temperatura powietrza (wejście klasyfikatora)', loc='left', fontsize=10.5, color=INK, pad=6)

    a3.step(df['Timestamp'], prawda, color=INK, lw=1.6, where='post', label='"prawda" (z pomiaru opadu)')
    for i, w in enumerate(wachlarze):
        t_fore = [w['t'] + pd.Timedelta(minutes=15 * (k + 1)) for k in range(8)]
        etykieta = 'prognoza (8x15 min, wystawiana co 6h)' if i == 0 else None
        a3.step([w['t']] + t_fore, [prawda[df['Timestamp'].searchsorted(w['t'])]] + w['opad_fore'],
               color=KOL_PROGNOZA, lw=1.3, ls='--', marker='o', ms=3, alpha=0.85, where='post', label=etykieta)
    a3.set_yticks([0, 1, 2, 3])
    a3.set_ylim(-0.3, 3.3)
    a3.set_ylabel('intensywność [0-3]', color=INK2, fontsize=10)
    a3.legend(loc='upper right', frameon=False, fontsize=9, labelcolor=INK)
    a3.set_title('(c) Klasyfikacja intensywności: prawda vs prognoza z wyprzedzeniem', loc='left', fontsize=10.5, color=INK, pad=6)
    a3.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m\n%H:%M'))
    fig.text(0.06, 0.012, 'Prognoza jest zerowa, dopóki w niedawnej historii nie wystąpił już realny opad (patrz AGENTS.md, sekcja 2.1) - to widać jako płaskie zera na początku okna.',
             fontsize=8, color=MUTED, ha='left')
    fig.subplots_adjust(left=0.08, right=0.97, top=0.91, bottom=0.07, hspace=0.32)
    fig.savefig(os.path.join(KATALOG, '06_prognoza_opadow.png'), dpi=150, facecolor=POWIERZCHNIA)
    plt.close(fig)


if __name__ == '__main__':
    df = wczytaj_okno()
    wachlarze = zbierz_prognozy(df, chwile_co_h=6)
    prawda = prawda_opadu(df)
    rysunek_temperatury(df, wachlarze)
    rysunek_opadu(df, wachlarze, prawda)
    print('Zapisano rysunki w', KATALOG)
