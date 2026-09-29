# Identyfikacja/Identyfikacja/wykres_modelu_polaczonego.py
#
# Wykres zgodności MODELU POŁĄCZONEGO z realnymi danymi (Wrocław Popowice, log urządzenia
# "algo (4).log") w STYLU wykresów identyfikacji (ciemny motyw i układ paneli jak w
# Identyfikacja/Porowanie i optymalizacja/porownanie.py oraz wykres_miso w identyfikacja_miso.py).
# Dwa widoki: TYDZIEŃ i pojedyncza DOBA. W każdym: HRT i CRT (pomiar vs model), residua,
# temperatura powietrza AT i sygnał załączenia grzania.
#
# MODEL = dokładnie ten, którego używa symulator Benchmark_crt/benchmark/symulacja_fizyczna.py:
#   HRT_model = G_W(AT) + G_H(u)         G_W: K=1,217 T1=2482,3 s Tz=690,8 s  (zmierzona)
#   CRT_model = G_W(AT) + G_HC(u)        G_H: K=48,07 T1=1901,2 s Tz=90,36 s  (zmierzona)
#                                        G_HC: K=4,807 T1=14400 s             (ZAŁOŻONA)
# u = 1 gdy urządzenie zapisało moc grzania > 0. BEZ żadnego offsetu (jak w symulatorze).
#
# UCZCIWE OGRANICZENIA (patrz notatki_identyfikacja/wyniki.md):
#  - moc grzania jest ZAPISANA tylko w dwóch oknach testu skokowego (22.04 i 30.04, ok. 80 min każde);
#    poza nimi stan grzania jest NIEZNANY - model zakłada tam u = 0 (zaznaczone kreskowaniem);
#  - model NIE zna nasłonecznienia (nie jest wejściem symulatora) - w słoneczne popołudnia pomiar
#    wychodzi ponad model, zwłaszcza HRT (ciemna stal);
#  - okna testu skokowego były użyte do identyfikacji G_H, więc zgodność w nich jest "na próbie uczącej".
#
# Uruchomienie: python wykres_modelu_polaczonego.py   (z tego folderu)
# Wyniki: ../wyniki_identyfikacja/model_polaczony_tydzien.png, model_polaczony_dzien.png

import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from scipy import signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', 'Benchmark_crt', 'benchmark'))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, BENCH)
sys.path.insert(0, os.path.join(BENCH, 'Algorytmy'))

import identyfikacja_miso as im          # parser logu + resampling (te same co w identyfikacji)
import symulacja_fizyczna as fiz         # model = ten sam co w symulatorze

OUTPUT_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'wyniki_identyfikacja')

# Model SPRZED dodania słońca (stałe dawnego symulatora) - baza porównawcza dla wykresów ze słońcem.
from types import SimpleNamespace  # noqa: E402
STARE = SimpleNamespace(K_W=1.217, T1_W=2482.3, TZ_W=690.8, K_H=48.07, T1_H=1901.2, TZ_H=90.36,
                        K_H_CRT=4.807, T1_H_CRT=14400.0)
DT = 10.0            # siatka [s], jak RESAMPLE_S w identyfikacji i krok symulatora
ROZGRZEWKA_S = 24 * 3600   # stan początkowy toru pogodowego: doba stałego AT[0] (bez transientu z zera)

# Okna widoku (tydzień z pierwszym testem skokowym; doba testu skokowego)
TYDZIEN = (pd.Timestamp('2026-04-20 00:00'), pd.Timestamp('2026-04-27 00:00'))
DZIEN = (pd.Timestamp('2026-04-22 00:00'), pd.Timestamp('2026-04-23 00:00'))

# Kolory jak w porownanie.py
KOL = {'meas': '#e8eaf6', 'model': '#00e5ff', 'weather': '#ffb74d', 'heat': '#ef5350',
       'at': '#4fc3f7', 'uheat': '#a5d6a7', 'resid_h': '#ce93d8', 'resid_c': '#80cbc4'}
TLO, TLO_OS, SIATKA, TEKST = '#0a0d14', '#0f1520', '#1e2840', '#7a8aaa'


