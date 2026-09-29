# notatki/rysunki/generuj_wizualizacje_modelu.py
#
# Generuje trzy rysunki modelu (PNG obok tego skryptu) opisane w notatki/model_do_wizualizacji.md:
#   01_schemat_obiektu.png            - przepływ sygnałów obiektu fizycznego (E1, P1-P10)
#   02_architektura_kontrolera.png    - rdzeń kontrolera, funkcja ryzyka, regulatory
#   03_odpowiedz_skokowa_hrt_crt.png  - odpowiedź HRT vs CRT na pełną moc od zera
#   04_kanal_sloneczny.png            - kanał nasłonecznienia: wejście dobowe i nagrzewanie szyn
# Stałe (K, T1, Tz) to te same liczby co w symulacja_fizyczna.py (stan po dodaniu słońca, 2026-09-28).
#
# Uruchomienie:  python notatki/rysunki/generuj_wizualizacje_modelu.py

import os

import matplotlib
import matplotlib.dates  # noqa: F401
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Arc, Circle, FancyBboxPatch, Rectangle

KATALOG = os.path.dirname(os.path.abspath(__file__))

# --- Paleta (reference palette: slot 1 = niebieski, slot 2 = pomarańczowy) i atrament ---
HRT = '#2a78d6'
CRT = '#eb6834'
POWIERZCHNIA = '#fcfcfb'
INK = '#0b0b0b'
INK2 = '#52514e'
MUTED = '#898781'
SIATKA = '#e1e0d9'
SZARY = '#6b6a66'   # strzałki sygnałów
BIALY = '#ffffff'

plt.rcParams['font.family'] = 'DejaVu Sans'

# Stałe modelu (symulacja_fizyczna.py)
K_W, T1_W, TZ_W = 0.9866, 5145.5, 1321.4
K_H, T1_H, TZ_H = 47.17, 2462.4, 203.9
K_HC, T1_HC = 4.717, 14400.0
K_S_CRT, T1_S_CRT = 12.773, 5650.6
K_S_HRT, T1_S_HRT = 9.629, 35062.2
KOL_SLONCE = '#ffd54f'


def _blok(ax, x, y, w, h, tytul, linie=(), akcent=None, przerywany=False, rozmiar=7.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=0.9',
                                fc=BIALY, ec=akcent or INK2, lw=1.9 if akcent else 1.3,
                                ls=(0, (4, 3)) if przerywany else '-', zorder=3))
    ax.text(x + 1.6, y + h - 0.9, tytul, fontsize=rozmiar + 1.0, fontweight='bold', color=INK, va='top', zorder=5)
    for i, linia in enumerate(linie):
        ax.text(x + 1.6, y + h - 3.0 - 1.3 * i, linia, fontsize=rozmiar, color=INK2, va='top', zorder=5)


def _linia(ax, xs, ys, kolor=SZARY, lw=1.6, strzalka=True):
    ax.plot(xs, ys, color=kolor, lw=lw, solid_capstyle='butt', zorder=2)
    if strzalka:
        ax.annotate('', xy=(xs[-1], ys[-1]), xytext=(xs[-2], ys[-2]),
                    arrowprops=dict(arrowstyle='-|>', color=kolor, lw=lw, shrinkA=0, shrinkB=0,
                                    mutation_scale=12), zorder=2)


def _kropka(ax, x, y, kolor=SZARY):
    ax.plot([x], [y], 'o', color=kolor, ms=5, zorder=4)


def _suma(ax, x, y, kolor):
    ax.add_patch(Circle((x, y), 2.6, fc=BIALY, ec=kolor, lw=2.4, zorder=4))
    ax.text(x, y - 0.1, '+', ha='center', va='center', fontsize=14, color=INK, zorder=5)


def _plotno(szer, wys, rozmiar):
    fig = plt.figure(figsize=rozmiar)
    fig.patch.set_facecolor(POWIERZCHNIA)
    ax = fig.add_axes([0.004, 0.004, 0.992, 0.992])
    ax.set_xlim(0, szer)
    ax.set_ylim(0, wys)
    ax.axis('off')
    return fig, ax


