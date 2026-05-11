import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from sklearn.metrics import r2_score
from scipy import signal

# ==========================================
# 1. PRÓG WYŚWIETLANIA NA WYKRESIE
# ==========================================
R2_MIN_PLOT = 0.3  # <-- zmień według potrzeb

# ==========================================
# 2. ZAKRES ITERACYJNEGO SZUKANIA OPÓŹNIENIA
# ==========================================
L_SEARCH_MIN  = 0      # minimalne opóźnienie [próbki]
L_SEARCH_MAX  = 500    # maksymalne opóźnienie [próbki]
L_SEARCH_STEP = 5      # krok przeszukiwania [próbki]

# ==========================================
# 3. FUNKCJE BAZOWE
# ==========================================
def apply_delay(u, L_sec):
    L_int = int(max(0, round(L_sec)))
    if L_int == 0:
        return u
    u_delayed = np.zeros_like(u)
    if L_int < len(u):
        u_delayed[L_int:] = u[:-L_int]
    return u_delayed

def get_sim(num, den, u):
    den = [max(abs(d), 1e-10) if i == 0 else d for i, d in enumerate(den)]
    sys_d = signal.TransferFunction(num, den).to_discrete(dt=1, method='gbt', alpha=0.5)
    y = signal.lfilter(sys_d.num, sys_d.den, u)
    return y

def build_poly(roots_T):
    poly = np.array([1.0])
    for T in roots_T:
        poly = np.polymul(poly, [max(T, 1e-6), 1.0])
    return poly.tolist()

# ==========================================
# 4. METRYKI
# ==========================================
def compute_metrics(y_true, y_pred, n_params):
    n = len(y_true)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - ss_res / ss_tot
    adj_r2 = 1 - (1 - r2) * (n - 1) / (n - n_params - 1)
    mse = ss_res / n
    if mse <= 0:
        mse = 1e-30
    aic = n * np.log(mse) + 2 * n_params
    return r2, adj_r2, aic

# ==========================================
# 5. DEFINICJE MODELI (u jest już binarne 0/1)
# ==========================================

def model_FOLP(u, K, T1):
    return get_sim([K], [T1, 1], u)

def model_FOLP_Z(u, K, T1, Tz):
    return get_sim([K * Tz, K], [T1, 1], u)

def model_FOLPD(u, K, T1, L):
    return model_FOLP(apply_delay(u, L), K, T1)

def model_FOLPD_Z(u, K, T1, Tz, L):
    return model_FOLP_Z(apply_delay(u, L), K, T1, Tz)

def model_SOSP(u, K, T1, T2):
    return get_sim([K], build_poly([T1, T2]), u)

def model_SOSP_Z(u, K, T1, T2, Tz):
    return get_sim([K * Tz, K], build_poly([T1, T2]), u)

def model_SOSPD(u, K, T1, T2, L):
    return model_SOSP(apply_delay(u, L), K, T1, T2)

def model_SOSPD_Z(u, K, T1, T2, Tz, L):
    return model_SOSP_Z(apply_delay(u, L), K, T1, T2, Tz)

def model_TOSP(u, K, T1, T2, T3):
    return get_sim([K], build_poly([T1, T2, T3]), u)

def model_TOSPD(u, K, T1, T2, T3, L):
    return model_TOSP(apply_delay(u, L), K, T1, T2, T3)

def model_FOSP(u, K, T1, T2, T3, T4, T5):
    return get_sim([K], build_poly([T1, T2, T3, T4, T5]), u)

def model_FOSPD(u, K, T1, T2, T3, T4, T5, L):
    return model_FOSP(apply_delay(u, L), K, T1, T2, T3, T4, T5)

# ==========================================
# 6. KONFIGURACJA — WSZYSTKIE MODELE
# ==========================================
INF = 50000