def zbuduj_dane():
    df, okna = im.wczytaj_log(os.path.join(SCRIPT_DIR, 'algo (4).log'))
    surowe = df.copy()
    siatka = im.resampluj(df[['Timestamp', 'CRT', 'HRT', 'AT']], DT)
    t = siatka['Timestamp'].to_numpy()

    # --- sygnał grzania: TYLKO tam, gdzie urządzenie zapisało moc (okna testu); poza nimi nieznany ---
    p3 = surowe.dropna(subset=['PWRL1']).copy()
    p3_t = p3['Timestamp'].to_numpy().astype('int64')
    p3_on = ((p3['PWRL1'].fillna(0) + p3['PWRL2'].fillna(0)) > 0).to_numpy().astype(float)
    t_num = t.astype('int64')
    znane = np.zeros(len(t), dtype=bool)
    u = np.zeros(len(t))
    for a, b in okna:
        m = (t >= np.datetime64(a)) & (t <= np.datetime64(b))
        znane |= m
    idx = np.clip(np.searchsorted(p3_t, t_num), 1, len(p3_t) - 1)
    blizej_lewy = np.abs(t_num - p3_t[idx - 1]) < np.abs(t_num - p3_t[idx])
    najblizszy = np.where(blizej_lewy, idx - 1, idx)
    u[znane] = p3_on[najblizszy[znane]]

    # --- model (dokładnie jak symulacja_fizyczna.uruchom_kontroler) ---
    # STARY model (bez słońca) z jawnych stałych STARE - symulator ma już nowe stałe (ze słońcem), a ten
    # skrypt/wykres ma pokazywać model sprzed tej zmiany.
    def _ss(num, den):
        return signal.cont2discrete(signal.tf2ss(num, den), DT, method='zoh')[:4]
    A_wd, B_wd, C_wd, D_wd = _ss([STARE.K_W * STARE.TZ_W, STARE.K_W], [STARE.T1_W, 1])
    A_hd, B_hd, C_hd, D_hd = _ss([STARE.K_H * STARE.TZ_H, STARE.K_H], [STARE.T1_H, 1])
    A_chd, B_chd, C_chd, D_chd = _ss([STARE.K_H_CRT], [STARE.T1_H_CRT, 1])
    opoznienie = 0

    at = siatka['AT'].to_numpy()
    n_roz = int(ROZGRZEWKA_S / DT)
    at_z_rozgrzewka = np.concatenate([np.full(n_roz, at[0]), at])
    w = fiz.wylicz_skladowa_pogodowa(at_z_rozgrzewka, A_wd, B_wd, C_wd, D_wd, DT)[n_roz:]

    x_h = np.zeros((A_hd.shape[0], 1))
    x_c = np.zeros((A_chd.shape[0], 1))
    h = np.zeros(len(t))
    hc = np.zeros(len(t))
    for k in range(len(t)):
        uk = u[k - opoznienie] if k >= opoznienie else 0.0
        x_h = A_hd @ x_h + B_hd * uk
        h[k] = float((C_hd @ x_h + D_hd * uk)[0, 0])
        x_c = A_chd @ x_c + B_chd * uk
        hc[k] = float((C_chd @ x_c + D_chd * uk)[0, 0])

    return {'t': t, 'at': at, 'hrt': siatka['HRT'].to_numpy(), 'crt': siatka['CRT'].to_numpy(),
            'w': w, 'h': h, 'hc': hc, 'hrt_model': w + h, 'crt_model': w + hc,
            'u': u, 'znane': znane, 'okna': okna}


