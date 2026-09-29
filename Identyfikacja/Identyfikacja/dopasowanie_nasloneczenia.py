# Identyfikacja/Identyfikacja/dopasowanie_nasloneczenia.py
#
# Kanał NASŁONECZNIENIA modelu połączonego (wersja finalna 2026-09-28):
#     HRT = G_W(AT) + G_S,HRT(słońce) + G_H(u)          CRT = G_W(AT) + G_S,CRT(słońce) + G_HC(u)
#   słońce = ułamek_słońca * sin(wysokość słońca)        (0 = brak słońca / noc, 1 = pełne słońce w zenicie)
#   G_S(s) = Ks/(Ts*s+1)    G_W wspólny dla HRT i CRT (K, T1, Tz)    - patrz Benchmark_crt/benchmark/wejscie_slonca.py
#
# Wejście słońca liczone JAK W SYMULATORZE: sekundy słońca -> średni ułamek w przedziale, ustawiony w środku
# przedziału i interpolowany liniowo (przedziały godzinowe, jak w plikach 44 lokalizacji), razem z sinusem
# wysokości słońca ze współrzędnych. Dopasowanie na wejściu GODZINOWYM (jak w symulatorze) i, dla porównania,
# na oryginalnym 15-minutowym (ile daje gęstsza siatka).
# Czas: zegar urządzenia vs UTC - przesunięcie dobrane z danych (kryterium: min. łącznego SSE CRT+HRT).
# Wynik: parametry (CSV + gotowy blok stałych do symulacja_fizyczna.py) i wykresy tydzień/doba.
#
# Uruchomienie: python dopasowanie_nasloneczenia.py   (z tego folderu)

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
from scipy.optimize import least_squares

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import wykres_modelu_polaczonego as wm     # dane, parser logu, stałe modelu (fiz), kolory/styl
sys.path.insert(0, wm.BENCH)
import wejscie_slonca as ws

im, fiz = wm.im, wm.fiz
OUTPUT_DIR = wm.OUTPUT_DIR
DT_FIT = 60.0
TS_MAX = 200000.0
KOL, TLO, TLO_OS, SIATKA, TEKST = wm.KOL, wm.TLO, wm.TLO_OS, wm.SIATKA, wm.TEKST
KOL_SLONCE = '#ffd54f'
LAT, LON, STREFA_POGODY = ws.LOKALIZACJE['wroclaw']


def filtr_tf(K, T1, Tz, x, dt, stan_ustalony=False):
    num = [K * Tz, K] if Tz > 1e-9 else [K]
    b, a, _ = signal.cont2discrete((num, [T1, 1.0]), dt, method='zoh')
    b, a = np.atleast_1d(b).ravel(), np.atleast_1d(a).ravel()
    if stan_ustalony:
        y, _ = signal.lfilter(b, a, x, zi=signal.lfilter_zi(b, a) * x[0])
    else:
        y = signal.lfilter(b, a, x)
    return y


def metr(y, m):
    return wm.metryki(y, m)


def zrodla_slonca():
    """Sekundy słońca z Open-Meteo (Wrocław Popowice, 15 min) w dwóch wersjach: 15-minutowej i uśrednionej do
    godzinowej (suma czterech kroków, znacznik = koniec godziny, jak w plikach /v1/archive)."""
    pog = pd.read_csv(os.path.join(im.SCRIPT_DIR, 'pogoda_wroclaw_popowice_15min.csv'), parse_dates=['Timestamp'])
    t_utc = ws.na_utc(pog['Timestamp'], STREFA_POGODY)
    s15 = pd.Series(pog['naslonecznienie_sekundy'].to_numpy(float), index=t_utc)
    s60 = s15.rolling(4).sum()
    s60 = s60[(s60.index.minute == 0)].dropna()
    return {'15 min': (s15.index, s15.to_numpy(), 900.0), 'godzinowe': (s60.index, s60.to_numpy(), 3600.0)}


def wejscie(zrodlo, t_dev, offset_min):
    """Wejście słońca (frakcja*sin) na siatce czasu urządzenia; UTC = czas urządzenia - offset."""
    t_utc = pd.DatetimeIndex(t_dev) - pd.Timedelta(minutes=offset_min)
    fr, sin_el, inp = ws.wejscie_slonca(zrodlo[0], zrodlo[1], zrodlo[2], t_utc, LAT, LON)
    return fr, inp


