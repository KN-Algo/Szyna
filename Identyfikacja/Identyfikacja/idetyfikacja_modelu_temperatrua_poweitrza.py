import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from scipy.optimize import curve_fit
from scipy import signal

# ==================================================================================
# KONFIGURACJA
# ==================================================================================

FILE_PATH    = 'D:\\Pulpit\\KN ALGO\\Szyna\\Nowe_dane\\dane_bez_skoku.csv'
R2_MIN_PLOT  = 0.975   # próg R² do wyświetlenia na wykresie
WINDOW_SIZE  = 7200  # liczba próbek widocznych naraz na wykresie

# Iteracyjne szukanie opóźnienia
L_SEARCH_MIN  = 0    # [próbki]
L_SEARCH_MAX  = 360  # [próbki]  360 × 10s = 1h
L_SEARCH_STEP = 5    # [próbki]

INF = 50_000

# ==================================================================================
# FUNKCJE BAZOWE
# ==================================================================================

def apply_delay(u, L):
    L_int = int(max(0, round(L)))
    if L_int == 0:
        return u
    out = np.zeros_like(u)
    if L_int < len(u):
        out[L_int:] = u[:-L_int]
    return out

def get_sim(num, den, u):
    den = list(den)
    den[0] = max(abs(den[0]), 1e-10)
    sys_c = signal.TransferFunction(num, den)
    sys_d = sys_c.to_discrete(dt=10, method='gbt', alpha=0.5)  # dt=10s
    return signal.lfilter(sys_d.num, sys_d.den, u)

def build_poly(roots_T):
    poly = np.array([1.0])
    for T in roots_T:
        poly = np.polymul(poly, [max(T, 1e-6), 1.0])
    return poly.tolist()

# ==================================================================================
# METRYKI
# ==================================================================================

def compute_metrics(y_true, y_pred, n_params):
    n      = len(y_true)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2     = 1 - ss_res / (ss_tot + 1e-30)
    adj_r2 = 1 - (1 - r2) * (n - 1) / max(n - n_params - 1, 1)
    mse    = max(ss_res / n, 1e-30)
    aic    = n * np.log(mse) + 2 * n_params
    rmse   = np.sqrt(mse)
    mae    = np.mean(np.abs(y_true - y_pred))
    return {"r2": r2, "adj_r2": adj_r2, "aic": aic, "rmse": rmse, "mae": mae}

# ==================================================================================
# DEFINICJE MODELI
# ==================================================================================

# --- modele standardowe ---
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

def m_FOD(u, K, T1, L):
    return m_FO(apply_delay(u, L), K, T1)

def m_FOD_Z(u, K, T1, Tz, L):
    return m_FO_Z(apply_delay(u, L), K, T1, Tz)

def m_SOD(u, K, T1, T2, L):
    return m_SO(apply_delay(u, L), K, T1, T2)

def m_SOD_Z(u, K, T1, T2, Tz, L):
    return m_SO_Z(apply_delay(u, L), K, T1, T2, Tz)

def m_TOD(u, K, T1, T2, T3, L):
    return m_TO(apply_delay(u, L), K, T1, T2, T3)

# --- modele pogodowe (duże T, L w próbkach) ---
def m_W_FO(u, K, T1):
    return get_sim([K], [T1, 1], u)

def m_W_FOD(u, K, T1, L):
    return m_W_FO(apply_delay(u, L), K, T1)

def m_W_SO(u, K, T1, T2):
    return get_sim([K], build_poly([T1, T2]), u)

def m_W_SOD(u, K, T1, T2, L):
    return m_W_SO(apply_delay(u, L), K, T1, T2)

# ==================================================================================
# DEFINICJE LIST MODELI
# ==================================================================================

