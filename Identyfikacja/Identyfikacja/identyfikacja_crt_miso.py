# Identyfikacja/Identyfikacja/identyfikacja_crt_miso.py
#
# DODATKOWY, samodzielny skrypt (nie modyfikuje żadnego innego skryptu w tym
# folderze) - na życzenie użytkownika (2026-09-28): "wpływ HRT względem CRT
# na obiekt cały... to nie grzałka wchodzi [jako wejście modelu], tylko
# grzanie HRT powoduje wzrost CRT... generalnie na CRT powinno wpływać tylko
# HRT oraz temperatura powietrza, więc zrób testy, które utworzą transmitancję
# o takich wejściach jako model MISO".
#
# RÓŻNICA względem identyfikacja_crt.py (AT -> CRT, jeden kanał, TYLKO
# długoterminowe okno bez testu skokowego, bo tamten skrypt szukał "czystej
# pogody"): tu WEJŚCIAMI modelu MISO są HRT (temperatura szyny OGRZEWANEJ,
# zmierzona - NIE moc grzania) i AT (temperatura powietrza), a CELEM jest
# CRT. HRT i AT są ZAWSZE mierzone (w odróżnieniu od mocy grzania, logowanej
# tylko w oknach testu skokowego) - dlatego używamy CAŁEGO logu (~21 dni),
# BEZ wykluczania dni testu skokowego. To wręcz POŻĄDANE: w oknie testu
# skokowego grzanie podnosi HRT niezależnie od AT (który w tym krótkim oknie
# ledwo się zmienia) - ta chwilowa DEKORELACJA HRT od AT jest dokładnie tym,
# co pozwala model MISO odróżnić wpływ HRT od wpływu AT na CRT (bez niej,
# na samym długim oknie, HRT i AT są silnie skorelowane - oba podążają za
# pogodą - i model nie miałby jak rozdzielić ich wkładów).
#
# Metodologia (matematyka/silnik dopasowania) identyczna jak w
# identyfikacja_miso.py/identyfikacja_crt.py - biblioteka postaci
# transmitancji I/FO/FO_Z/SO/SO_Z/TO (z/bez opóźnienia), MNK przez
# scipy.optimize.curve_fit, symulacja przez
# scipy.signal.TransferFunction.to_discrete + lfilter, ranking wg adj R²/AIC,
# potem WSPÓLNY model MISO (CRT = y0 + G_HRT(HRT) + G_AT(AT)) i analiza
# ablacyjna (usunięcie kanału -> spadek R² = miara jego wpływu).
#
# Wynik: CSV/Excel + wykresy w wyniki_identyfikacja/ (ten sam folder co reszta
# skryptów identyfikacyjnych), plus jawny odczyt "ile °C CRT rośnie na 1°C HRT"
# (gain kanału HRT w dopasowanym modelu MISO).
#
# Uruchomienie: python identyfikacja_crt_miso.py   (z tego folderu)

import os
import re
import sys
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy import signal

try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

# ==========================================================================
# 1. KONFIGURACJA
# ==========================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "algo (4).log")
OUTPUT_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "wyniki_identyfikacja")
os.makedirs(OUTPUT_DIR, exist_ok=True)

R2_MIN_PLOT = 0.3
RESAMPLE_S = 10

QUICK_MODE_DZIELNIK = 4
L_SEARCH_MIN = 0
L_SEARCH_MAX = 360          # próbki (360 x 10s = 1h) - jak w identyfikacja_crt.py
L_SEARCH_STEP = max(1, 5 * QUICK_MODE_DZIELNIK)

# Analiza OGRANICZONA do okien testu skokowego (patrz sekcja 10 niżej) - okna
# same są krótkie (~80-90 min = ~480-540 próbek po 10s), więc szukanie
# opóźnienia do 1h (jak wyżej) zjadłoby większość okna - siatka L tu węższa
# (do 20 min) i gęstsza (co 1 próbkę zamiast co 20).
L_SEARCH_MAX_OKNO = 120     # próbki (120 x 10s = 20 min)
L_SEARCH_STEP_OKNO = 1

INF = 50_000


# ==========================================================================
# 2. PASEK POSTĘPU
# ==========================================================================
class PasekPostepu:
    def __init__(self, calkowita_liczba_krokow, etykieta="Postęp"):
        self.total = max(1, calkowita_liczba_krokow)
        self.i = 0
        self.etykieta = etykieta
        self.t0 = time.time()

    def krok(self, opis=""):
        self.i += 1
        procent = min(100.0, 100.0 * self.i / self.total)
        elapsed = time.time() - self.t0
        eta = (elapsed / self.i) * (self.total - self.i) if self.i > 0 else 0
        pasek_dlugosc = 30
        wypelnione = int(pasek_dlugosc * procent / 100.0)
        pasek = "#" * wypelnione + "-" * (pasek_dlugosc - wypelnione)
        linia = (f"\r[{self.etykieta}] [{pasek}] {procent:5.1f}%  "
                 f"({self.i}/{self.total})  ETA {eta:5.0f}s  {opis[:60]:<60}")
        sys.stdout.write(linia)
        sys.stdout.flush()
        if self.i >= self.total:
            sys.stdout.write("\n")

    def zakoncz(self):
        if self.i < self.total:
            self.i = self.total
            sys.stdout.write("\n")