def rysunek_schemat():
    fig, ax = _plotno(136, 72, (18.9, 10.0))

    ax.text(1, 70.8, 'Model symulacyjny ogrzewania rozjazdu - wariant CRT', fontsize=16, fontweight='bold', color=INK, va='top')
    ax.text(1, 67.2, 'Obiekt fizyczny: przepływ sygnałów w jednym kroku symulacji (dt = 10 s).', fontsize=9, color=INK2, va='top')
    ax.text(1, 65.6, 'Szyna zimna (CRT) reaguje na grzanie ok. 10x słabiej i 5,8x wolniej niż szyna ogrzewana (HRT). Obie szyny nagrzewa też słońce (P11).',
            fontsize=9, color=INK2, va='top')

    # --- Tor pogody (góra) ---
    _blok(ax, 1, 48, 19, 10, 'E1  Dane pogodowe (CSV)', ['AT, punkt rosy, wiatr, opad,', 'nasłonecznienie [s/h]', '44 lokalizacje (lat/lon)'])
    _blok(ax, 24, 48, 25, 10, 'P1  G_W: pogoda -> szyna',
          ['K = 0,987    T1 = 86 min', 'Tz = 22 min    L = 0', 'ZMIERZONA (Wrocław), z P11'])
    _linia(ax, [20, 24], [53, 53])
    _linia(ax, [49, 104, 104], [53, 53, 42.3])
    ax.text(58, 54.1, 'W = składowa pogodowa (wspólna dla HRT i CRT)', fontsize=8.2, color=INK2, va='bottom')
    _kropka(ax, 99, 53)
    _linia(ax, [99, 99, 104, 104], [53, 31.6, 31.6, 27.2])

    # --- Tor grzania (dół -> prawo) ---
    _blok(ax, 1, 4, 14, 13, 'KONTROLER', ['algorytm z rejestru', 'moc żądana 0-100%'], akcent=INK2)
    _blok(ax, 19, 4, 17, 13, 'P9  Bezpiecznik z normy', ['moc = max(moc, moc', 'normy) gdy zalega śnieg'])
    _blok(ax, 40, 4, 17, 13, 'P8  Zabezp. 45 °C', ['HRT >= 45 °C -> moc 0', 'zwolnienie < 40 °C *', 'tylko algorytmy nie-fuzzy'])
    _blok(ax, 61, 4, 12, 13, 'P2  Opóźnienie', ['L = 0', '(brak w modelu)'])
    _linia(ax, [15, 19], [10.5, 10.5])
    _linia(ax, [36, 40], [10.5, 10.5])
    _linia(ax, [57, 61], [10.5, 10.5])
    _linia(ax, [73, 76, 76], [10.5, 10.5, 39.5], strzalka=False)
    _kropka(ax, 76, 24.5)
    ax.text(77, 12, 'u = moc po zabezpieczeniach', fontsize=8.2, color=INK2, va='bottom')

    _blok(ax, 79, 34, 18, 11, 'P3  G_H: moc -> HRT',
          ['K = 47,2 °C   T1 = 41 min', 'Tz = 3,4 min    L = 0', 'ZMIERZONA'], akcent=HRT)
    _blok(ax, 79, 19, 18, 11, 'P4  G_HC: moc -> CRT',
          ['K = 4,72 °C   T1 = 4 h', 'bez członu różniczkującego', 'ZAŁOŻONA (nie pomiar)'], akcent=CRT, przerywany=True)
    _linia(ax, [76, 79], [39.5, 39.5])
    _linia(ax, [76, 79], [24.5, 24.5])

    # --- P11: kanał nasłonecznienia (wejście: ułamek słońca x sin(wysokość słońca); wyjścia S_h, S_c do sum) ---
    _blok(ax, 50, 36, 25, 12, 'P11  G_S: słońce -> szyna',
          ['wejście: ułamek słońca x', 'sin(wysokość słońca), 0..1', 'HRT: K=9,6 °C, T=9,7 h', 'CRT: K=12,8 °C, T=94 min',
           'zimą w symulacji: wkład x 0,5*'],
          akcent=KOL_SLONCE)
    _linia(ax, [10, 10, 50], [48, 41.5, 41.5], kolor=KOL_SLONCE, lw=1.8)
    ax.text(11.2, 42.3, 'sekundy słońca -> średni ułamek godzinowy, interpolacja', fontsize=7.4, color=INK2, va='bottom')
    _linia(ax, [99.3, 102.5], [45.6, 41.9], kolor=KOL_SLONCE, lw=1.8)
    ax.text(98.7, 46.4, 'S_h z P11', fontsize=7.6, color=INK, ha='right', va='bottom', fontweight='bold')
    _linia(ax, [100.2, 102.8], [30.2, 27.1], kolor=KOL_SLONCE, lw=1.8)
    ax.text(99.8, 31.0, 'S_c z P11', fontsize=7.6, color=INK, ha='right', va='bottom', fontweight='bold')

    # --- Sumatory ---
    _suma(ax, 104, 39.5, HRT)
    _suma(ax, 104, 24.5, CRT)
    # H do sumy HRT z 'przeskokiem' nad odgałęzieniem W (x=99)
    r = 0.9
    ax.plot([97, 99 - r], [39.5, 39.5], color=SZARY, lw=1.6, zorder=2, solid_capstyle='butt')
    _linia(ax, [99 + r, 101.4], [39.5, 39.5])
    ax.add_patch(Arc((99, 39.5), 2 * r, 2 * r, theta1=0, theta2=180, ec=SZARY, lw=1.6, zorder=2))
    _linia(ax, [97, 101.4], [24.5, 24.5])
    ax.text(104, 35.6, 'HRT = W + S_h + H', fontsize=8.4, color=INK, ha='center', va='top', fontweight='bold')
    ax.text(104, 21.1, 'CRT = W + S_c + HC', fontsize=8.4, color=INK, ha='center', va='top', fontweight='bold')

    # --- Wyjścia: HRT, CRT -> blok czujników; HRT -> model śniegu ---
    _blok(ax, 111, 18, 24, 27, 'P7  Blok czujników',
          ['CRT prawdziwe:', '   W + HC (poprz. krok)', 'HRT (poprz. krok), AT, RH', 'opad, intensywność śniegu',
           'punkt rosy, wiatr', '', 'NIE widzi grubości śniegu -', 'liczy własny estymator'])
    _linia(ax, [106.6, 111], [39.5, 39.5], kolor=HRT, lw=2.4)
    _linia(ax, [106.6, 111], [24.5, 24.5], kolor=CRT, lw=2.4)
    ax.text(108.8, 40.4, 'HRT', fontsize=8, color=INK, ha='center', va='bottom', fontweight='bold')
    ax.text(108.8, 25.4, 'CRT', fontsize=8, color=INK, ha='center', va='bottom', fontweight='bold')
    _kropka(ax, 108.6, 39.5, HRT)

    _blok(ax, 111, 55, 24, 12, 'P6  Model śniegu i lodu',
          ['(pochodna SnowClim)', 'wejście: pogoda (E1) + HRT', 'wyjście: śnieg [mm], lód [mm]'])
    _linia(ax, [108.6, 108.6, 111], [39.5, 60, 60], kolor=HRT, lw=2.0)

    _blok(ax, 76, 56, 32, 11, 'P10  Metryki wyniku',
          ['energia, przełączenia, IAE/ISE/ITAE,', 'kara bezpieczeństwa (HRT + CRT),', 'czas powyżej 45 °C'])
    _linia(ax, [111, 108], [65, 65])

    # --- Sprzężenie zwrotne: P7 -> kontroler ---
    _linia(ax, [123, 123, 8, 8], [18, 1.6, 1.6, 4])
    ax.text(66, 2.2, 'odczyty czujników -> kontroler (pętla sprzężenia zwrotnego)', fontsize=8.2, color=INK2, va='bottom', ha='center')

    # --- Legenda ---
    lx, ly = 2, 39.6
    ax.text(lx, ly, 'Legenda', fontsize=9.5, fontweight='bold', color=INK, va='top')
    ax.add_patch(FancyBboxPatch((lx, ly - 4.6), 4.2, 2.1, boxstyle='round,pad=0,rounding_size=0.4', fc=BIALY, ec=INK2, lw=1.4))
    ax.text(lx + 5.4, ly - 3.55, 'ciągła ramka: zmierzone / zdefiniowane', fontsize=8.2, color=INK2, va='center')
    ax.add_patch(FancyBboxPatch((lx, ly - 8.2), 4.2, 2.1, boxstyle='round,pad=0,rounding_size=0.4', fc=BIALY, ec=CRT, lw=1.8,
                                ls=(0, (4, 3))))
    ax.text(lx + 5.4, ly - 7.15, 'przerywana ramka: ZAŁOŻENIE (bez pomiaru)', fontsize=8.2, color=INK2, va='center')
    ax.plot([lx, lx + 4.2], [ly - 10.7, ly - 10.7], color=HRT, lw=2.6)
    ax.text(lx + 5.4, ly - 10.7, 'HRT - szyna ogrzewana', fontsize=8.2, color=INK2, va='center')
    ax.plot([lx, lx + 4.2], [ly - 13.4, ly - 13.4], color=CRT, lw=2.6)
    ax.text(lx + 5.4, ly - 13.4, 'CRT - szyna zimna (nieogrzewana)', fontsize=8.2, color=INK2, va='center')
    ax.plot([lx, lx + 4.2], [ly - 16.1, ly - 16.1], color=SZARY, lw=1.6)
    ax.text(lx + 5.4, ly - 16.1, 'sygnał / przepływ danych', fontsize=8.2, color=INK2, va='center')
    ax.plot([lx, lx + 4.2], [ly - 18.8, ly - 18.8], color=KOL_SLONCE, lw=2.6)
    ax.text(lx + 5.4, ly - 18.8, 'nasłonecznienie (kanał P11)', fontsize=8.2, color=INK2, va='center')
    ax.text(lx, ly - 21.4, '* założenia: histereza zwolnienia 5 °C; zimowe tłumienie słońca 0,5 (śnieg odbija). Limit 45 °C to wymóg sprzętu.',
            fontsize=7.6, color=MUTED, va='center')

    fig.savefig(os.path.join(KATALOG, '01_schemat_obiektu.png'), dpi=150, facecolor=POWIERZCHNIA)
    plt.close(fig)