MODELS_NO_DELAY = [
    # --- modele całkujące / z integratorem (wolna termika) ---
    {
        "name":   "I",
        "func":   lambda u, K: get_sim([K], [1, 0], u),
        "p0":     [0.01],
        "bounds": ([0], [10]),
    },
    {
        "name":   "FO_sym",
        "func":   lambda u, K, T1: get_sim([K], [T1, 1], u),
        "p0":     [0.95, 600],
        "bounds": ([0.5, 10], [1.5, 200_000]),
    },
    # --- modele różniczkujące (reakcja na zmiany) ---
    {
        "name":   "PD",
        "func":   lambda u, K, Td: get_sim([K * Td, K], [1], u),
        "p0":     [1.0, 60],
        "bounds": ([0.1, 1], [5.0, 10_000]),
    },
    # --- FO z dużą stałą czasową i swobodnym K blisko 1 ---
    {
        "name":   "FO_big",
        "func":   lambda u, K, T1: get_sim([K], [T1, 1], u),
        "p0":     [1.0, 10_000],
        "bounds": ([0.5, 500], [2.0, 500_000]),
    },
    {
        "name":   "SO_big",
        "func":   lambda u, K, T1, T2: get_sim([K], build_poly([T1, T2]), u),
        "p0":     [1.0, 8_000, 2_000],
        "bounds": ([0.5, 100, 100], [2.0, 500_000, 500_000]),
    },
    {
        "name":   "TO_big",
        "func":   lambda u, K, T1, T2, T3: get_sim([K], build_poly([T1, T2, T3]), u),
        "p0":     [1.0, 6_000, 2_000, 500],
        "bounds": ([0.5, 100, 100, 10], [2.0, 500_000, 500_000, 100_000]),
    },
    # --- modele ze wzmocnieniem bliskim 1 i zerem ---
    {
        "name":   "FO_Z_sym",
        "func":   lambda u, K, T1, Tz: get_sim([K * Tz, K], [T1, 1], u),
        "p0":     [1.0, 5_000, 500],
        "bounds": ([0.5, 100, -100_000], [1.5, 500_000, 100_000]),
    },
    {
        "name":   "SO_Z_big",
        "func":   lambda u, K, T1, T2, Tz: get_sim([K * Tz, K], build_poly([T1, T2]), u),
        "p0":     [1.0, 8_000, 2_000, 500],
        "bounds": ([0.5, 100, 100, -100_000], [2.0, 500_000, 500_000, 100_000]),
    },
]

MODELS_WITH_DELAY = [
    # --- wersje z opóźnieniem dla modeli "big" ---
    {
        "name":          "FOD_big",
        "func_no_L":     lambda u, K, T1: get_sim([K], [T1, 1], u),
        "func_with_L":   lambda u, K, T1, L: get_sim([K], [T1, 1], apply_delay(u, L)),
        "p0":            [1.0, 10_000],
        "bounds_no_L":   ([0.5, 500],          [2.0, 500_000]),
        "bounds_with_L": ([0.5, 500,   0],     [2.0, 500_000, L_SEARCH_MAX]),
    },
    {
        "name":          "SOD_big",
        "func_no_L":     lambda u, K, T1, T2: get_sim([K], build_poly([T1, T2]), u),
        "func_with_L":   lambda u, K, T1, T2, L: get_sim([K], build_poly([T1, T2]), apply_delay(u, L)),
        "p0":            [1.0, 8_000, 2_000],
        "bounds_no_L":   ([0.5, 100, 100],         [2.0, 500_000, 500_000]),
        "bounds_with_L": ([0.5, 100, 100,   0],    [2.0, 500_000, 500_000, L_SEARCH_MAX]),
    },
    {
        "name":          "TOD_big",
        "func_no_L":     lambda u, K, T1, T2, T3: get_sim([K], build_poly([T1, T2, T3]), u),
        "func_with_L":   lambda u, K, T1, T2, T3, L: get_sim([K], build_poly([T1, T2, T3]), apply_delay(u, L)),
        "p0":            [1.0, 6_000, 2_000, 500],
        "bounds_no_L":   ([0.5, 100, 100, 10],         [2.0, 500_000, 500_000, 100_000]),
        "bounds_with_L": ([0.5, 100, 100, 10,   0],    [2.0, 500_000, 500_000, 100_000, L_SEARCH_MAX]),
    },
    {
        "name":          "FOD_Z_big",
        "func_no_L":     lambda u, K, T1, Tz: get_sim([K * Tz, K], [T1, 1], u),
        "func_with_L":   lambda u, K, T1, Tz, L: get_sim([K * Tz, K], [T1, 1], apply_delay(u, L)),
        "p0":            [1.0, 5_000, 500],
        "bounds_no_L":   ([0.5, 100, -100_000],          [1.5, 500_000, 100_000]),
        "bounds_with_L": ([0.5, 100, -100_000,  0],      [1.5, 500_000, 100_000, L_SEARCH_MAX]),
    },
    {
        "name":          "SOD_Z_big",
        "func_no_L":     lambda u, K, T1, T2, Tz: get_sim([K * Tz, K], build_poly([T1, T2]), u),
        "func_with_L":   lambda u, K, T1, T2, Tz, L: get_sim([K * Tz, K], build_poly([T1, T2]), apply_delay(u, L)),
        "p0":            [1.0, 8_000, 2_000, 500],
        "bounds_no_L":   ([0.5, 100, 100, -100_000],          [2.0, 500_000, 500_000, 100_000]),
        "bounds_with_L": ([0.5, 100, 100, -100_000,  0],      [2.0, 500_000, 500_000, 100_000, L_SEARCH_MAX]),
    },
]