def main():
    dane = wm.zbuduj_dane()
    t, at, hrt, crt, u, okna = dane['t'], dane['at'], dane['hrt'], dane['crt'], dane['u'], dane['okna']
    zrodla = zrodla_slonca()

    maska_testu = np.zeros(len(t), dtype=bool)
    for a, b in okna:
        maska_testu |= (t >= np.datetime64(a)) & (t <= np.datetime64(b + pd.Timedelta(hours=2)))

    w10 = filtr_tf(wm.STARE.K_W, wm.STARE.T1_W, wm.STARE.TZ_W, at, wm.DT, stan_ustalony=True)
    hrt_stary = w10 + filtr_tf(wm.STARE.K_H, wm.STARE.T1_H, wm.STARE.TZ_H, u, wm.DT)
    crt_stary = w10 + filtr_tf(wm.STARE.K_H_CRT, wm.STARE.T1_H_CRT, 0.0, u, wm.DT)

    s6 = slice(None, None, int(DT_FIT / wm.DT))
    t6, at6, hrt6, crt6, u6, mt6 = t[s6], at[s6], hrt[s6], crt[s6], u[s6], maska_testu[s6]
    hc6 = filtr_tf(wm.STARE.K_H_CRT, wm.STARE.T1_H_CRT, 0.0, u6, DT_FIT)
    n_tot = len(t6) + int((~mt6).sum())

    def reszty(w, sl_c, sl_h):
        return np.concatenate([crt6 - (w + hc6 + sl_c), (hrt6 - (w + sl_h))[~mt6]])

    def dopasuj_wspolnie(S6, ze_sloncem=True):
        if ze_sloncem:
            def f(p):
                w = filtr_tf(p[0], p[1], p[2], at6, DT_FIT, stan_ustalony=True)
                return reszty(w, filtr_tf(p[3], p[4], 0.0, S6, DT_FIT), filtr_tf(p[5], p[6], 0.0, S6, DT_FIT))
            x0 = [1.0, 4000.0, 800.0, 10.0, 5000.0, 8.0, 20000.0]
            lo = [0.3, 200.0, 0.0, 0.0, 60.0, 0.0, 60.0]
            hi = [2.5, 20000.0, 6000.0, 80.0, TS_MAX, 80.0, TS_MAX]
            xs = [0.1, 500.0, 200.0, 3.0, 1000.0, 3.0, 1000.0]
        else:
            def f(p):
                return reszty(filtr_tf(p[0], p[1], p[2], at6, DT_FIT, stan_ustalony=True), 0.0, 0.0)
            x0, lo, hi, xs = [1.1, 2500.0, 300.0], [0.3, 200.0, 0.0], [2.5, 20000.0, 6000.0], [0.1, 500.0, 200.0]
        r = least_squares(f, x0, bounds=(lo, hi), x_scale=xs)
        return r.x, float(np.sum(r.fun ** 2))

    print('\n1) Dopasowanie kanału słonecznego (wspólny G_W + G_S dla CRT i HRT), przesunięcie zegara urządzenia względem UTC')
    wyniki = {}
    for nazwa, zr in zrodla.items():
        skan = []
        for off in range(-60, 181, 15):
            fr6, inp6 = wejscie(zr, t6, off)
            p, sse = dopasuj_wspolnie(inp6)
            skan.append((off, sse, p))
        off, sse, p = min(skan, key=lambda x: x[1])
        wyniki[nazwa] = {'off': off, 'sse': sse, 'p': p}
        print(f"   wejście {nazwa:<10}: najlepsze przesunięcie zegara {off:+4d} min; łączne RMSE={np.sqrt(sse / n_tot):.3f} °C"
              f"   (skan: " + ', '.join(f"{o:+d}:{np.sqrt(s / n_tot):.2f}" for o, s, _ in skan[::2]) + ')')
    p0, sse0 = dopasuj_wspolnie(np.zeros(len(t6)), ze_sloncem=False)
    sse_st = float(np.sum(reszty(filtr_tf(wm.STARE.K_W, wm.STARE.T1_W, wm.STARE.TZ_W, at6, DT_FIT, stan_ustalony=True), 0.0, 0.0) ** 2))
    print(f"   bez słońca, G_W przeliczone: łączne RMSE={np.sqrt(sse0 / n_tot):.3f} °C;  stary model z symulatora: {np.sqrt(sse_st / n_tot):.3f} °C")
    r15, r60 = np.sqrt(wyniki['15 min']['sse'] / n_tot), np.sqrt(wyniki['godzinowe']['sse'] / n_tot)
    print(f"   => wejście godzinowe (jak w symulatorze) traci {100 * (r60 / r15 - 1):.1f}% RMSE względem 15-minutowego "
          f"({r60:.3f} vs {r15:.3f} °C); względem starego modelu nadal poprawa {100 * (1 - r60 / np.sqrt(sse_st / n_tot)):.0f}%")

    W = wyniki['godzinowe']            # dalej: wersja jak w symulatorze (godzinowa)
    off = W['off']
    Kw, T1w, Tzw, Ks_c, Ts_c, Ks_h, Ts_h = W['p']
    print(f"\n2) Parametry (wejście godzinowe, zegar urządzenia = UTC {off / 60:+.2f} h):")
    print(f"   G_W (HRT i CRT): K={Kw:.3f}  T1={T1w:.0f} s ({T1w / 60:.0f} min)  Tz={Tzw:.0f} s   (stary: {wm.STARE.K_W} / {wm.STARE.T1_W:.0f} / {wm.STARE.TZ_W:.0f})")
    print(f"   G_S CRT: Ks={Ks_c:.2f} °C  Ts={Ts_c:.0f} s ({Ts_c / 60:.0f} min)      G_S HRT: Ks={Ks_h:.2f} °C  Ts={Ts_h:.0f} s ({Ts_h / 60:.0f} min)")
    if max(Ts_c, Ts_h) > 0.98 * TS_MAX:
        print('   UWAGA: stała czasowa słońca dotknęła górnej granicy - słabo zidentyfikowana')

    fr6, inp6 = wejscie(zrodla['godzinowe'], t6, off)
    w_n6 = filtr_tf(Kw, T1w, Tzw, at6, DT_FIT, stan_ustalony=True)
    slonce_h6 = filtr_tf(Ks_h, Ts_h, 0.0, inp6, DT_FIT)
    maska_okien = np.zeros(len(t6), bool)
    for a, b in okna:
        maska_okien |= (t6 >= np.datetime64(a - pd.Timedelta(minutes=20))) & (t6 <= np.datetime64(b + pd.Timedelta(minutes=60)))

    def resid_h(p):
        return (hrt6 - (w_n6 + slonce_h6 + filtr_tf(p[0], p[1], p[2], u6, DT_FIT)))[maska_okien]
    r = least_squares(resid_h, [wm.STARE.K_H, wm.STARE.T1_H, wm.STARE.TZ_H], bounds=([5, 100, 0], [120, 8000, 3000]), x_scale=[10, 500, 100])
    K_H2, T1_H2, TZ_H2 = r.x
    print(f"\n3) G_H w oknach testu: stare K={wm.STARE.K_H:.1f}/T1={wm.STARE.T1_H:.0f}/Tz={wm.STARE.TZ_H:.0f}  RMSE={np.sqrt(np.mean(resid_h([wm.STARE.K_H, wm.STARE.T1_H, wm.STARE.TZ_H]) ** 2)):.2f} °C"
          f"   ->  nowe K={K_H2:.1f}/T1={T1_H2:.0f}/Tz={TZ_H2:.0f}  RMSE={np.sqrt(np.mean(r.fun ** 2)):.2f} °C")

    # --- model końcowy na siatce 10 s: TE SAME funkcje i stałe co w symulatorze (symulacja_fizyczna) ---
    # (stałe w symulatorze = wynik tego dopasowania zaokrąglony; wykres jest więc testem integracji)
    fr10, inp10 = wejscie(zrodla['godzinowe'], t, off)
    dt = wm.DT
    A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, opoz = fiz.przygotuj_modele_stanowe(dt)
    A_chd, B_chd, C_chd, D_chd, _ = signal.cont2discrete(signal.tf2ss(fiz.TF_CRT_HEATING.num, fiz.TF_CRT_HEATING.den), dt, method='zoh')
    n_roz = int(wm.ROZGRZEWKA_S / dt)
    w_sim = fiz.wylicz_skladowa_pogodowa(np.concatenate([np.full(n_roz, at[0]), at]), A_wd, B_wd, C_wd, D_wd, dt)[n_roz:]
    slonce_h10, slonce_c10 = fiz.wylicz_skladowe_slonca(inp10, dt)
    x_h, x_c = np.zeros((A_hd.shape[0], 1)), np.zeros((A_chd.shape[0], 1))
    h_sim, hc_sim = np.zeros(len(t)), np.zeros(len(t))
    for k in range(len(t)):
        uk = u[k - opoz] if k >= opoz else 0.0
        x_h = A_hd @ x_h + B_hd * uk
        h_sim[k] = float((C_hd @ x_h + D_hd * uk)[0, 0])
        x_c = A_chd @ x_c + B_chd * uk
        hc_sim[k] = float((C_chd @ x_c + D_chd * uk)[0, 0])
    crt_nowy = w_sim + slonce_c10 + hc_sim
    hrt_nowy = w_sim + slonce_h10 + h_sim
    # kontrola: model z dopasowania (lfilter, stałe niezaokrąglone) vs symulator (stałe zaokrąglone)
    crt_fit = filtr_tf(Kw, T1w, Tzw, at, dt, stan_ustalony=True) + filtr_tf(Ks_c, Ts_c, 0.0, inp10, dt) + filtr_tf(fiz.K_H_CRT, fiz.T1_H_CRT, 0.0, u, dt)
    hrt_fit = filtr_tf(Kw, T1w, Tzw, at, dt, stan_ustalony=True) + filtr_tf(Ks_h, Ts_h, 0.0, inp10, dt) + filtr_tf(K_H2, T1_H2, TZ_H2, u, dt)
    print(f"\n   Kontrola integracji (model z dopasowania vs funkcje symulatora): max |różnica| CRT={np.max(np.abs(crt_fit - crt_nowy)):.3f} °C, "
          f"HRT={np.max(np.abs(hrt_fit - hrt_nowy)):.3f} °C")

    print('\n4) Metryki (pomiar vs model):')
    zakresy = [('całe dane 21 dni', np.ones(len(t), bool)),
               ('tydzień 20-27.04', (t >= np.datetime64(wm.TYDZIEN[0])) & (t < np.datetime64(wm.TYDZIEN[1]))),
               ('doba 22.04', (t >= np.datetime64(wm.DZIEN[0])) & (t < np.datetime64(wm.DZIEN[1])))]
    tabela = []
    for nazwa, m in zakresy:
        for szyna, y, ms, mn in (('CRT', crt, crt_stary, crt_nowy), ('HRT', hrt, hrt_stary, hrt_nowy)):
            mm = m & ~maska_testu if (szyna == 'HRT' and nazwa.startswith('całe')) else m
            a, c = metr(y[mm], ms[mm]), metr(y[mm], mn[mm])
            tabela.append({'okres': nazwa, 'szyna': szyna, 'r2_stary': a['r2'], 'rmse_stary': a['rmse'], 'bias_stary': a['bias'],
                           'r2_nowy': c['r2'], 'rmse_nowy': c['rmse'], 'bias_nowy': c['bias']})
            print(f"   {nazwa:<18}{szyna}  stary: R²={a['r2']:.3f} RMSE={a['rmse']:.2f} bias={a['bias']:+.2f}   ->   ze słońcem: "
                  f"R²={c['r2']:.3f} RMSE={c['rmse']:.2f} bias={c['bias']:+.2f}")
    mm_okno = np.zeros(len(t), bool)
    for a, b in okna:
        mm_okno |= (t >= np.datetime64(a)) & (t <= np.datetime64(b))
    for szyna, y, ms, mn in (('HRT', hrt, hrt_stary, hrt_nowy), ('CRT', crt, crt_stary, crt_nowy)):
        a, c = metr(y[mm_okno], ms[mm_okno]), metr(y[mm_okno], mn[mm_okno])
        print(f"   w oknach testu {szyna}: stary RMSE={a['rmse']:.2f} bias={a['bias']:+.2f}  ->  nowy RMSE={c['rmse']:.2f} bias={c['bias']:+.2f}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pd.DataFrame(tabela).to_csv(os.path.join(OUTPUT_DIR, 'nasloneczenie_metryki.csv'), index=False)
    par = [('przesuniecie_zegara_urzadzenia_min', off), ('G_W_K', Kw), ('G_W_T1_s', T1w), ('G_W_Tz_s', Tzw),
           ('G_S_CRT_Ks_C', Ks_c), ('G_S_CRT_Ts_s', Ts_c), ('G_S_HRT_Ks_C', Ks_h), ('G_S_HRT_Ts_s', Ts_h),
           ('G_H_K', K_H2), ('G_H_T1_s', T1_H2), ('G_H_Tz_s', TZ_H2)]
    pd.DataFrame(par, columns=['parametr', 'wartosc']).to_csv(os.path.join(OUTPUT_DIR, 'nasloneczenie_parametry.csv'), index=False)
    print('\n5) Gotowy blok stałych do symulacja_fizyczna.py:')
    print(f"   K_W = {Kw:.4f}; T1_W = {T1w:.1f}; TZ_W = {Tzw:.1f}")
    print(f"   K_H = {K_H2:.2f}; T1_H = {T1_H2:.1f}; TZ_H = {TZ_H2:.1f}")
    print(f"   K_S_CRT = {Ks_c:.3f}; T1_S_CRT = {Ts_c:.1f}; K_S_HRT = {Ks_h:.3f}; T1_S_HRT = {Ts_h:.1f}")

    wynik = dict(dane)
    wynik.update({'S_frakcja': fr10 * 900.0, 'S': inp10 * 900.0, 'hrt_stary': hrt_stary, 'crt_stary': crt_stary,
                  'hrt_nowy': hrt_nowy, 'crt_nowy': crt_nowy, 'slonce_h': slonce_h10, 'slonce_c': slonce_c10,
                  'par': (K_H2, T1_H2, TZ_H2, {'CRT': {'Ks': Ks_c, 'Ts': Ts_c}, 'HRT': {'Ks': Ks_h, 'Ts': Ts_h}}, off, (Kw, T1w, Tzw))})
    rysuj_z_sloncem(wynik, wm.TYDZIEN, 'tydzień 20-27.04.2026', 'model_z_sloncem_tydzien.png')
    rysuj_z_sloncem(wynik, wm.DZIEN, 'doba 22.04.2026 (test skokowy grzania)', 'model_z_sloncem_dzien.png', dzien=True)


def rysuj_z_sloncem(d, okno, tytul_widoku, plik, dzien=False):
    t0, t1 = np.datetime64(okno[0]), np.datetime64(okno[1])
    m = (d['t'] >= t0) & (d['t'] < t1)
    t = d['t'][m]
    K_H2, T1_H2, TZ_H2, wybor, off, (Kw, T1w, Tzw) = d['par']
    mh_s, mh_n = metr(d['hrt'][m], d['hrt_stary'][m]), metr(d['hrt'][m], d['hrt_nowy'][m])
    mc_s, mc_n = metr(d['crt'][m], d['crt_stary'][m]), metr(d['crt'][m], d['crt_nowy'][m])
    test_w_oknie = [(a, b) for a, b in d['okna'] if a < okno[1] and b > okno[0]]

    fig = plt.figure(figsize=(20, 14.5))
    fig.patch.set_facecolor(TLO)
    gs = gridspec.GridSpec(6, 1, figure=fig, left=0.055, right=0.975, top=0.925, bottom=0.075, hspace=0.09,
                           height_ratios=[3.3, 3.3, 1.2, 1.2, 1.2, 0.8])
    axs = [fig.add_subplot(gs[0])]
    for i in range(1, 6):
        axs.append(fig.add_subplot(gs[i], sharex=axs[0]))
    ax_h, ax_c, ax_r, ax_a, ax_s, ax_g = axs
    for ax in axs:
        ax.set_facecolor(TLO_OS)
        ax.tick_params(colors=TEKST, labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(SIATKA)
        ax.grid(True, color=SIATKA, alpha=0.7, lw=0.5)
    for ax in axs[:-1]:
        plt.setp(ax.get_xticklabels(), visible=False)
    for a, b in test_w_oknie:
        for ax in (ax_h, ax_c, ax_a, ax_s):
            ax.axvspan(max(a, okno[0]), min(b, okno[1]), color=KOL['uheat'], alpha=0.10, lw=0)

    ax_h.plot(t, d['hrt'][m], color=KOL['meas'], lw=1.2, alpha=0.85, label='HRT pomiar', zorder=5)
    ax_h.plot(t, d['hrt_nowy'][m], color=KOL['model'], lw=1.8, alpha=0.95, zorder=6,
              label=f"HRT model + słońce   R²={mh_n['r2']:.3f}  RMSE={mh_n['rmse']:.2f}°C  bias={mh_n['bias']:+.2f}°C")
    ax_h.plot(t, d['hrt_stary'][m], color=KOL['weather'], lw=1.1, alpha=0.75, ls='--', zorder=4,
              label=f"HRT model bez słońca (stary)   R²={mh_s['r2']:.3f}  RMSE={mh_s['rmse']:.2f}°C  bias={mh_s['bias']:+.2f}°C")
    ax_h.plot(t, d['slonce_h'][m], color=KOL_SLONCE, lw=1.0, alpha=0.7, ls=':', zorder=3, label='składnik słoneczny G_S·słońce')
    ax_h.set_ylabel('HRT [°C]', color=TEKST, fontsize=9)
    ax_h.legend(loc='upper left', fontsize=8, facecolor='#151c2e', labelcolor='white', framealpha=0.9)

    ax_c.plot(t, d['crt'][m], color=KOL['meas'], lw=1.2, alpha=0.85, label='CRT pomiar', zorder=5)
    ax_c.plot(t, d['crt_nowy'][m], color=KOL['model'], lw=1.8, alpha=0.95, zorder=6,
              label=f"CRT model + słońce   R²={mc_n['r2']:.3f}  RMSE={mc_n['rmse']:.2f}°C  bias={mc_n['bias']:+.2f}°C")
    ax_c.plot(t, d['crt_stary'][m], color=KOL['weather'], lw=1.1, alpha=0.75, ls='--', zorder=4,
              label=f"CRT model bez słońca (stary)   R²={mc_s['r2']:.3f}  RMSE={mc_s['rmse']:.2f}°C  bias={mc_s['bias']:+.2f}°C")
    ax_c.plot(t, d['slonce_c'][m], color=KOL_SLONCE, lw=1.0, alpha=0.7, ls=':', zorder=3, label='składnik słoneczny G_S·słońce')
    ax_c.set_ylabel('CRT [°C]', color=TEKST, fontsize=9)
    ax_c.legend(loc='upper left', fontsize=8, facecolor='#151c2e', labelcolor='white', framealpha=0.9)

    ax_r.axhline(0, color='#3a4060', lw=0.8)
    ax_r.plot(t, (d['hrt'] - d['hrt_nowy'])[m], color=KOL['resid_h'], lw=0.9, alpha=0.9, label='HRT (z słońcem)')
    ax_r.plot(t, (d['crt'] - d['crt_nowy'])[m], color=KOL['resid_c'], lw=0.9, alpha=0.9, label='CRT (z słońcem)')
    ax_r.set_ylabel('Residuum\n[°C]', color=TEKST, fontsize=8)
    ax_r.legend(loc='upper left', fontsize=7.5, ncol=2, facecolor='#151c2e', labelcolor='white', framealpha=0.9)

    ax_a.fill_between(t, d['at'][m], color=KOL['at'], alpha=0.30)
    ax_a.plot(t, d['at'][m], color=KOL['at'], lw=0.9)
    ax_a.set_ylabel('AT [°C]', color=TEKST, fontsize=8)

    ax_s.plot(t, d['S_frakcja'][m], color=KOL_SLONCE, lw=0.9, alpha=0.55, ls='--', label='ułamek słońca (średnia godzinowa, interpolowana)')
    ax_s.fill_between(t, d['S'][m], color=KOL_SLONCE, alpha=0.35)
    ax_s.plot(t, d['S'][m], color=KOL_SLONCE, lw=0.9, label='wejście modelu = ułamek x sin(wysokość słońca)')
    ax_s.set_ylim(-20, 1000)
    ax_s.set_yticks([0, 450, 900])
    ax_s.set_ylabel('Słońce\n[s/15 min]', color=TEKST, fontsize=8)
    ax_s.legend(loc='upper right', fontsize=7.2, facecolor='#151c2e', labelcolor='white', framealpha=0.9)
    ax_s.text(0.005, 0.86, '0 = brak słońca (noc / zachmurzenie), 900 = pełne słońce', transform=ax_s.transAxes,
              ha='left', va='top', fontsize=7.5, color='#8fa0c0')

    uu, znane = d['u'][m], d['znane'][m]
    ax_g.fill_between(t, 0, 1, where=~znane, facecolor='none', edgecolor='#3a4562', hatch='////', lw=0)
    ax_g.fill_between(t, uu, where=znane, color=KOL['uheat'], alpha=0.55, step='post')
    ax_g.step(t, np.where(znane, uu, np.nan), color=KOL['uheat'], lw=1.0, where='post')
    ax_g.set_ylim(-0.05, 1.25)
    ax_g.set_yticks([0, 1])
    ax_g.set_ylabel('Grzanie\n[0/1]', color=TEKST, fontsize=8)
    ax_g.text(0.995, 0.5, 'kreskowanie = stan grzania NIEZNANY (model zakłada 0)', transform=ax_g.transAxes,
              ha='right', va='center', fontsize=7.5, color='#8fa0c0')

    if dzien:
        ax_g.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax_g.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax_g.set_xlabel('Godzina (czas urządzenia)', color=TEKST, fontsize=8)
    else:
        ax_g.xaxis.set_major_locator(mdates.DayLocator())
        ax_g.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))
        dni_pl = ['pon', 'wt', 'śr', 'czw', 'pt', 'sob', 'niedz']
        ax_g.xaxis.set_major_formatter(plt.FuncFormatter(
            lambda x, _: (lambda dt: f"{dt:%d.%m}\n{dni_pl[dt.weekday()]}")(mdates.num2date(x))))
        ax_g.set_xlabel('Data', color=TEKST, fontsize=8)
    ax_g.set_xlim(t[0], t[-1])
    plt.setp(ax_g.get_xticklabels(), visible=True, color=TEKST)

    fig.suptitle(f'Model połączony + nasłonecznienie vs dane rzeczywiste - {tytul_widoku}', color='#c5cfe8',
                 fontsize=13, x=0.055, ha='left', y=0.975)
    fig.text(0.055, 0.945,
             f"G_W: K={Kw:.3f}, T1={T1w:.0f}s, Tz={Tzw:.0f}s (było {wm.STARE.K_W}/{wm.STARE.T1_W:.0f}/{wm.STARE.TZ_W:.0f})   |   G_S: HRT Ks={wybor['HRT']['Ks']:.1f}°C, "
             f"Ts={wybor['HRT']['Ts'] / 60:.0f} min; CRT Ks={wybor['CRT']['Ks']:.1f}°C, Ts={wybor['CRT']['Ts'] / 60:.0f} min   |   "
             f"G_H: K={K_H2:.1f}, T1={T1_H2:.0f}s, Tz={TZ_H2:.0f}s (było {wm.STARE.K_H}/{wm.STARE.T1_H:.0f}/{wm.STARE.TZ_H:.0f})   |   zegar urządzenia = UTC {off / 60:+.2f} h",
             color='#8fa0c0', fontsize=8.5, ha='left')
    fig.text(0.055, 0.03,
             f"HRT: bez słońca R²={mh_s['r2']:.3f} RMSE={mh_s['rmse']:.2f}°C  ->  ze słońcem R²={mh_n['r2']:.3f} RMSE={mh_n['rmse']:.2f}°C   |   "
             f"CRT: bez słońca R²={mc_s['r2']:.3f} RMSE={mc_s['rmse']:.2f}°C  ->  ze słońcem R²={mc_n['r2']:.3f} RMSE={mc_n['rmse']:.2f}°C",
             color='#8fa0c0', fontsize=8.5, ha='left')
    fig.text(0.055, 0.01,
             'Słońce z Open-Meteo (Wrocław Popowice, uśrednione do godzin i interpolowane - jak w symulatorze; to nie pomiar na miejscu). '
             'G_H dopasowane w oknach testu (na próbie uczącej).', color='#5d6b8c', fontsize=7.8, ha='left')
    sciezka = os.path.join(OUTPUT_DIR, plik)
    fig.savefig(sciezka, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f'Zapisano: {sciezka}')


if __name__ == '__main__':
    main()