# ==========================================================================
# 3. PARSOWANIE SUROWEGO LOGU (powielone z identyfikacja_miso.py/crt.py dla
#    samodzielności - patrz tam po komentarze uzasadniające każdy krok)
# ==========================================================================
_PAT_P1 = re.compile(
    r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) ALGOp1: '
    r'CRT ([\-\d.]+), HRT ([\-\d.]+), AT:?\s*([\-\d.]+)'
)
_PAT_P2 = re.compile(
    r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) ALGOp2: '
    r'DPT ([\-\d.]+), RH (\d+), PRESS (\d+), PRECIP (\d+), SNOW (\d+)'
)
_PAT_P3 = re.compile(
    r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) ALGOp3: '
    r'PWRL1 (\d+), PWRL2 (\d+)'
)
_PAT_TRYB = re.compile(
    r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) '
    r'ALGO new control mode for circuit \d+: (\w+)'
)


def wczytaj_log(sciezka):
    rows_p1, rows_p2, rows_p3, tryby = [], [], [], []
    with open(sciezka, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            m = _PAT_P1.match(line)
            if m:
                rows_p1.append((m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))))
                continue
            m = _PAT_P2.match(line)
            if m:
                rows_p2.append((m.group(1), float(m.group(2)), int(m.group(3)),
                                 int(m.group(4)), int(m.group(5)), int(m.group(6))))
                continue
            m = _PAT_P3.match(line)
            if m:
                rows_p3.append((m.group(1), float(m.group(2)), float(m.group(3))))
                continue
            m = _PAT_TRYB.match(line)
            if m:
                tryby.append((m.group(1), m.group(2)))

    def do_df(rows, kolumny):
        df = pd.DataFrame(rows, columns=['Timestamp'] + kolumny)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%Y.%m.%d %H:%M:%S.%f')
        return df.sort_values('Timestamp').reset_index(drop=True)

    df_p1 = do_df(rows_p1, ['CRT', 'HRT', 'AT'])
    df_p2 = do_df(rows_p2, ['DPT', 'RH', 'PRESS', 'PRECIP', 'SNOW'])
    df_p3 = do_df(rows_p3, ['PWRL1', 'PWRL2'])

    df = pd.merge_asof(df_p1, df_p2, on='Timestamp', tolerance=pd.Timedelta('2s'), direction='nearest')
    df = pd.merge_asof(df, df_p3, on='Timestamp', tolerance=pd.Timedelta('2s'), direction='nearest')
    df = df.dropna(subset=['CRT', 'HRT', 'AT']).reset_index(drop=True)

    okna = []
    poczatek = None
    for ts_str, tryb in tryby:
        ts = pd.to_datetime(ts_str, format='%Y.%m.%d %H:%M:%S.%f')
        if tryb == 'IndOn' and poczatek is None:
            poczatek = ts
        elif tryb != 'IndOn' and poczatek is not None:
            okna.append((poczatek, ts))
            poczatek = None
    if poczatek is not None:
        okna.append((poczatek, df['Timestamp'].max()))

    print(f"Wczytano log: {len(df)} próbek połączonych.")
    print(f"Zakres czasu: {df['Timestamp'].min()}  ->  {df['Timestamp'].max()}")
    print(f"Wykryto {len(okna)} okien testu skokowego (informacyjnie - NIE wykluczamy ich tutaj, patrz nagłówek pliku):")
    for a, b in okna:
        print(f"    {a}  ->  {b}   ({(b - a).total_seconds() / 60:.1f} min)")

    return df, okna


def resampluj(df, dt_s):
    df = df.drop_duplicates(subset='Timestamp').sort_values('Timestamp').reset_index(drop=True)
    siatka = pd.date_range(df['Timestamp'].min(), df['Timestamp'].max(), freq=f'{dt_s}s')
    out = pd.DataFrame({'Timestamp': siatka})
    idx_num = df['Timestamp'].to_numpy().astype('int64')
    siatka_num = siatka.to_numpy().astype('int64')
    for k in ['CRT', 'HRT', 'AT']:
        out[k] = np.interp(siatka_num, idx_num, df[k].to_numpy())
    return out


# ==========================================================================
# 4. RDZEŃ TRANSMITANCJI (identyczny jak identyfikacja_miso.py/crt.py)
# ==========================================================================
def apply_delay(u, L):
    L_int = int(max(0, round(L)))
    if L_int == 0:
        return u
    out = np.zeros_like(u)
    if L_int < len(u):
        out[L_int:] = u[:-L_int]
    return out


def get_sim(num, den, u):
    """dt=RESAMPLE_S - patrz identyfikacja_miso.py::get_sim po pełne uzasadnienie
    (poprawka jednostek T1/T2/Tz/L z 2026-09-25 - tu zastosowana od razu poprawnie)."""
    den = [max(abs(d), 1e-10) if i == 0 else d for i, d in enumerate(den)]
    sys_d = signal.TransferFunction(num, den).to_discrete(dt=RESAMPLE_S, method='gbt', alpha=0.5)
    return signal.lfilter(sys_d.num, sys_d.den, u)


def build_poly(roots_T):
    poly = np.array([1.0])
    for T in roots_T:
        poly = np.polymul(poly, [max(T, 1e-6), 1.0])
    return poly.tolist()