# Modele pogodowe z L jako zwykłym parametrem curve_fit (bez iteracji)
MODELS_WEATHER_DIRECT = [
    {
        "name":   "W_FOD_direct",
        "func":   m_W_FOD,
        "p0":     [1.0, 5000, 60],
        "bounds": ([0.1, 100,   0], [2.0, 100_000, L_SEARCH_MAX]),
    },
    {
        "name":   "W_SOD_direct",
        "func":   m_W_SOD,
        "p0":     [1.0, 5000, 1000, 60],
        "bounds": ([0.1, 100,  100,  0], [2.0, 100_000, 100_000, L_SEARCH_MAX]),
    },
]

# ==================================================================================
# ITERACYJNE SZUKANIE OPÓŹNIENIA
# ==================================================================================

def find_best_delay(u, y, m):
    best_adj_r2 = -np.inf
    best_L      = 0
    best_popt   = None

    print(f"  [{m['name']}] szukanie L w [{L_SEARCH_MIN}..{L_SEARCH_MAX}] "
          f"krok={L_SEARCH_STEP} ...", end=" ", flush=True)

    for L_try in range(L_SEARCH_MIN, L_SEARCH_MAX + 1, L_SEARCH_STEP):
        u_shifted = apply_delay(u, L_try)
        try:
            popt, _ = curve_fit(
                m["func_no_L"], u_shifted, y,
                p0=m["p0"],
                bounds=m["bounds_no_L"],
                maxfev=10_000,
                ftol=1e-8, xtol=1e-8,
            )
            y_pred = m["func_no_L"](u_shifted, *popt)
            met    = compute_metrics(y, y_pred, len(popt) + 1)
            if met["adj_r2"] > best_adj_r2:
                best_adj_r2 = met["adj_r2"]
                best_L      = L_try
                best_popt   = popt
        except Exception:
            continue

    print(f"L* = {best_L}  (adj R² = {best_adj_r2:.4f})")
    return best_L, best_popt

# ==================================================================================
# WCZYTANIE DANYCH
# ==================================================================================