def metryki(y, m):
    ok = ~(np.isnan(y) | np.isnan(m))
    y, m = y[ok], m[ok]
    ss_res = float(np.sum((y - m) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {'r2': 1 - ss_res / (ss_tot + 1e-30), 'rmse': float(np.sqrt(ss_res / len(y))),
            'mae': float(np.mean(np.abs(y - m))), 'bias': float(np.mean(m - y))}


def rysuj(d, okno, tytul_widoku, plik, dzien=False):
    t0, t1 = np.datetime64(okno[0]), np.datetime64(okno[1])
    m = (d['t'] >= t0) & (d['t'] < t1)
    t = d['t'][m]
    mh = metryki(d['hrt'][m], d['hrt_model'][m])
    mc = metryki(d['crt'][m], d['crt_model'][m])
    test_w_oknie = [(a, b) for a, b in d['okna'] if a < okno[1] and b > okno[0]]

    fig = plt.figure(figsize=(20, 13))
    fig.patch.set_facecolor(TLO)
    gs = gridspec.GridSpec(5, 1, figure=fig, left=0.055, right=0.975, top=0.925, bottom=0.085, hspace=0.09,
                           height_ratios=[3.3, 3.3, 1.2, 1.3, 0.9])
    ax_h = fig.add_subplot(gs[0])
    ax_c = fig.add_subplot(gs[1], sharex=ax_h)
    ax_r = fig.add_subplot(gs[2], sharex=ax_h)
    ax_a = fig.add_subplot(gs[3], sharex=ax_h)
    ax_g = fig.add_subplot(gs[4], sharex=ax_h)
    for ax in (ax_h, ax_c, ax_r, ax_a, ax_g):
        ax.set_facecolor(TLO_OS)
        ax.tick_params(colors=TEKST, labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(SIATKA)
        ax.grid(True, color=SIATKA, alpha=0.7, lw=0.5)
    for ax in (ax_h, ax_c, ax_r, ax_a):
        plt.setp(ax.get_xticklabels(), visible=False)

    # okna testu skokowego (grzanie zapisane) - delikatne tło na panelach temperatur
    for a, b in test_w_oknie:
        for ax in (ax_h, ax_c, ax_a):
            ax.axvspan(max(a, okno[0]), min(b, okno[1]), color=KOL['uheat'], alpha=0.10, lw=0)

    # --- HRT ---
    ax_h.plot(t, d['hrt'][m], color=KOL['meas'], lw=1.2, alpha=0.85, label='HRT pomiar', zorder=5)
    ax_h.plot(t, d['hrt_model'][m], color=KOL['model'], lw=1.7, alpha=0.95, zorder=6,
              label=f"HRT model łączny (G_W·AT + G_H·u)   R²={mh['r2']:.3f}  RMSE={mh['rmse']:.2f}°C  bias={mh['bias']:+.2f}°C")
    ax_h.plot(t, d['w'][m], color=KOL['weather'], lw=1.0, alpha=0.6, ls='--', label='składnik pogodowy G_W·AT', zorder=4)
    ax_h.plot(t, d['h'][m], color=KOL['heat'], lw=1.0, alpha=0.75, ls='--', label='składnik grzania G_H·u', zorder=4)
    ax_h.set_ylabel('HRT [°C]', color=TEKST, fontsize=9)
    ax_h.legend(loc='upper left', fontsize=8, facecolor='#151c2e', labelcolor='white', framealpha=0.9)

    # --- CRT ---
    ax_c.plot(t, d['crt'][m], color=KOL['meas'], lw=1.2, alpha=0.85, label='CRT pomiar', zorder=5)
    ax_c.plot(t, d['crt_model'][m], color=KOL['model'], lw=1.7, alpha=0.95, zorder=6,
              label=f"CRT model łączny (G_W·AT + G_HC·u)   R²={mc['r2']:.3f}  RMSE={mc['rmse']:.2f}°C  bias={mc['bias']:+.2f}°C")
    ax_c.plot(t, d['hc'][m], color=KOL['heat'], lw=1.0, alpha=0.75, ls='--',
              label='składnik grzania G_HC·u (ZAŁOŻONY - patrz uwagi)', zorder=4)
    ax_c.set_ylabel('CRT [°C]', color=TEKST, fontsize=9)
    ax_c.legend(loc='upper left', fontsize=8, facecolor='#151c2e', labelcolor='white', framealpha=0.9)

    # --- residua (pomiar - model) ---
    ax_r.axhline(0, color='#3a4060', lw=0.8)
    ax_r.plot(t, (d['hrt'] - d['hrt_model'])[m], color=KOL['resid_h'], lw=0.9, alpha=0.9, label='HRT')
    ax_r.plot(t, (d['crt'] - d['crt_model'])[m], color=KOL['resid_c'], lw=0.9, alpha=0.9, label='CRT')
    ax_r.set_ylabel('Residuum\n[°C]', color=TEKST, fontsize=8)
    ax_r.legend(loc='upper left', fontsize=7.5, ncol=2, facecolor='#151c2e', labelcolor='white', framealpha=0.9)

    # --- AT ---
    ax_a.fill_between(t, d['at'][m], color=KOL['at'], alpha=0.30)
    ax_a.plot(t, d['at'][m], color=KOL['at'], lw=0.9)
    ax_a.set_ylabel('AT [°C]', color=TEKST, fontsize=8)

    # --- grzanie: zielone = zapisane ON, kreskowanie = stan nieznany (model zakłada 0) ---
    u, znane = d['u'][m], d['znane'][m]
    ax_g.fill_between(t, 0, 1, where=~znane, facecolor='none', edgecolor='#3a4562', hatch='////', lw=0)
    ax_g.fill_between(t, u, where=znane, color=KOL['uheat'], alpha=0.55, step='post')
    ax_g.step(t, np.where(znane, u, np.nan), color=KOL['uheat'], lw=1.0, where='post')
    ax_g.set_ylim(-0.05, 1.25)
    ax_g.set_yticks([0, 1])
    ax_g.set_ylabel('Grzanie\n[0/1]', color=TEKST, fontsize=8)
    ax_g.text(0.995, 0.5, 'kreskowanie = stan grzania NIEZNANY (brak zapisu mocy), model zakłada 0',
              transform=ax_g.transAxes, ha='right', va='center', fontsize=7.5, color='#8fa0c0')

    # oś czasu
    if dzien:
        ax_g.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax_g.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax_g.set_xlabel('Godzina', color=TEKST, fontsize=8)
    else:
        ax_g.xaxis.set_major_locator(mdates.DayLocator())
        ax_g.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))
        dni_pl = ['pon', 'wt', 'śr', 'czw', 'pt', 'sob', 'niedz']
        ax_g.xaxis.set_major_formatter(plt.FuncFormatter(
            lambda x, _: (lambda dt: f"{dt:%d.%m}\n{dni_pl[dt.weekday()]}")(mdates.num2date(x))))
        ax_g.set_xlabel('Data', color=TEKST, fontsize=8)
    ax_g.set_xlim(t[0], t[-1])
    plt.setp(ax_g.get_xticklabels(), visible=True, color=TEKST)

    fig.suptitle(f'Model połączony vs dane rzeczywiste (Wrocław Popowice) - {tytul_widoku}', color='#c5cfe8',
                 fontsize=13, x=0.055, ha='left', y=0.975)
    fig.text(0.055, 0.945,
             f'STARY model (bez słońca): G_W: K={STARE.K_W}, T1={STARE.T1_W:.0f}s, Tz={STARE.TZ_W:.0f}s   |   G_H: K={STARE.K_H}, T1={STARE.T1_H:.0f}s, '
             f'Tz={STARE.TZ_H:.1f}s   |   G_HC (założona): K={STARE.K_H_CRT:.2f}, T1={STARE.T1_H_CRT:.0f}s   |   bez offsetu',
             color='#8fa0c0', fontsize=8.5, ha='left')
    dodatek = ''
    if test_w_oknie:
        a, b = test_w_oknie[0]
        mt = (d['t'] >= np.datetime64(a)) & (d['t'] <= np.datetime64(b))
        mth = metryki(d['hrt'][mt], d['hrt_model'][mt])
        mtc = metryki(d['crt'][mt], d['crt_model'][mt])
        dodatek = (f"   |   w oknie testu skokowego ({a:%d.%m %H:%M}-{b:%H:%M}, grzanie ON): "
                   f"HRT RMSE={mth['rmse']:.2f}°C, CRT RMSE={mtc['rmse']:.2f}°C")
    fig.text(0.055, 0.035,
             f"HRT: R²={mh['r2']:.3f} RMSE={mh['rmse']:.2f}°C MAE={mh['mae']:.2f}°C   |   CRT: R²={mc['r2']:.3f} "
             f"RMSE={mc['rmse']:.2f}°C MAE={mc['mae']:.2f}°C{dodatek}",
             color='#8fa0c0', fontsize=8.5, ha='left')
    fig.text(0.055, 0.012,
             'Model nie zna nasłonecznienia (słoneczne popołudnia: pomiar ponad modelem). Zaznaczone tło = okno testu skokowego '
             '(grzanie zapisane; z takich okien identyfikowano G_H, więc zgodność w nich jest na próbie uczącej).',
             color='#5d6b8c', fontsize=7.8, ha='left')

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sciezka = os.path.join(OUTPUT_DIR, plik)
    fig.savefig(sciezka, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f'Zapisano: {sciezka}')
    print(f"   {tytul_widoku}: HRT R²={mh['r2']:.3f} RMSE={mh['rmse']:.2f} bias={mh['bias']:+.2f} | "
          f"CRT R²={mc['r2']:.3f} RMSE={mc['rmse']:.2f} bias={mc['bias']:+.2f}")
    return mh, mc


if __name__ == '__main__':
    dane = zbuduj_dane()
    rysuj(dane, TYDZIEN, 'tydzień 20-27.04.2026', 'model_polaczony_tydzien.png')
    rysuj(dane, DZIEN, 'doba 22.04.2026 (test skokowy grzania)', 'model_polaczony_dzien.png', dzien=True)