def compute_metrics(y_true, y_pred, n_params):
    n = len(y_true)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - ss_res / (ss_tot + 1e-30)
    adj_r2 = 1 - (1 - r2) * (n - 1) / max(n - n_params - 1, 1)
    mse = max(ss_res / n, 1e-30)
    aic = n * np.log(mse) + 2 * n_params
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(y_true - y_pred))
    return {"r2": r2, "adj_r2": adj_r2, "aic": aic, "rmse": rmse, "mae": mae}


# ==========================================================================
# 5. BIBLIOTEKA POSTACI MODELI (SISO) - forma "kanału pogodowego" (sygnał
#    ciągły, wolnozmienny) - HRT i AT są oba tego typu (w odróżnieniu od
#    binarnej/skokowej mocy grzania w identyfikacja_miso.py).
# ==========================================================================
def m_I(u, K):
    return get_sim([K], [1, 0], u)


def m_FO(u, K, T1):
    return get_sim([K], [T1, 1], u)


def m_FO_Z(u, K, T1, Tz):
    return get_sim([K * Tz, K], [T1, 1], u)


def m_SO(u, K, T1, T2):
    return get_sim([K], build_poly([T1, T2]), u)


def m_SO_Z(u, K, T1, T2, Tz):
    return get_sim([K * Tz, K], build_poly([T1, T2]), u)


def m_TO(u, K, T1, T2, T3):
    return get_sim([K], build_poly([T1, T2, T3]), u)


def modele_ciagle():
    bez_L = [
        {"name": "I", "func": m_I, "p0": [0.1], "bounds": ([-10], [10]), "n": 1},
        {"name": "FO", "func": m_FO, "p0": [0.5, 600], "bounds": ([-2.0, 1], [2.0, 200_000]), "n": 2},
        {"name": "FO_Z", "func": m_FO_Z, "p0": [0.5, 600, 100], "bounds": ([-2.0, 1, -100_000], [2.0, 200_000, 100_000]), "n": 3},
        {"name": "SO", "func": m_SO, "p0": [0.5, 3000, 500], "bounds": ([-2.0, 1, 1], [2.0, 200_000, 200_000]), "n": 3},
        {"name": "SO_Z", "func": m_SO_Z, "p0": [0.5, 3000, 500, 100], "bounds": ([-2.0, 1, 1, -100_000], [2.0, 200_000, 200_000, 100_000]), "n": 4},
        {"name": "TO", "func": m_TO, "p0": [0.5, 2000, 500, 100], "bounds": ([-2.0, 1, 1, 1], [2.0, 200_000, 200_000, 200_000]), "n": 4},
    ]
    z_L = [
        {"name": "FOD", "func_no_L": m_FO, "p0": [0.5, 600], "bounds_no_L": ([-2.0, 1], [2.0, 200_000]), "bounds_with_L": ([-2.0, 1, 0], [2.0, 200_000, L_SEARCH_MAX])},
        {"name": "SOD", "func_no_L": m_SO, "p0": [0.5, 3000, 500], "bounds_no_L": ([-2.0, 1, 1], [2.0, 200_000, 200_000]), "bounds_with_L": ([-2.0, 1, 1, 0], [2.0, 200_000, 200_000, L_SEARCH_MAX])},
    ]
    return bez_L, z_L


# ==========================================================================
# 6. SILNIK DOPASOWANIA (SISO)
# ==========================================================================
def _fit_bez_L(m, u, y):
    popt, _ = curve_fit(m["func"], u, y, p0=m["p0"], bounds=m["bounds"], maxfev=20000)
    return popt


def _znajdz_L(m, u, y, L_min, L_max, L_step, pasek=None):
    best_adj = -np.inf
    best_L, best_popt = 0, None
    for L_try in range(L_min, L_max + 1, L_step):
        u_shift = apply_delay(u, L_try)
        try:
            popt, _ = curve_fit(m["func_no_L"], u_shift, y, p0=m["p0"], bounds=m["bounds_no_L"], maxfev=8000)
            y_pred = m["func_no_L"](u_shift, *popt)
            met = compute_metrics(y, y_pred, len(popt) + 1)
            if met["adj_r2"] > best_adj:
                best_adj, best_L, best_popt = met["adj_r2"], L_try, popt
        except Exception:
            pass
        if pasek is not None:
            pasek.krok(f"L={L_try}")
    return best_L, best_popt


def _fit_z_L(m, u, y, L_min, L_max, L_step, pasek=None):
    L_best, popt_no_L = _znajdz_L(m, u, y, L_min, L_max, L_step, pasek)
    if popt_no_L is None:
        raise RuntimeError("brak zbieżności dla żadnego L")
    p0_full = list(popt_no_L) + [float(L_best)]
    popt, _ = curve_fit(m["func_with_L"], u, y, p0=p0_full, bounds=m["bounds_with_L"], maxfev=20000)
    return popt[:-1], popt[-1]