def load_data(file_path):
    df = pd.read_csv(file_path, sep=';')

    def clean(col):
        return pd.to_numeric(col.astype(str).str.replace(',', '.'), errors='coerce')

    df['Timestamp']         = pd.to_datetime(df['Timestamp'])
    df['HRT_temp_grzana']   = clean(df['HRT_temp_grzana'])
    df['AT_temp_powietrza'] = clean(df['AT_temp_powietrza'])

    df = df.dropna(subset=['HRT_temp_grzana', 'AT_temp_powietrza'])
    df = df.sort_values('Timestamp').reset_index(drop=True)

    y = df['HRT_temp_grzana'].values
    u = df['AT_temp_powietrza'].values
    t = df['Timestamp'].values

    print(f"Wczytano {len(y)} próbek")
    print(f"Okres: {t[0]}  →  {t[-1]}")
    return t, u, y


def clean_signals(u_raw, y_raw, u_max_valid=30.0, u_min_valid=-30.0, u_clip=(-40, 50), y_clip=(-30, 80)):
    """
    Czyści sygnały:
    1. Próbki AT > u_max_valid lub < u_min_valid → zastąpione interpolacją
       (szuka poprzedniej i następnej dobrej próbki)
    2. Clip do fizycznego zakresu jako ostatnia siatka bezpieczeństwa
    3. Medianowy filtr wygładzający drobny szum AT
    """
    u = u_raw.copy().astype(float)
    y = y_raw.copy().astype(float)

    # ── 1. Oznacz złe próbki AT jako NaN ────────────────────────────────────
    bad_mask = (u > u_max_valid) | (u < u_min_valid)
    n_bad = bad_mask.sum()
    u[bad_mask] = np.nan
    print(f"  Złe próbki AT (poza [{u_min_valid}, {u_max_valid}]°C): {n_bad} → interpolacja")

    # ── 2. Interpolacja: dla każdego NaN szukaj poprzedniej i następnej dobrej ──
    idx = np.arange(len(u))
    valid = ~np.isnan(u)
    if valid.sum() > 2:
        u = np.interp(idx, idx[valid], u[valid])
    else:
        print("  UWAGA: za mało dobrych próbek AT do interpolacji!")

    # ── 3. Clip jako siatka bezpieczeństwa ──────────────────────────────────
    n_u_out = np.sum((u < u_clip[0]) | (u > u_clip[1]))
    n_y_out = np.sum((y < y_clip[0]) | (y > y_clip[1]))
    u = np.clip(u, u_clip[0], u_clip[1])
    y = np.clip(y, y_clip[0], y_clip[1])
    if n_u_out > 0:
        print(f"  Clip AT:  {n_u_out} próbek poza [{u_clip[0]}, {u_clip[1]}]°C")
    if n_y_out > 0:
        print(f"  Clip HRT: {n_y_out} próbek poza [{y_clip[0]}, {y_clip[1]}]°C")

    # ── 4. Lekkie wygładzenie medianoowe AT ─────────────────────────────────
    from scipy.signal import medfilt
    u = medfilt(u, kernel_size=5)

    print(f"  Po czyszczeniu: AT ∈ [{u.min():.2f}, {u.max():.2f}], "
          f"HRT ∈ [{y.min():.2f}, {y.max():.2f}]")
    return u, y

# ==================================================================================
# PREPROCESSING — praca na przyrostach względem punktu pracy
# ==================================================================================

def preprocess_signals(u_raw, y_raw, mode='diff'):
    """
    Przekształca sygnały do postaci nadającej się dla identyfikacji transmitancji.
    
    mode='offset'  → odejmuje pierwszą wartość (praca wokół punktu pracy)
    mode='mean'    → odejmuje średnią (centrowanie)
    mode='diff'    → różniczkowanie (przyrosty między próbkami)
    mode='raw'     → bez zmian (do testów)
    """
    if mode == 'offset':
        u = u_raw - u_raw[0]
        y = y_raw - y_raw[0]
    elif mode == 'mean':
        u = u_raw - np.mean(u_raw)
        y = y_raw - np.mean(y_raw)
    elif mode == 'diff':
        u = np.diff(u_raw, prepend=u_raw[0])
        y = np.diff(y_raw, prepend=y_raw[0])
    else:
        u, y = u_raw.copy(), y_raw.copy()

    print(f"  Preprocessing '{mode}': u ∈ [{u.min():.2f}, {u.max():.2f}], "
          f"y ∈ [{y.min():.2f}, {y.max():.2f}]")
    return u, y