# Modele BEZ opóźnienia w parametrach (L będzie szukane iteracyjnie osobno)
MODELS_NO_DELAY = [
    {"name": "FOLP",    "func": model_FOLP,    "p0": [34, 1400],              "bounds": (0, [500, INF])},
    {"name": "FOLP_Z",  "func": model_FOLP_Z,  "p0": [36, 1160, -60],         "bounds": ([-500, -INF, -INF], [500, INF, INF])},
    {"name": "SOSP",    "func": model_SOSP,    "p0": [34, 960, 95],            "bounds": (0, [500, INF, INF])},
    {"name": "SOSP_Z",  "func": model_SOSP_Z,  "p0": [34, 975, 80, -11],      "bounds": ([-500, -INF, -INF, -INF], [500, INF, INF, INF])},
    {"name": "TOSP",    "func": model_TOSP,    "p0": [34, 990, 45, 45],        "bounds": (0, [500, INF, INF, INF])},
    {"name": "FOSP",    "func": model_FOSP,    "p0": [34, 990, 45, 45, 0.1, 0.1], "bounds": (0, [500, INF, INF, INF, INF, INF])},
]

# Modele Z opóźnieniem — L iteracyjnie szukane (podajemy model bez L, wrapper doda)
MODELS_WITH_DELAY = [
    {
        "name": "FOLPD",
        "func_no_L": model_FOLP,
        "func_with_L": model_FOLPD,
        "p0": [34, 1040],
        "bounds_no_L": (0, [500, INF]),
        "bounds_with_L": (0, [500, INF, 1000]),
    },
    {
        "name": "FOLPD_Z",
        "func_no_L": model_FOLP_Z,
        "func_with_L": model_FOLPD_Z,
        "p0": [34, 1040, 0.01],
        "bounds_no_L": ([-500, -INF, -INF], [500, INF, INF]),
        "bounds_with_L": ([-500, -INF, -INF, 0], [500, INF, INF, 1000]),
    },
    {
        "name": "SOSPD",
        "func_no_L": model_SOSP,
        "func_with_L": model_SOSPD,
        "p0": [34, 980, 75],
        "bounds_no_L": (0, [500, INF, INF]),
        "bounds_with_L": (0, [500, INF, INF, 1000]),
    },
    {
        "name": "SOSPD_Z",
        "func_no_L": model_SOSP_Z,
        "func_with_L": model_SOSPD_Z,
        "p0": [34, 500, 1050, 500],
        "bounds_no_L": (0, [500, INF, INF, INF]),
        "bounds_with_L": (0, [500, INF, INF, INF, 1000]),
    },
    {
        "name": "TOSPD",
        "func_no_L": model_TOSP,
        "func_with_L": model_TOSPD,
        "p0": [34, 990, 45, 45],
        "bounds_no_L": (0, [500, INF, INF, INF]),
        "bounds_with_L": (0, [500, INF, INF, INF, 1000]),
    },
    {
        "name": "FOSPD",
        "func_no_L": model_FOSP,
        "func_with_L": model_FOSPD,
        "p0": [34, 990, 45, 45, 0.1, 0.1],
        "bounds_no_L": (0, [500, INF, INF, INF, INF, INF]),
        "bounds_with_L": (0, [500, INF, INF, INF, INF, INF, 1000]),
    },
]

# ==========================================
# 7. ITERACYJNE SZUKANIE OPÓŹNIENIA
# ==========================================
def find_best_delay(u_bin, y_delta, m_with_delay):
    """
    Dla danego modelu z opóźnieniem przeszukuje zakres L_SEARCH_MIN..L_SEARCH_MAX
    z krokiem L_SEARCH_STEP, dla każdego L dopasowuje pozostałe parametry
    i zwraca L*, popt* o najlepszym adj_R².
    """
    best_r2   = -np.inf
    best_L    = 0
    best_popt = None

    L_candidates = range(L_SEARCH_MIN, L_SEARCH_MAX + 1, L_SEARCH_STEP)
    print(f"  [{m_with_delay['name']}] Iteracyjne szukanie L "
          f"({L_SEARCH_MIN}..{L_SEARCH_MAX}, krok {L_SEARCH_STEP}) ...", end=" ", flush=True)

    for L_try in L_candidates:
        u_shifted = apply_delay(u_bin, L_try)

        # Dopasuj parametry modelu BEZ opóźnienia na przesuniętym sygnale
        try:
            popt_no_L, _ = curve_fit(
                m_with_delay["func_no_L"],
                u_shifted,
                y_delta,
                p0=m_with_delay["p0"],
                bounds=m_with_delay["bounds_no_L"],
                maxfev=10000,
            )
            y_pred = m_with_delay["func_no_L"](u_shifted, *popt_no_L)
            n_params = len(popt_no_L) + 1  # +1 za L
            r2, adj_r2, _ = compute_metrics(y_delta, y_pred, n_params)

            if adj_r2 > best_r2:
                best_r2   = adj_r2
                best_L    = L_try
                best_popt = popt_no_L
        except Exception:
            continue

    print(f"L* = {best_L}  (adj R² = {best_r2:.4f})")
    return best_L, best_popt, best_r2