def przesiej_kanal(nazwa_kanalu, u, y, modele_bez_L, modele_z_L, L_min, L_max, L_step, pasek):
    wyniki = []
    for m in modele_bez_L:
        try:
            popt = _fit_bez_L(m, u, y)
            y_pred = m["func"](u, *popt)
            met = compute_metrics(y, y_pred, len(popt))
            wyniki.append({"kanal": nazwa_kanalu, "model": m["name"], "typ": "brak L",
                            "popt": popt, "L": None, "func": m["func"],
                            "func_base": m["func"], "popt_bez_L": popt, **met})
        except Exception as e:
            wyniki.append({"kanal": nazwa_kanalu, "model": m["name"], "typ": "BŁĄD",
                            "popt": None, "L": None, "func": None, "func_base": None, "popt_bez_L": None,
                            "r2": np.nan, "adj_r2": -np.inf, "aic": np.nan, "rmse": np.nan, "mae": np.nan,
                            "blad": str(e)})
        pasek.krok(f"{nazwa_kanalu}/{m['name']}")

    for m in modele_z_L:
        liczba_L = len(range(L_min, L_max + 1, L_step))
        try:
            popt_bez_L, L_best = _fit_z_L(m, u, y, L_min, L_max, L_step, pasek=None)
            popt_pelne = list(popt_bez_L) + [L_best]
            y_pred = m["func_with_L"](u, *popt_pelne)
            met = compute_metrics(y, y_pred, len(popt_pelne))
            wyniki.append({"kanal": nazwa_kanalu, "model": m["name"], "typ": "L iter.",
                            "popt": popt_pelne, "L": L_best, "func": m["func_with_L"],
                            "func_base": m["func_no_L"], "popt_bez_L": popt_bez_L, **met})
        except Exception as e:
            wyniki.append({"kanal": nazwa_kanalu, "model": m["name"], "typ": "BŁĄD",
                            "popt": None, "L": None, "func": None, "func_base": None, "popt_bez_L": None,
                            "r2": np.nan, "adj_r2": -np.inf, "aic": np.nan, "rmse": np.nan, "mae": np.nan,
                            "blad": str(e)})
        pasek.krok(f"{nazwa_kanalu}/{m['name']} (L-search x{liczba_L})")

    return wyniki


# ==========================================================================
# 7. MODEL MISO WSPÓLNY (identyczne jak identyfikacja_miso.py)
# ==========================================================================
def zbuduj_funkcje_miso(wybrane_kanaly):
    segmenty = []
    p0, lo, hi = [], [], []
    opis = []

    for nazwa, u, wynik in wybrane_kanaly:
        func_bazowa = wynik["func_base"]
        base_params = list(wynik["popt_bez_L"])
        L = wynik["L"]
        n_bez_L = len(base_params)
        segmenty.append((nazwa, func_bazowa, n_bez_L, L))
        p0.extend(base_params)
        lo.extend([-np.inf] * n_bez_L)
        hi.extend([np.inf] * n_bez_L)
        opis.extend([f"{nazwa}.p{i}" for i in range(n_bez_L)])

    p0.append(0.0)
    lo.append(-np.inf)
    hi.append(np.inf)
    opis.append("y0")

    def func_miso(X, *params):
        total = np.zeros(X.shape[1])
        idx = 0
        for (nazwa, func_bazowa, n_par, L), (_, u_arr, _) in zip(segmenty, wybrane_kanaly):
            p = params[idx:idx + n_par]
            u_eff = apply_delay(u_arr, L) if L else u_arr
            total = total + func_bazowa(u_eff, *p)
            idx += n_par
        total = total + params[-1]
        return total

    return func_miso, p0, lo, hi, opis, segmenty


def dopasuj_miso(wybrane_kanaly, y, pasek=None):
    func_miso, p0, lo, hi, opis, segmenty = zbuduj_funkcje_miso(wybrane_kanaly)
    X = np.vstack([u for _, u, _ in wybrane_kanaly])

    def wrapper(X_flat_ignored, *params):
        return func_miso(X, *params)

    popt, _ = curve_fit(wrapper, np.zeros(X.shape[1]), y, p0=p0, bounds=(lo, hi), maxfev=40000)
    y_pred = func_miso(X, *popt)
    met = compute_metrics(y, y_pred, len(popt))
    if pasek is not None:
        pasek.krok("model MISO (HRT+AT)")
    return {"y_pred": y_pred, "popt": popt, "opis_param": opis, "segmenty": segmenty, **met}


def analiza_ablacyjna(wybrane_kanaly, y, pelny_wynik, pasek=None):
    wyniki = []
    for i, (nazwa, _, _) in enumerate(wybrane_kanaly):
        pozostale = [k for j, k in enumerate(wybrane_kanaly) if j != i]
        if not pozostale:
            continue
        try:
            wynik_bez = dopasuj_miso(pozostale, y)
            delta_r2 = pelny_wynik["r2"] - wynik_bez["r2"]
            delta_adj = pelny_wynik["adj_r2"] - wynik_bez["adj_r2"]
            wyniki.append({"kanal": nazwa, "r2_bez_kanalu": wynik_bez["r2"],
                            "adj_r2_bez_kanalu": wynik_bez["adj_r2"],
                            "delta_r2": delta_r2, "delta_adj_r2": delta_adj})
        except Exception as e:
            wyniki.append({"kanal": nazwa, "r2_bez_kanalu": np.nan, "adj_r2_bez_kanalu": np.nan,
                            "delta_r2": np.nan, "delta_adj_r2": np.nan, "blad": str(e)})
        if pasek is not None:
            pasek.krok(f"ablacja: bez kanału {nazwa}")
    return sorted(wyniki, key=lambda w: -(w["delta_r2"] if not np.isnan(w["delta_r2"]) else -999))