def compute_correlation(u, y, max_lag_samples=720):
    """
    Wyznacza korelację krzyżową AT↔HRT i szacuje opóźnienie.
    max_lag_samples: maksymalne opóźnienie do przeszukania (domyślnie 720 × 10s = 2h)
    """
    # normalizacja
    u_n = (u - np.mean(u)) / (np.std(u) + 1e-10)
    y_n = (y - np.mean(y)) / (np.std(y) + 1e-10)

    # korelacja krzyżowa (pełna)
    corr    = np.correlate(y_n, u_n, mode='full')
    lags    = np.arange(-len(u_n) + 1, len(u_n))
    corr_n  = corr / len(u_n)   # normalizacja do [-1, 1]

    # szukamy najlepszego opóźnienia w przedziale [0, max_lag_samples]
    mid     = len(u_n) - 1
    lag_idx = np.arange(mid, mid + max_lag_samples + 1)
    lag_idx = lag_idx[lag_idx < len(corr_n)]
    best_i  = lag_idx[np.argmax(np.abs(corr_n[lag_idx]))]
    best_L  = lags[best_i]
    best_r  = corr_n[best_i]

    # korelacja Pearsona (L=0)
    from scipy.stats import pearsonr
    r_pearson, p_val = pearsonr(u, y)

    print(f"\n  ── Analiza korelacji AT ↔ HRT ──────────────────────────────")
    print(f"  Korelacja Pearsona (L=0)  : r = {r_pearson:.4f}  (p = {p_val:.2e})")
    print(f"  Najlepsza korelacja krzyż.: r = {best_r:.4f}  przy L = {best_L} próbek "
          f"= {best_L * 10}s = {best_L * 10 / 60:.1f} min")
    print(f"  ────────────────────────────────────────────────────────────\n")

    return corr_n, lags, best_L, best_r, r_pearson



# ==================================================================================
# IDENTYFIKACJA — wspólny silnik
# ==================================================================================

def _fit_direct(m, u, y):
    """Dopasowanie bezpośrednie (L jako zwykły parametr lub brak L)."""
    popt, _ = curve_fit(
        m["func"], u, y,
        p0=m["p0"],
        bounds=m["bounds"],
        maxfev=30_000,
        ftol=1e-9, xtol=1e-9,
    )
    return popt

def _fit_with_iter_delay(m, u, y):
    """Iteracyjne L*, potem dokładny curve_fit."""
    L_best, popt_no_L = find_best_delay(u, y, m)
    if popt_no_L is None:
        raise RuntimeError("brak zbieżności dla każdego L")
    p0_full = list(popt_no_L) + [float(L_best)]
    blo     = list(m["bounds_with_L"][0])
    bhi     = list(m["bounds_with_L"][1])
    popt, _ = curve_fit(
        m["func_with_L"], u, y,
        p0=p0_full,
        bounds=(blo, bhi),
        maxfev=30_000,
        ftol=1e-9, xtol=1e-9,
    )
    return popt, L_best