def rysunek_kontroler():
    fig, ax = _plotno(136, 72, (18.9, 10.0))
    ax.text(1, 70.8, 'Architektura kontrolera', fontsize=16, fontweight='bold', color=INK, va='top')
    ax.text(1, 67.2, 'Każdy algorytm widzi tylko odczyty czujników i sam buduje pamięć, prognozy i estymatory; '
            'na końcu regulator zamienia cel na moc.', fontsize=9, color=INK2, va='top')

    _blok(ax, 1, 56, 134, 8, 'P7  Wiersz czujników (co krok)',
          ['CRT (prawdziwe, z wkładem grzania), HRT, AT, wilgotność, opad, intensywność śniegu, punkt rosy, wiatr'])

    kafle = [
        ('K1  Pamięć czujników', ['średnie w binach 15 min', 'bufor 36 binów (9 h)'], None, False),
        ('K2  Prognoza AT', ['Kalman: poziom + trend', '2 h = 8 kroków x 15 min'], None, False),
        ('K3  Prognoza CRT', ['Kalman fizyczny (G_W)', 'Q = R = 0,01', 'RMSE ok. 1,8 °C'], CRT, False),
        ('K4  Autotest', ['skok mocy 0 -> 100%', 'dopasowanie SOPDT', 'K, T1, T2, L (start)'], HRT, False),
        ('K5  Bliźniak HRT', ['SOPDT z autotestu', 'zanikanie ciepła', 'po wyłączeniu'], HRT, False),
        ('K6  Bliźniak CRT', ['G_HC: K 4,81, T1 4 h', 'ZAŁOŻONY (nie pomiar)'], CRT, True),
        ('K7  Estymator śniegu', ['przyrost: opad śniegu', 'ubytek: 0,001 mm/s/°C', '  x max(CRT, 0)'], CRT, False),
        ('K8  Prognoza opadu', ['intensywność 0-3', 'horyzont 2 h'], None, False),
    ]
    for i, (t, l, a, p) in enumerate(kafle):
        x = 1 + 16.9 * i
        _blok(ax, x, 38, 15.4, 13.2, t, l, akcent=a, przerywany=p, rozmiar=7.3)
        _linia(ax, [x + 7.7, x + 7.7], [56, 51.2])
        _linia(ax, [x + 7.7, x + 7.7], [38, 34.2])

    _blok(ax, 1, 14, 134, 20, 'Funkcja ryzyka  ->  temperatura zadana, czy grzać, powód (wspólna dla rodziny risk_function*, MPC, fuzzy_ryzyko*)',
          ['Priorytety (pierwszy spełniony wygrywa):',
           '1) marznący deszcz -> grzej bezwarunkowo (cel 3 °C)',
           '2) opad śniegu lub zalegający śnieg > 5 mm -> grzej (cel 2 °C + kara za zaleganie); chyba że prognoza CRT pokazuje ocieplenie za ~30 min przy cienkiej pokrywie',
           '2b) front opadowy za ~30 min i AT lub CRT <= 2 °C -> grzanie wyprzedzające',
           '3) CRT <= -8 °C albo prognoza 2 h <= -12 °C -> ochrona przed spadkiem poniżej -10 °C (cel -5 °C)',
           '4) suchy mróz: AT <= -5 °C -> cel -5 °C          5) w innym razie: brak zagrożenia, nie grzej'], rozmiar=8.0)

    _blok(ax, 1, 2, 116, 8.5, 'Regulator (jeden na algorytm)',
          ['histereza binarna  |  PI ciągły (SIMC)  |  kaskada 2xPI  |  PI binarny, histereza 2 °C  |  ADRC / LADRC / NADRC  |  '
           'MPC (8 x 15 min)  |  fuzzy Sugeno  |  uczenie z kar  |  automat z normy'], rozmiar=7.6)
    _linia(ax, [58, 58], [14, 10.5])
    _blok(ax, 120, 2, 15, 8.5, 'Moc 0-100%', ['-> P9 (obiekt)'])
    _linia(ax, [117, 120], [6.2, 6.2])

    fig.savefig(os.path.join(KATALOG, '02_architektura_kontrolera.png'), dpi=150, facecolor=POWIERZCHNIA)
    plt.close(fig)