# ==========================================================================
# 7b. ANALIZA OGRANICZONA DO OKNA TESTU SKOKOWEGO (na życzenie użytkownika,
#     2026-09-28: "jedziesz z tym" - dopisanie wariantu ograniczonego TYLKO do
#     okien, gdzie NA PEWNO wiemy, że grzanie działa niezależnie od AT, żeby
#     dostać czystszy szacunek efektu HRT->CRT niż z pełnych 21 dni, gdzie
#     ten słaby, krótkotrwały sygnał ginie w silniejszym, długoterminowym
#     szumie korelacji HRT-z-pogodą (patrz wynik modelu MISO na całym logu -
#     ujemny, niefizyczny K_HRT).
# ==========================================================================
def analizuj_okno_skokowe(nazwa_okna, df_okno):
    """
    Dopasowuje CRT = y0 + G_HRT(HRT) + G_AT(AT) WYŁĄCZNIE na próbkach z
    jednego, ciągłego okna testu skokowego (bez zszywania z innymi oknami -
    unika artefaktu nieciągłości czasu przy lfilter, patrz komentarz w
    identyfikacja_miso.py przy df_pog). Zwraca dict z wynikiem MISO, ablacją
    i gain'ami, albo None jeśli dopasowanie się nie powiodło (za mało próbek).
    """
    t = df_okno['Timestamp'].to_numpy()
    y = df_okno['CRT'].to_numpy()
    u_hrt = df_okno['HRT'].to_numpy()
    u_at = df_okno['AT'].to_numpy()
    n = len(df_okno)
    print(f"\n--- Okno '{nazwa_okna}': {n} próbek ({n * RESAMPLE_S / 60:.1f} min), "
          f"ΔHRT={u_hrt.max() - u_hrt.min():.2f}°C, ΔAT={u_at.max() - u_at.min():.2f}°C, "
          f"ΔCRT={y.max() - y.min():.2f}°C ---")

    kanaly = {'HRT': u_hrt, 'AT': u_at}
    modele_bez_L, modele_z_L = modele_ciagle()
    total_kroki = len(kanaly) * (len(modele_bez_L) + len(modele_z_L)) + 1 + len(kanaly)
    pasek = PasekPostepu(total_kroki, etykieta=f"MISO {nazwa_okna}")
    wszystkie_wyniki = {}
    for nazwa, u_k in kanaly.items():
        w = przesiej_kanal(nazwa, u_k, y, modele_bez_L, modele_z_L,
                            L_SEARCH_MIN, L_SEARCH_MAX_OKNO, L_SEARCH_STEP_OKNO, pasek)
        wszystkie_wyniki[nazwa] = w
        najlepszy = max(w, key=lambda x: x["adj_r2"])
        print(f"  SISO {nazwa} -> CRT: {najlepszy['model']} adj R²={najlepszy['adj_r2']:.4f} K={najlepszy['popt'][0]:.4f}")

    wybrane_kanaly = [(nazwa, u_k, max(wszystkie_wyniki[nazwa], key=lambda x: x["adj_r2"]))
                       for nazwa, u_k in kanaly.items()]
    try:
        wynik_miso = dopasuj_miso(wybrane_kanaly, y, pasek)
        ablacja = analiza_ablacyjna(wybrane_kanaly, y, wynik_miso, pasek)
        idx = 0
        gain_info = {}
        for (nazwa, func_bazowa, n_par, L), _ in zip(wynik_miso["segmenty"], wybrane_kanaly):
            p = wynik_miso["popt"][idx:idx + n_par]
            gain_info[nazwa] = {"K": p[0], "L": L}
            idx += n_par
        print(f"  MISO ({nazwa_okna}): R²={wynik_miso['r2']:.4f} adj R²={wynik_miso['adj_r2']:.4f} "
              f"RMSE={wynik_miso['rmse']:.3f}°C  K_HRT={gain_info['HRT']['K']:.4f}  K_AT={gain_info['AT']['K']:.4f}")
        for a in ablacja:
            print(f"    ablacja bez {a['kanal']:<5}: ΔR²={a['delta_r2']:.4f}")
        pasek.zakoncz()
        return {"nazwa": nazwa_okna, "t": t, "y": y, "wynik_miso": wynik_miso,
                "ablacja": ablacja, "gain_info": gain_info, "n": n}
    except Exception as e:
        pasek.zakoncz()
        print(f"  BŁĄD dopasowania MISO dla okna '{nazwa_okna}': {e}")
        return None


# ==========================================================================
# 8. WYKRESY
# ==========================================================================
def wykres_przesiewania(t, y, u, wyniki, nazwa_kanalu, etykieta_wejscia, plik_png):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                                    gridspec_kw={'height_ratios': [3, 1]})
    ax1.plot(t, y, 'k--', label='Dane pomiarowe (CRT)', alpha=0.4, lw=1.2)

    pokazane = [w for w in wyniki if not np.isnan(w.get("r2", np.nan)) and w["r2"] >= R2_MIN_PLOT]
    colors = plt.cm.tab20(np.linspace(0, 1, max(len(wyniki), 1)))
    for i, w in enumerate(pokazane):
        y_pred = w["func"](u, *w["popt"])
        L_info = f" L={w['L']}" if w["L"] else ""
        ax1.plot(t, y_pred, color=colors[i % len(colors)], lw=1.5,
                  label=f"{w['model']}{L_info} (R²={w['r2']:.3f})")

    ax1.set_title(f"Przesiewanie postaci transmitancji — kanał: {nazwa_kanalu} -> CRT  "
                   f"(pokazane: R² ≥ {R2_MIN_PLOT}, {len(pokazane)}/{len(wyniki)})")
    ax1.legend(loc='lower right', fontsize=7, ncol=2)
    ax1.grid(True, alpha=0.2)
    ax1.set_ylabel("CRT [°C]")

    ax2.plot(t, u, color='steelblue', lw=1.0)
    ax2.fill_between(t, u, color='steelblue', alpha=0.3)
    ax2.set_ylabel(etykieta_wejscia)
    ax2.set_xlabel("Czas")
    ax2.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(plik_png, dpi=150, bbox_inches='tight')
    plt.close(fig)