def run_identification(u, y, y_offset=0.0):
    results = []

    header = (f"{'MODEL':<16} | {'R²':>7} | {'adj R²':>7} | "
              f"{'RMSE':>7} | {'MAE':>7} | {'AIC':>12} | {'TYP':<10} | PARAMETRY")
    print("\n" + header)
    print("-" * 130)

    # ── 1. Modele BEZ opóźnienia (+ W_FO, W_SO) ─────────────────────────────
    print("\n[ Modele bez opóźnienia ]\n")
    for m in MODELS_NO_DELAY:
        try:
            popt = _fit_direct(m, u, y)
            y_pred = m["func"](u, *popt)
            met    = compute_metrics(y, y_pred, len(popt))
            results.append({"name": m["name"], "func": m["func"],
                             "popt": popt, "y_pred": y_pred + y_offset,
                             "L_best": None, "typ": "brak L", **met})
            flag = "" if met["r2"] >= R2_MIN_PLOT else "  ←"
            print(f"{m['name']:<16} | {met['r2']:7.4f} | {met['adj_r2']:7.4f} | "
                  f"{met['rmse']:7.4f} | {met['mae']:7.4f} | {met['aic']:12.2f} | "
                  f"{'brak L':<10} | {np.round(popt, 4)}{flag}")
        except Exception as e:
            print(f"{m['name']:<16} | BŁĄD: {e}")

    # ── 2. Modele Z opóźnieniem — iteracyjne L ───────────────────────────────
    print("\n[ Modele z opóźnieniem — iteracyjne L ]\n")
    for m in MODELS_WITH_DELAY:
        try:
            popt, L_best = _fit_with_iter_delay(m, u, y)
            y_pred = m["func_with_L"](u, *popt)
            met    = compute_metrics(y, y_pred, len(popt))
            results.append({"name": m["name"], "func": m["func_with_L"],
                             "popt": popt, "y_pred": y_pred + y_offset,
                             "L_best": L_best, "typ": "L iter", **met})
            flag = "" if met["r2"] >= R2_MIN_PLOT else "  ←"
            print(f"{m['name']:<16} | {met['r2']:7.4f} | {met['adj_r2']:7.4f} | "
                  f"{met['rmse']:7.4f} | {met['mae']:7.4f} | {met['aic']:12.2f} | "
                  f"{'L iter':<10} | {np.round(popt, 4)}  "
                  f"[L_iter={L_best} = {L_best*10}s]{flag}")
        except Exception as e:
            print(f"{m['name']:<16} | BŁĄD: {e}")

    # ── 3. Modele pogodowe — L bezpośredni (curve_fit) ───────────────────────
    print("\n[ Modele pogodowe — L bezpośredni (curve_fit) ]\n")
    for m in MODELS_WEATHER_DIRECT:
        try:
            popt = _fit_direct(m, u, y)
            y_pred = m["func"](u, *popt)
            met    = compute_metrics(y, y_pred, len(popt))
            # L jest ostatnim parametrem
            L_val  = popt[-1]
            results.append({"name": m["name"], "func": m["func"],
                             "popt": popt, "y_pred": y_pred + y_offset,
                             "L_best": int(round(L_val)), "typ": "L direct", **met})
            flag = "" if met["r2"] >= R2_MIN_PLOT else "  ←"
            print(f"{m['name']:<16} | {met['r2']:7.4f} | {met['adj_r2']:7.4f} | "
                  f"{met['rmse']:7.4f} | {met['mae']:7.4f} | {met['aic']:12.2f} | "
                  f"{'L direct':<10} | {np.round(popt, 4)}  "
                  f"[L={L_val:.1f}próbek = {L_val*10:.0f}s]{flag}")
        except Exception as e:
            print(f"{m['name']:<16} | BŁĄD: {e}")

    # ── Podsumowanie ──────────────────────────────────────────────────────────
    if results:
        best = max(results, key=lambda x: x["adj_r2"])
        print("\n" + "=" * 95)
        print(f"  NAJLEPSZY MODEL : {best['name']}  [{best['typ']}]")
        print(f"  R²              : {best['r2']:.4f}")
        print(f"  adj R²          : {best['adj_r2']:.4f}")
        print(f"  RMSE            : {best['rmse']:.4f} °C")
        print(f"  MAE             : {best['mae']:.4f} °C")
        print(f"  AIC             : {best['aic']:.2f}")
        if best["L_best"] is not None:
            print(f"  Opóźnienie L    : {best['L_best']} próbek = {best['L_best']*10} s")
        print(f"  PARAMETRY       : {np.round(best['popt'], 4)}")
        print("=" * 95)

        # Tabela porównawcza pogodowych
        weather_res = [r for r in results if r["name"].startswith("W_")]
        if weather_res:
            print("\n  Porównanie modeli pogodowych:")
            print(f"  {'MODEL':<16} | {'TYP':<10} | {'R²':>7} | {'adj R²':>7} | {'RMSE':>7} | L [próbki]")
            print("  " + "-" * 68)
            for r in weather_res:
                L_str = f"{r['L_best']}" if r["L_best"] is not None else "—"
                print(f"  {r['name']:<16} | {r['typ']:<10} | {r['r2']:7.4f} | "
                      f"{r['adj_r2']:7.4f} | {r['rmse']:7.4f} | {L_str}")

    return results