# ==========================================
# 8. SILNIK OBLICZENIOWY
# ==========================================
def run_identification(file_path):
    df = pd.read_csv(file_path, sep=';')
    clean = lambda s: pd.to_numeric(s.astype(str).str.replace(',', '.'), errors='coerce')

    y_raw = clean(df['HRT_temp_grzana']).values

    # --- Sygnał binarny u(t) = 1 gdy suma mocy > 0, inaczej 0 ---
    moc1 = clean(df.iloc[:, -2]).fillna(0).values  # przedostatnia kolumna
    moc2 = clean(df.iloc[:, -1]).fillna(0).values  # ostatnia kolumna
    u_raw = ((moc1 + moc2) > 0).astype(float)      # binaryzacja → 0.0 lub 1.0

    mask = ~np.isnan(y_raw)
    y, u_bin = y_raw[mask], u_raw[mask]
    t  = np.arange(len(y))
    y0 = y[0]
    y_delta = y - y0

    print(f"\nWczytano {len(y)} próbek.")
    print(f"Sygnał wejściowy: binarny  0/1  (impulsy prostokątne)")
    print(f"Liczba przejść 0→1: {int(np.sum(np.diff(u_bin) > 0))}")
    print(f"Zakres szukania opóźnienia: {L_SEARCH_MIN}..{L_SEARCH_MAX} próbek, krok {L_SEARCH_STEP}\n")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True,
                                   gridspec_kw={'height_ratios': [3, 1]})
    ax1.plot(t, y, 'k--', label='Dane pomiarowe', alpha=0.4, lw=1.5)
    n_total = len(MODELS_NO_DELAY) + len(MODELS_WITH_DELAY)
    colors   = plt.cm.tab20(np.linspace(0, 1, n_total))
    color_idx = 0

    header = f"{'MODEL':<12} | {'R²':<8} | {'adj R²':<8} | {'AIC':<12} | PARAMETRY"
    print(header)
    print("-" * 120)

    results = []

    # --- Modele BEZ iteracyjnego szukania L ---
    for m in MODELS_NO_DELAY:
        try:
            popt, _ = curve_fit(
                m["func"], u_bin, y_delta,
                p0=m["p0"], bounds=m["bounds"], maxfev=20000
            )
            y_fit  = m["func"](u_bin, *popt) + y0
            n_params = len(popt)
            r2, adj_r2, aic = compute_metrics(y, y_fit, n_params)

            results.append({"name": m["name"], "r2": r2, "adj_r2": adj_r2,
                             "aic": aic, "popt": popt, "L_best": None})
            print(f"{m['name']:<12} | {r2:<8.4f} | {adj_r2:<8.4f} | {aic:<12.2f} | {np.round(popt, 3)}")

            if r2 >= R2_MIN_PLOT:
                ax1.plot(t, y_fit,
                         label=f"{m['name']} (adj R²={adj_r2:.4f})",
                         color=colors[color_idx], lw=1.8)
            else:
                print(f"  → pominięto na wykresie (R²={r2:.4f} < {R2_MIN_PLOT})")
        except Exception as e:
            print(f"{m['name']:<12} | BŁĄD: {e}")
        color_idx += 1

    # --- Modele Z iteracyjnym szukaniem L ---
    for m in MODELS_WITH_DELAY:
        try:
            # Krok 1: znajdź najlepsze L iteracyjnie
            L_best, popt_no_L, _ = find_best_delay(u_bin, y_delta, m)

            if popt_no_L is None:
                print(f"{m['name']:<12} | BŁĄD: nie udało się dopasować dla żadnego L")
                color_idx += 1
                continue

            # Krok 2: dokładne dopasowanie ze znalezionym L jako punktem startowym
            p0_full     = list(popt_no_L) + [float(L_best)]
            bounds_lo   = m["bounds_with_L"][0]
            bounds_hi   = m["bounds_with_L"][1]
            # Upewnij się, że L_best leży w granicach
            if isinstance(bounds_lo, (int, float)):
                bounds_lo = [bounds_lo] * len(p0_full)
            else:
                bounds_lo = list(bounds_lo)
            if isinstance(bounds_hi, (int, float)):
                bounds_hi = [bounds_hi] * len(p0_full)
            else:
                bounds_hi = list(bounds_hi)

            popt_full, _ = curve_fit(
                m["func_with_L"], u_bin, y_delta,
                p0=p0_full,
                bounds=(bounds_lo, bounds_hi),
                maxfev=20000
            )
            y_fit    = m["func_with_L"](u_bin, *popt_full) + y0
            n_params = len(popt_full)
            r2, adj_r2, aic = compute_metrics(y, y_fit, n_params)

            results.append({"name": m["name"], "r2": r2, "adj_r2": adj_r2,
                             "aic": aic, "popt": popt_full, "L_best": L_best})
            print(f"{m['name']:<12} | {r2:<8.4f} | {adj_r2:<8.4f} | {aic:<12.2f} | "
                  f"{np.round(popt_full, 3)}  [L_iter={L_best}]")

            if r2 >= R2_MIN_PLOT:
                ax1.plot(t, y_fit,
                         label=f"{m['name']} L={popt_full[-1]:.0f} (adj R²={adj_r2:.4f})",
                         color=colors[color_idx], lw=1.8)
            else:
                print(f"  → pominięto na wykresie (R²={r2:.4f} < {R2_MIN_PLOT})")
        except Exception as e:
            print(f"{m['name']:<12} | BŁĄD: {e}")
        color_idx += 1

    # --- Podsumowanie ---
    if results:
        best = max(results, key=lambda x: x["adj_r2"])
        print("\n" + "=" * 90)
        print(f"  NAJLEPSZY MODEL : {best['name']}")
        print(f"  adj R²          : {best['adj_r2']:.4f}")
        print(f"  AIC             : {best['aic']:.2f}")
        if best["L_best"] is not None:
            print(f"  L iteracyjne    : {best['L_best']} próbek  (ostateczne z curve_fit: {best['popt'][-1]:.1f})")
        print(f"  PARAMETRY       : {np.round(best['popt'], 4)}")
        print("=" * 90)

    ax1.set_title(f"Porównanie modeli — wejście binarne u∈{{0,1}}  (wyświetlane: R² ≥ {R2_MIN_PLOT})")
    ax1.legend(loc='lower right', fontsize=8, ncol=2)
    ax1.grid(True, alpha=0.2)
    ax1.set_ylabel("Temperatura [°C]")

    ax2.fill_between(t, u_bin, color='steelblue', alpha=0.4, label='u(t) binarny')
    ax2.set_ylim(-0.1, 1.4)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(['0 (wyłączone)', '1 (włączone)'])
    ax2.set_ylabel("Sygnał wejściowy")
    ax2.set_xlabel("Czas [s]")
    ax2.legend(loc='upper right', fontsize=8)
    ax2.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig("identyfikacja_wyniki.png", dpi=150, bbox_inches='tight')
    plt.show()

if __name__ == "__main__":
    run_identification('D:\\Pulpit\\KN ALGO\\Szyna\\Nowe_dane\\skok.csv')