def wykres_miso(t, y, y_pred, plik_png, tytul):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                                    gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#0f1117')
    for ax in (ax1, ax2):
        ax.set_facecolor('#181c27')
        ax.tick_params(colors='#aab4c8', labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor('#2a3045')

    ax1.plot(t, y, color='#e8eaf6', lw=1.2, alpha=0.75, label='CRT (pomiar)')
    ax1.plot(t, y_pred, color='#4fc3f7', lw=1.5, alpha=0.9, label='CRT (model MISO: HRT+AT)')
    ax1.set_ylabel("CRT [°C]", color='#aab4c8')
    ax1.legend(loc='upper left', fontsize=8, facecolor='#1e2235', labelcolor='white')
    ax1.grid(True, color='#2a3045', alpha=0.5)
    ax1.set_title(tytul, color='#e8eaf6', fontsize=10)

    resid = y - y_pred
    ax2.fill_between(t, resid, color='#ff8a65', alpha=0.5)
    ax2.set_ylabel("Reszta [°C]", color='#aab4c8')
    ax2.grid(True, color='#2a3045', alpha=0.4)

    plt.tight_layout()
    plt.savefig(plik_png, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)


def wykres_wplywu(ablacja, plik_png):
    nazwy = [a["kanal"] for a in ablacja]
    delty = [a["delta_r2"] for a in ablacja]
    colors = plt.cm.tab20(np.linspace(0, 1, len(nazwy)))

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(nazwy, delty, color=colors)
    ax.set_xlabel("ΔR² (spadek dopasowania po usunięciu kanału z modelu MISO CRT=f(HRT,AT))")
    ax.set_title("Wpływ HRT vs AT na CRT")
    ax.grid(True, axis='x', alpha=0.3)
    plt.tight_layout()
    plt.savefig(plik_png, dpi=150, bbox_inches='tight')
    plt.close(fig)


# ==========================================================================
# 9. GŁÓWNY PRZEBIEG
# ==========================================================================
def main():
    print("=" * 90)
    print("IDENTYFIKACJA MISO: CRT = f(HRT, AT) - wpływ szyny ogrzewanej na szynę zimną")
    print("=" * 90)

    df_raw, okna = wczytaj_log(LOG_PATH)
    df = resampluj(df_raw, RESAMPLE_S).dropna().reset_index(drop=True)
    t = df['Timestamp'].to_numpy()
    y = df['CRT'].to_numpy()
    u_hrt = df['HRT'].to_numpy()
    u_at = df['AT'].to_numpy()

    print(f"\nDane: {len(df)} próbek co {RESAMPLE_S}s "
          f"({(t[-1] - t[0]).astype('timedelta64[s]').astype(float) / 86400.0:.1f} dni) - CAŁY log, "
          f"BEZ wykluczania dni testu skokowego (patrz nagłówek pliku - to tu POŻĄDANE).")
    print(f"Zakres HRT: {u_hrt.min():.1f} .. {u_hrt.max():.1f}°C   "
          f"Zakres AT: {u_at.min():.1f} .. {u_at.max():.1f}°C   "
          f"Zakres CRT: {y.min():.1f} .. {y.max():.1f}°C")

    kanaly = {'HRT': u_hrt, 'AT': u_at}

    modele_bez_L, modele_z_L = modele_ciagle()
    total_kroki = len(kanaly) * (len(modele_bez_L) + len(modele_z_L))
    total_kroki += 1  # MISO
    total_kroki += len(kanaly)  # ablacja
    pasek = PasekPostepu(total_kroki, etykieta="Identyfikacja CRT MISO")

    wszystkie_wyniki = {}
    for nazwa, u_k in kanaly.items():
        print(f"\n--- Przesiewanie: kanał {nazwa} -> CRT ---")
        w = przesiej_kanal(nazwa, u_k, y, modele_bez_L, modele_z_L,
                            L_SEARCH_MIN, L_SEARCH_MAX, L_SEARCH_STEP, pasek)
        wszystkie_wyniki[nazwa] = w
        najlepszy = max(w, key=lambda x: x["adj_r2"])
        wykres_przesiewania(t, y, u_k, w, nazwa, nazwa,
                             os.path.join(OUTPUT_DIR, f"przesiewanie_CRT_{nazwa}.png"))
        print(f"\n  Najlepszy dla {nazwa} -> CRT: {najlepszy['model']} "
              f"(adj R²={najlepszy['adj_r2']:.4f}, K={najlepszy['popt'][0]:.4f})")

    pasek.zakoncz()

    # --- tabela zbiorcza przesiewań ---
    wiersze = []
    for nazwa, w_lista in wszystkie_wyniki.items():
        for w in w_lista:
            wiersze.append({"kanal": w["kanal"], "model": w["model"], "typ": w["typ"],
                             "R2": w.get("r2"), "adj_R2": w.get("adj_r2"), "AIC": w.get("aic"),
                             "RMSE": w.get("rmse"), "L": w.get("L"),
                             "parametry": np.round(w["popt"], 4).tolist() if w.get("popt") is not None else None})
    df_tabela = pd.DataFrame(wiersze)

    # --- model MISO wspólny: CRT = y0 + G_HRT(HRT) + G_AT(AT) ---
    wybrane_kanaly = [(nazwa, u_k, max(wszystkie_wyniki[nazwa], key=lambda x: x["adj_r2"]))
                       for nazwa, u_k in kanaly.items()]

    print("\n--- Budowa wspólnego modelu MISO: CRT = y0 + G_HRT(HRT) + G_AT(AT) ---")
    try:
        wynik_miso = dopasuj_miso(wybrane_kanaly, y, pasek)
        wykres_miso(t, y, wynik_miso["y_pred"],
                    os.path.join(OUTPUT_DIR, "model_MISO_CRT.png"),
                    f"Model MISO CRT=f(HRT,AT) — R²={wynik_miso['r2']:.4f}, adj R²={wynik_miso['adj_r2']:.4f}, "
                    f"RMSE={wynik_miso['rmse']:.3f}°C")

        print(f"\nMODEL MISO: R²={wynik_miso['r2']:.4f}  adj R²={wynik_miso['adj_r2']:.4f}  "
              f"RMSE={wynik_miso['rmse']:.4f}°C  AIC={wynik_miso['aic']:.2f}")

        ablacja = analiza_ablacyjna(wybrane_kanaly, y, wynik_miso, pasek)
        wykres_wplywu(ablacja, os.path.join(OUTPUT_DIR, "wplyw_HRT_vs_AT_na_CRT.png"))

        print("\nWPŁYW PARAMETRÓW NA MODEL MISO CRT=f(HRT,AT) (ΔR² po usunięciu kanału, malejąco):")
        for a in ablacja:
            print(f"  {a['kanal']:<6} ΔR²={a['delta_r2']:.4f}  Δadj R²={a['delta_adj_r2']:.4f}")

        # --- odczyt gain'u HRT->CRT wprost z dopasowanego modelu MISO (nie z SISO) -
        # to jest ODPOWIEDŹ na pytanie "ile °C CRT rośnie na 1°C HRT" PRZY
        # RÓWNOCZESNYM uwzględnieniu wpływu AT (SISO K_HRT byłby zawyżony, bo
        # częściowo "łapie" korelację HRT z AT poza oknem testu skokowego).
        idx = 0
        gain_info = {}
        for (nazwa, func_bazowa, n_par, L), (_, _, _) in zip(wynik_miso["segmenty"], wybrane_kanaly):
            p = wynik_miso["popt"][idx:idx + n_par]
            gain_info[nazwa] = {"K": p[0], "n_par": n_par, "L": L}
            idx += n_par
        print("\nGAIN KAŻDEGO KANAŁU WEWNĄTRZ MODELU MISO (K = ile °C CRT w stanie ustalonym na 1°C/1-jednostkę wejścia):")
        for nazwa, info in gain_info.items():
            print(f"  {nazwa:<6} K={info['K']:.4f} °C/°C   L={info['L']}")
        if 'HRT' in gain_info:
            K_hrt = gain_info['HRT']['K']
            print(f"\n>>> ODPOWIEDŹ: przy RÓWNOCZESNYM uwzględnieniu AT, 1°C wzrostu HRT (w stanie")
            print(f">>> ustalonym) odpowiada ZA {K_hrt:.4f}°C wzrostu CRT wg tego modelu MISO.")

        df_ablacja = pd.DataFrame(ablacja)
    except Exception as e:
        print(f"BŁĄD przy budowie modelu MISO: {e}")
        wynik_miso = None
        df_ablacja = pd.DataFrame()
        gain_info = {}

    pasek.zakoncz()

    # ----------------------------------------------------------------------
    # 10. ANALIZA OGRANICZONA DO OKIEN TESTU SKOKOWEGO (na życzenie użytkownika,
    # patrz nagłówek sekcji 7b) - czystszy szacunek K_HRT niż z całego logu,
    # bo tu AT prawie się nie zmienia (80-90 min), a HRT skacze WYŁĄCZNIE od
    # mocy grzania - dekorelacja od AT jest tu największa z całych danych.
    # ----------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("ANALIZA OGRANICZONA DO OKIEN TESTU SKOKOWEGO (osobno per okno + zszyte razem)")
    print("=" * 90)

    wyniki_okien = []
    dfy_okien = []
    for i, (a, b) in enumerate(okna, start=1):
        df_surowe_okno = df_raw[(df_raw['Timestamp'] >= a) & (df_raw['Timestamp'] <= b)].copy()
        df_okno = resampluj(df_surowe_okno, RESAMPLE_S).dropna().reset_index(drop=True)
        dfy_okien.append(df_okno)
        wynik = analizuj_okno_skokowe(f"okno_{i}_{a.date()}", df_okno)
        if wynik is not None:
            wyniki_okien.append(wynik)
            wykres_miso(wynik["t"], wynik["y"], wynik["wynik_miso"]["y_pred"],
                        os.path.join(OUTPUT_DIR, f"model_MISO_CRT_{wynik['nazwa']}.png"),
                        f"Model MISO CRT=f(HRT,AT) — TYLKO {wynik['nazwa']} — "
                        f"R²={wynik['wynik_miso']['r2']:.4f}, K_HRT={wynik['gain_info']['HRT']['K']:.4f}")

    # --- wariant "zszyty": oba okna połączone w jedną serię (WIĘCEJ próbek =
    # bardziej stabilne dopasowanie, kosztem jednej sztucznej nieciągłości
    # czasu na styku okien - ten sam, udokumentowany kompromis co w
    # identyfikacja_miso.py przy łączeniu dni bez testu skokowego). ---
    if len(dfy_okien) >= 2:
        df_zszyte = pd.concat(dfy_okien, ignore_index=True)
        wynik_zszyty = analizuj_okno_skokowe("oba_okna_zszyte", df_zszyte)
        if wynik_zszyty is not None:
            wyniki_okien.append(wynik_zszyty)
            wykres_miso(np.arange(len(df_zszyte)), wynik_zszyty["y"], wynik_zszyty["wynik_miso"]["y_pred"],
                        os.path.join(OUTPUT_DIR, "model_MISO_CRT_oba_okna_zszyte.png"),
                        f"Model MISO CRT=f(HRT,AT) — oba okna ZSZYTE (uwaga: 1 sztuczna nieciągłość na styku) — "
                        f"R²={wynik_zszyty['wynik_miso']['r2']:.4f}, K_HRT={wynik_zszyty['gain_info']['HRT']['K']:.4f}")

    print("\n" + "-" * 90)
    print("PODSUMOWANIE: K_HRT (ile °C CRT na 1°C HRT, PRZY RÓWNOCZESNYM AT) wg wariantu analizy:")
    print(f"  {'Cały log (21 dni)':<28} K_HRT={gain_info.get('HRT', {}).get('K', float('nan')):+.4f}  "
          f"(zdominowany przez 21 dni bez pewnego grzania - patrz ostrzeżenie wyżej)")
    for w in wyniki_okien:
        print(f"  {w['nazwa']:<28} K_HRT={w['gain_info']['HRT']['K']:+.4f}  "
              f"(n={w['n']} próbek, R²={w['wynik_miso']['r2']:.4f}, ΔR²_HRT="
              f"{next(a['delta_r2'] for a in w['ablacja'] if a['kanal'] == 'HRT'):.4f})")
    print("-" * 90)

    df_okna_tabela = pd.DataFrame([
        {"wariant": w["nazwa"], "n_probek": w["n"],
         "K_HRT": w["gain_info"]["HRT"]["K"], "K_AT": w["gain_info"]["AT"]["K"],
         "R2": w["wynik_miso"]["r2"], "adj_R2": w["wynik_miso"]["adj_r2"], "RMSE": w["wynik_miso"]["rmse"],
         "delta_R2_HRT": next(a["delta_r2"] for a in w["ablacja"] if a["kanal"] == "HRT"),
         "delta_R2_AT": next(a["delta_r2"] for a in w["ablacja"] if a["kanal"] == "AT")}
        for w in wyniki_okien
    ])

    # --- zapis wyników ---
    sciezka_csv = os.path.join(OUTPUT_DIR, "wyniki_identyfikacji_crt_miso.csv")
    df_tabela.to_csv(sciezka_csv, index=False, encoding='utf-8-sig')
    sciezka_ablacja_csv = os.path.join(OUTPUT_DIR, "wplyw_HRT_vs_AT_na_CRT.csv")
    df_ablacja.to_csv(sciezka_ablacja_csv, index=False, encoding='utf-8-sig')
    sciezka_okna_csv = os.path.join(OUTPUT_DIR, "wplyw_HRT_na_CRT_okna_skokowe.csv")
    df_okna_tabela.to_csv(sciezka_okna_csv, index=False, encoding='utf-8-sig')

    try:
        sciezka_xlsx = os.path.join(OUTPUT_DIR, "wyniki_identyfikacji_crt_miso.xlsx")
        with pd.ExcelWriter(sciezka_xlsx, engine='openpyxl') as writer:
            df_tabela.to_excel(writer, sheet_name='Przesiewanie_SISO', index=False)
            df_ablacja.to_excel(writer, sheet_name='Wplyw_HRT_vs_AT', index=False)
            df_okna_tabela.to_excel(writer, sheet_name='MISO_okna_skokowe', index=False)
            if wynik_miso is not None:
                pd.DataFrame({
                    'metryka': ['R2', 'adj_R2', 'RMSE', 'MAE', 'AIC'] + [f'K_{n}' for n in gain_info],
                    'wartosc': [wynik_miso['r2'], wynik_miso['adj_r2'], wynik_miso['rmse'],
                                wynik_miso['mae'], wynik_miso['aic']] + [gain_info[n]['K'] for n in gain_info],
                }).to_excel(writer, sheet_name='Model_MISO_podsumowanie', index=False)
        print(f"\nZapisano Excel: {sciezka_xlsx}")
    except ImportError:
        print("\nUWAGA: openpyxl niedostępny - zapisano tylko CSV (bez .xlsx).")

    print(f"Zapisano tabelę: {sciezka_csv}")
    print(f"Zapisano wpływ HRT vs AT: {sciezka_ablacja_csv}")
    print(f"Zapisano analizę okien skokowych: {sciezka_okna_csv}")
    print(f"Wykresy zapisane w: {OUTPUT_DIR}")
    print("\nGOTOWE.")


if __name__ == "__main__":
    main()