# ==================================================================================
# WYKRES Z SUWAKIEM
# ==================================================================================

def plot_results(t, u, y, results):
    n     = len(t)
    t_num = np.arange(n)

    total  = len(MODELS_NO_DELAY) + len(MODELS_WITH_DELAY) + len(MODELS_WEATHER_DIRECT)
    colors = plt.cm.tab20(np.linspace(0, 1, max(total, 1)))

    fig = plt.figure(figsize=(18, 9))
    fig.patch.set_facecolor('#0f1117')

    ax_main  = fig.add_axes([0.05, 0.30, 0.92, 0.62])
    ax_input = fig.add_axes([0.05, 0.17, 0.92, 0.10], sharex=ax_main)
    ax_slide = fig.add_axes([0.05, 0.08, 0.82, 0.04])
    ax_btn_l = fig.add_axes([0.88, 0.08, 0.04, 0.04])
    ax_btn_r = fig.add_axes([0.93, 0.08, 0.04, 0.04])

    for ax in [ax_main, ax_input]:
        ax.set_facecolor('#181c27')
        ax.tick_params(colors='#aab4c8', labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor('#2a3045')

    ax_main.plot(t_num, y, color='#e8eaf6', lw=1.2, alpha=0.7,
                 label='HRT (pomiar)', zorder=5)

    plotted = []
    for i, r in enumerate(results):
        if r["r2"] < R2_MIN_PLOT:
            continue
        L_info = ""
        if r["L_best"] is not None:
            L_info = f" L={r['L_best']}próbek"
        lbl = (f"{r['name']}{L_info} [{r['typ']}]  "
               f"R²={r['r2']:.4f}  RMSE={r['rmse']:.3f}°C")
        ax_main.plot(t_num, r["y_pred"], color=colors[i % len(colors)],
                     lw=1.5, alpha=0.85, label=lbl, zorder=4)
        plotted.append(r)

    ax_main.set_ylabel("Temperatura HRT [°C]", color='#aab4c8', fontsize=9)
    ax_main.legend(loc='upper left', fontsize=7.5, facecolor='#1e2235',
                   labelcolor='white', framealpha=0.85, ncol=2)
    ax_main.grid(True, color='#2a3045', alpha=0.6, lw=0.6)

    ax_input.fill_between(t_num, u, color='#4fc3f7', alpha=0.35)
    ax_input.plot(t_num, u, color='#4fc3f7', lw=0.8, alpha=0.7)
    ax_input.set_ylabel("AT [°C]", color='#aab4c8', fontsize=9)
    ax_input.grid(True, color='#2a3045', alpha=0.4, lw=0.5)

    W = min(WINDOW_SIZE, n)
    ax_main.set_xlim(0, W)
    ax_main.set_ylim(np.nanmin(y) - 1, np.nanmax(y) + 1)

    def format_xaxis(ax):
        ticks  = ax.get_xticks()
        idx    = np.clip(ticks.astype(int), 0, n - 1)
        labels = [pd.Timestamp(t[i]).strftime('%d.%m %H:%M') for i in idx]
        ax.set_xticklabels(labels, rotation=25, ha='right',
                           fontsize=7.5, color='#aab4c8')

    format_xaxis(ax_input)

    ax_main.set_title(
        f"Identyfikacja transmitancji  HRT ← AT  |  próg R² = {R2_MIN_PLOT}  |  "
        f"modele widoczne: {len(plotted)}/{len(results)}",
        color='#e8eaf6', fontsize=10, pad=8
    )

    slider_max = max(n - W, 1)
    slider = Slider(
        ax_slide, 'Czas →', 0, slider_max,
        valinit=0, valstep=max(1, W // 200),
        color='#4fc3f7', track_color='#2a3045'
    )
    ax_slide.set_facecolor('#181c27')
    slider.label.set_color('#aab4c8')
    slider.valtext.set_color('#4fc3f7')

    def update(val):
        x0 = int(slider.val)
        ax_main.set_xlim(x0, x0 + W)
        format_xaxis(ax_input)
        fig.canvas.draw_idle()

    slider.on_changed(update)

    STEP  = W // 4
    btn_l = Button(ax_btn_l, '◀', color='#2a3045', hovercolor='#3a4060')
    btn_r = Button(ax_btn_r, '▶', color='#2a3045', hovercolor='#3a4060')
    btn_l.label.set_color('#e8eaf6')
    btn_r.label.set_color('#e8eaf6')

    def go_left(event):
        slider.set_val(max(0, slider.val - STEP))

    def go_right(event):
        slider.set_val(min(slider_max, slider.val + STEP))

    btn_l.on_clicked(go_left)
    btn_r.on_clicked(go_right)

    def on_scroll(event):
        if event.inaxes in [ax_main, ax_input]:
            delta   = -(W // 8) if event.button == 'up' else (W // 8)
            new_val = np.clip(slider.val + delta, 0, slider_max)
            slider.set_val(new_val)

    fig.canvas.mpl_connect('scroll_event', on_scroll)

    plt.savefig("transmitancja_HRT_AT.png", dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    print("\nWykres zapisany jako: transmitancja_HRT_AT.png")
    plt.show()

# ==================================================================================
# MAIN
# ==================================================================================

if __name__ == "__main__":
    t, u_raw, y_raw = load_data(FILE_PATH)

    # ── Analiza korelacji na surowych danych ─────────────────────────────────
    corr, lags, L_corr, r_corr, r_pearson = compute_correlation(u_raw, y_raw)

    print("\n── Czyszczenie danych ──────────────────────────────────────────")
    u_raw, y_raw = clean_signals(u_raw, y_raw)

    # ── Wybierz tryb preprocessingu ─────────────────────────────────────────
    # Zalecana kolejność prób: 'mean' → 'offset' → 'diff' → 'raw'
    PREPROCESS_MODE = 'mean'   # ← zmień jeśli wyniki nadal złe

    u, y = preprocess_signals(u_raw, y_raw, mode=PREPROCESS_MODE)
    y_offset = np.mean(y_raw) if PREPROCESS_MODE == 'mean' else (y_raw[0] if PREPROCESS_MODE == 'offset' else 0.0)
    u_offset = np.mean(u_raw) if PREPROCESS_MODE == 'mean' else (u_raw[0] if PREPROCESS_MODE == 'offset' else 0.0)

    # Zaktualizuj L_SEARCH_MAX na podstawie korelacji krzyżowej
    if L_corr > 0:
        L_SEARCH_MAX = max(L_SEARCH_MAX, L_corr + 50)
        print(f"  → Korelacja sugeruje opóźnienie {L_corr} próbek. "
              f"L_SEARCH_MAX zaktualizowany na {L_SEARCH_MAX}.")

    results  = run_identification(u, y,y_offset=y_offset)
    plot_results(t, u_raw, y_raw, results)   # wykres zawsze na surowych danych