def rysunek_odpowiedz():
    t_h = np.linspace(0, 12, 1200)
    t = t_h * 3600.0
    y_hrt = K_H * (1 - (1 - TZ_H / T1_H) * np.exp(-t / T1_H))
    y_crt = K_HC * (1 - np.exp(-t / T1_HC))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8.6), gridspec_kw={'height_ratios': [1.15, 1]})
    fig.patch.set_facecolor(POWIERZCHNIA)
    fig.suptitle('Wkład pełnej mocy grzania (0 -> 100%) w temperaturę szyny', fontsize=15, fontweight='bold',
                 color=INK, x=0.06, ha='left', y=0.985)
    fig.text(0.06, 0.935, 'Bez wpływu pogody i słońca. CRT rośnie do ok. 4,7 °C, HRT do ok. 47 °C; T1: HRT 41 min, CRT 4 h.',
             fontsize=10, color=INK2, ha='left')

    for ax in (a1, a2):
        ax.set_facecolor(POWIERZCHNIA)
        ax.grid(True, color=SIATKA, lw=0.8)
        ax.set_axisbelow(True)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        for s in ('left', 'bottom'):
            ax.spines[s].set_color('#c3c2b7')
        ax.tick_params(colors=INK2, labelsize=9)
        ax.set_xlim(0, 12)

    # Panel 1: obie serie na JEDNEJ osi °C (widać skalę różnicy)
    a1.plot(t_h, y_hrt, color=HRT, lw=2.4, label='HRT (szyna ogrzewana)')
    a1.plot(t_h, y_crt, color=CRT, lw=2.4, label='CRT (szyna zimna)')
    a1.set_ylim(0, 52)
    a1.set_ylabel('wkład grzania [°C]', color=INK2, fontsize=10)
    a1.set_title('Ta sama oś: CRT wygląda na prawie płaskie', loc='left', fontsize=10.5, color=INK, pad=8)
    h32, h4 = K_H * (1 - (1 - TZ_H / T1_H) * np.exp(-1920 / T1_H)), K_H * (1 - (1 - TZ_H / T1_H) * np.exp(-14400 / T1_H))
    c32, c4 = K_HC * (1 - np.exp(-1920 / T1_HC)), K_HC * (1 - np.exp(-14400 / T1_HC))
    a1.text(6.2, 44.5, f'HRT: {h32:.0f} °C po 32 min, {h4:.0f} °C po 4 h', color=INK, fontsize=9.5)
    a1.text(6.2, 9.5, f'CRT: {c32:.1f} °C po 32 min, {c4:.1f} °C po 4 h', color=INK, fontsize=9.5)
    a1.legend(loc='center right', frameon=False, fontsize=9.5, labelcolor=INK)

    # Panel 2: przybliżenie CRT na własnej osi (nie oś podwójna - osobny panel)
    a2.plot(t_h, y_crt, color=CRT, lw=2.4, label='CRT (szyna zimna)')
    a2.axhline(K_HC, color=MUTED, lw=1.0, ls=(0, (4, 3)))
    a2.text(0.15, K_HC + 0.08, 'stan ustalony 4,72 °C (ZAŁOŻENIE - nie pomiar)', color=INK2, fontsize=9)
    a2.axvline(T1_HC / 3600.0, color=MUTED, lw=1.0, ls=(0, (4, 3)))
    a2.plot([T1_HC / 3600.0], [K_HC * (1 - np.exp(-1))], 'o', color=CRT, ms=8, mec=POWIERZCHNIA, mew=2)
    a2.text(T1_HC / 3600.0 + 0.15, 1.2, 'T1 = 4 h: 63% (3,04 °C)', color=INK, fontsize=9.5)
    a2.set_ylim(0, 5.4)
    a2.set_ylabel('wkład grzania [°C]', color=INK2, fontsize=10)
    a2.set_xlabel('czas od włączenia pełnej mocy [h]', color=INK2, fontsize=10)
    a2.set_title('Przybliżenie: tylko CRT, własna oś', loc='left', fontsize=10.5, color=INK, pad=8)

    fig.subplots_adjust(left=0.08, right=0.97, top=0.88, bottom=0.08, hspace=0.36)
    fig.savefig(os.path.join(KATALOG, '03_odpowiedz_skokowa_hrt_crt.png'), dpi=150, facecolor=POWIERZCHNIA)
    plt.close(fig)


def rysunek_slonce():
    """Kanał nasłonecznienia: (a) wejście dobowe dla bezchmurnego dnia (Wrocław, 22.04) - ułamek słońca, sinus wysokości,
    ich iloczyn; (b) nagrzewanie CRT i HRT wywołane takim wejściem powtarzanym przez 3 doby."""
    sys_path = os.path.normpath(os.path.join(KATALOG, '..', '..'))
    import sys
    sys.path.insert(0, sys_path)
    import wejscie_slonca as ws
    from scipy import signal as sg

    lat, lon, _ = ws.LOKALIZACJE['wroclaw']
    t = pd.date_range('2026-04-21 00:00', periods=3 * 144, freq='10min')          # UTC, 3 doby co 10 min
    sin_el = np.clip(ws.sinus_wysokosci_slonca(t, lat, lon), 0.0, None)
    frakcja = (sin_el > 0).astype(float)                                          # bezchmurnie: pełne słońce od świtu do zmierzchu
    wejscie = frakcja * sin_el

    def filtr(K, T1, x):
        b, a, _ = sg.cont2discrete(([K], [T1, 1.0]), 600.0, method='zoh')
        return sg.lfilter(np.ravel(b), np.ravel(a), x)

    d_crt, d_hrt = filtr(K_S_CRT, T1_S_CRT, wejscie), filtr(K_S_HRT, T1_S_HRT, wejscie)

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8.6), sharex=True, gridspec_kw={'height_ratios': [1, 1.15]})
    fig.patch.set_facecolor(POWIERZCHNIA)
    fig.suptitle('Kanał nasłonecznienia: wejście i nagrzewanie szyn (bezchmurne 3 doby, Wrocław, kwiecień)',
                 fontsize=14, fontweight='bold', color=INK, x=0.06, ha='left', y=0.985)
    fig.text(0.06, 0.94, 'wejście = ułamek słońca x sin(wysokość słońca);  0 = brak słońca (noc / zachmurzenie), 1 = pełne słońce w zenicie',
             fontsize=10, color=INK2, ha='left')
    for ax in (a1, a2):
        ax.set_facecolor(POWIERZCHNIA)
        ax.grid(True, color=SIATKA, lw=0.8)
        ax.set_axisbelow(True)
        for sp in ('top', 'right'):
            ax.spines[sp].set_visible(False)
        for sp in ('left', 'bottom'):
            ax.spines[sp].set_color('#c3c2b7')
        ax.tick_params(colors=INK2, labelsize=9)
    a1.plot(t, frakcja, color=KOL_SLONCE, lw=1.6, ls='--', label='ułamek słońca (bezchmurnie = 1 w ciągu dnia)')
    a1.plot(t, sin_el, color=MUTED, lw=1.4, label='sin(wysokość słońca)')
    a1.plot(t, wejscie, color='#c98500', lw=2.6, label='wejście modelu = iloczyn')
    a1.set_ylim(-0.05, 1.1)
    a1.set_ylabel('wejście [0..1]', color=INK2, fontsize=10)
    a1.legend(loc='upper right', frameon=False, fontsize=9, labelcolor=INK)
    a1.set_title('(a) Wejście słońca', loc='left', fontsize=10.5, color=INK, pad=6)
    a2.plot(t, d_crt, color=CRT, lw=2.4, label=f'CRT: K = {K_S_CRT:.1f} °C, T = {T1_S_CRT / 60:.0f} min')
    a2.plot(t, d_hrt, color=HRT, lw=2.4, label=f'HRT: K = {K_S_HRT:.1f} °C, T = {T1_S_HRT / 3600:.1f} h (wolno, słabo zidentyfikowane)')
    a2.set_ylabel('nagrzewanie od słońca [°C]', color=INK2, fontsize=10)
    a2.legend(loc='upper left', frameon=False, fontsize=9, labelcolor=INK)
    a2.set_title('(b) Wkład słońca w temperaturę szyny (ponad pogodę i grzanie)', loc='left', fontsize=10.5, color=INK, pad=6)
    a2.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d.%m\n%H:%M'))
    fig.text(0.06, 0.012, 'Parametry dopasowane do wiosennych danych z Wrocławia (jedna wiosna); w symulacji zimowej wkład słońca jest mnożony przez 0,5 (założenie: śnieg odbija promieniowanie; ten wykres pokazuje model bez tłumienia).',
             fontsize=8, color=MUTED, ha='left')
    fig.subplots_adjust(left=0.08, right=0.97, top=0.88, bottom=0.10, hspace=0.30)
    fig.savefig(os.path.join(KATALOG, '04_kanal_sloneczny.png'), dpi=150, facecolor=POWIERZCHNIA)
    plt.close(fig)


if __name__ == '__main__':
    rysunek_schemat()
    rysunek_kontroler()
    rysunek_odpowiedz()
    rysunek_slonce()
    print('Zapisano rysunki w', KATALOG)
