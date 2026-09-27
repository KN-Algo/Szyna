# Identyfikacja/Identyfikacja/identyfikacja_crt.py
#
# DODATKOWY, samodzielny skrypt (NIE modyfikuje idetyfikacja_modele.py,
# idetyfikacja_modelu_temperatrua_poweitrza.py ani identyfikacja_miso.py -
# wszystkie trzy pozostają nietknięte).
#
# PO CO: dotychczasowa identyfikacja modelu "pogodowego" (AT -> temperatura
# szyny, idetyfikacja_modelu_temperatrua_poweitrza.py) i przesiewanie kanałów
# w identyfikacja_miso.py liczyły transmitancję AT -> HRT (szyna OGRZEWANA).
# HRT poza krótkim oknem testu skokowego ma NIEZNANY, potencjalnie niezerowy
# stan grzania (patrz identyfikacja_miso.py, sekcja "ILE JEST W TYCH DANYCH
# MOMENTÓW..."), więc taki model opisuje CAŁY układ zamknięty (pogoda + ew.
# grzanie), nie czystą fizykę szyny. CRT ("temperatura szyny NIEogrzewanej")
# nie ma tego problemu - z definicji nie zależy od grzania - więc jest
# WŁAŚCIWYM, czystym celem do wyznaczenia transmitancji AT -> CRT (odpowiednik
# TF_WEATHER w Benchmark/benchmark/symulacja_fizyczna.py, tam dotąd wzięty z
# INNEGO wcześniejszego pomiaru, nie z tych danych z Wrocławia).
#
# METODOLOGIA: identyczna jak w idetyfikacja_modelu_temperatrua_poweitrza.py/
# identyfikacja_miso.py (ta sama biblioteka postaci modeli I/FO/FO_Z/SO/SO_Z/
# TO/FOD/SOD, ten sam silnik dopasowania MNK przez
# scipy.signal.TransferFunction.to_discrete + lfilter, dt=10s), ale:
#   1) źródłem jest surowy log urządzenia (algo (4).log) - te same ~3 tygodnie
#      danych co identyfikacja_miso.py,
#   2) CEL to CRT (nie HRT),
#   3) dni testu skokowego (IndOn) są wykluczone - jak w identyfikacja_miso.py -
#      ORAZ dodatkowo w sekcji 0 skrypt EMPIRYCZNIE sprawdza (na danych z
#      TYCH właśnie okien, gdzie moc jest znana), czy CRT w ogóle koreluje z
#      mocą grzania - to weryfikacja założenia "CRT nie zależy od grzania",
#      nie tylko wiara w nazwę kolumny.
#
# Wynik: ranking wszystkich postaci modelu (R²/adj R²/AIC/RMSE/MAE) wypisany
# w konsoli + zapisany do wyniki_identyfikacja/wyniki_identyfikacji_crt.csv
# (i .xlsx, jeśli openpyxl dostępne) + wykres przesiewania
# wyniki_identyfikacja/przesiewanie_AT_CRT.png (ten sam, wspólny folder co
# identyfikacja_miso.py - to "dodatkowy model do całości", nie osobny temat).
#
# Uruchomienie: python identyfikacja_crt.py   (z tego folderu)

import os
import re
import sys

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

RESAMPLE_S = 10  # ta sama siatka co w identyfikacja_miso.py

# Zakres iteracyjnego szukania opóźnienia L - jak w idetyfikacja_modelu_
# temperatrua_poweitrza.py/identyfikacja_miso.py (kanały pogodowe). Tylko
# JEDEN kanał (AT) do przesiania, więc stać nas na PEŁNĄ gęstość siatki
# (krok 5 próbek = 50s), bez trybu "szybkiego" z identyfikacja_miso.py.
L_SEARCH_MIN = 0
L_SEARCH_MAX = 360    # 360 x 10s = 1h
L_SEARCH_STEP = 5

INF = 50_000

# ==========================================================================
# 2. PARSOWANIE LOGU (powielone z identyfikacja_miso.py - patrz tam pełny
#    opis formatu; tu tylko to, co potrzebne: CRT/HRT/AT + okna IndOn, żeby
#    ten skrypt był w pełni samodzielny)
# ==========================================================================
_PAT_P1 = re.compile(
    r'^(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) ALGOp1: '
    r'CRT ([\-\d.]+), HRT ([\-\d.]+), AT:?\s*([\-\d.]+)'
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
    rows_p1, rows_p3, tryby = [], [], []
    with open(sciezka, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            m = _PAT_P1.match(line)
            if m:
                rows_p1.append((m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))))
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
    df_p3 = do_df(rows_p3, ['PWRL1', 'PWRL2'])
    df = pd.merge_asof(df_p1, df_p3, on='Timestamp', tolerance=pd.Timedelta('2s'), direction='nearest')
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

    print(f"Wczytano log: {len(df_p1)} próbek ALGOp1 (CRT/HRT/AT), {len(df_p3)} ALGOp3 (moc).")
    print(f"Zakres czasu: {df['Timestamp'].min()}  ->  {df['Timestamp'].max()}")
    print(f"Wykryto {len(okna)} okien testu skokowego (IndOn->koniec trybu ręcznego).")
    return df, okna


def resampluj(df, dt_s):
    df = df.drop_duplicates(subset='Timestamp').sort_values('Timestamp').reset_index(drop=True)
    siatka = pd.date_range(df['Timestamp'].min(), df['Timestamp'].max(), freq=f'{dt_s}s')
    siatka_df = pd.DataFrame({'Timestamp': siatka})

    ciagle = [k for k in ['CRT', 'HRT', 'AT'] if k in df.columns]
    dyskretne = [k for k in ['PWRL1', 'PWRL2'] if k in df.columns]

    out = pd.DataFrame({'Timestamp': siatka})
    idx_num = df['Timestamp'].to_numpy().astype('int64')
    siatka_num = siatka.to_numpy().astype('int64')
    for k in ciagle:
        out[k] = np.interp(siatka_num, idx_num, df[k].to_numpy())
    reszta = pd.merge_asof(siatka_df, df[['Timestamp'] + dyskretne], on='Timestamp', direction='backward')
    for k in dyskretne:
        out[k] = reszta[k].to_numpy()
    return out


# ==========================================================================
# 3. RDZEŃ TRANSMITANCJI (identyczna matematyka jak w skryptach referencyjnych)
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
# 4. BIBLIOTEKA POSTACI MODELI - IDENTYCZNA jak "modele_pogodowe()" w
#    identyfikacja_miso.py / MODELS_NO_DELAY-WEATHER w skrypcie referencyjnym
#    (sygnał wolnozmienny AT, stałe czasowe rzędu godzin).
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


MODELS_NO_DELAY = [
    {"name": "I", "func": m_I, "p0": [0.01], "bounds": ([-10], [10])},
    {"name": "FO", "func": m_FO, "p0": [0.5, 600], "bounds": ([-2.0, 1], [2.0, 200_000])},
    {"name": "FO_Z", "func": m_FO_Z, "p0": [0.5, 600, 100], "bounds": ([-2.0, 1, -100_000], [2.0, 200_000, 100_000])},
    {"name": "SO", "func": m_SO, "p0": [0.5, 3000, 500], "bounds": ([-2.0, 1, 1], [2.0, 200_000, 200_000])},
    {"name": "SO_Z", "func": m_SO_Z, "p0": [0.5, 3000, 500, 100], "bounds": ([-2.0, 1, 1, -100_000], [2.0, 200_000, 200_000, 100_000])},
    {"name": "TO", "func": m_TO, "p0": [0.5, 2000, 500, 100], "bounds": ([-2.0, 1, 1, 1], [2.0, 200_000, 200_000, 200_000])},
]

def _wrap_delay(func_no_L):
    """func_with_L(u, *params_no_L, L) = func_no_L(apply_delay(u, L), *params_no_L)."""
    def func_with_L(u, *params):
        *p, L = params
        return func_no_L(apply_delay(u, L), *p)
    return func_with_L


MODELS_WITH_DELAY = [
    {"name": "FOD", "func_no_L": m_FO, "func_with_L": _wrap_delay(m_FO), "p0": [0.5, 600],
     "bounds_no_L": ([-2.0, 1], [2.0, 200_000]),
     "bounds_with_L": ([-2.0, 1, 0], [2.0, 200_000, L_SEARCH_MAX])},
    {"name": "SOD", "func_no_L": m_SO, "func_with_L": _wrap_delay(m_SO), "p0": [0.5, 3000, 500],
     "bounds_no_L": ([-2.0, 1, 1], [2.0, 200_000, 200_000]),
     "bounds_with_L": ([-2.0, 1, 1, 0], [2.0, 200_000, 200_000, L_SEARCH_MAX])},
]


# ==========================================================================
# 5. SILNIK DOPASOWANIA (SISO, jeden kanał: AT -> CRT)
# ==========================================================================
def _fit_bez_L(m, u, y):
    popt, _ = curve_fit(m["func"], u, y, p0=m["p0"], bounds=m["bounds"], maxfev=30000)
    return popt


def _znajdz_L(m, u, y):
    best_adj, best_L, best_popt = -np.inf, 0, None
    for L_try in range(L_SEARCH_MIN, L_SEARCH_MAX + 1, L_SEARCH_STEP):
        u_shift = apply_delay(u, L_try)
        try:
            popt, _ = curve_fit(m["func_no_L"], u_shift, y, p0=m["p0"], bounds=m["bounds_no_L"], maxfev=10000)
            y_pred = m["func_no_L"](u_shift, *popt)
            met = compute_metrics(y, y_pred, len(popt) + 1)
            if met["adj_r2"] > best_adj:
                best_adj, best_L, best_popt = met["adj_r2"], L_try, popt
        except Exception:
            pass
    return best_L, best_popt


def przesiej(u, y):
    wyniki = []
    print(f"\n{'MODEL':<8} | {'TYP':<8} | {'R²':>8} | {'adj R²':>8} | {'RMSE':>8} | {'MAE':>8} | {'AIC':>12} | L [s] | PARAMETRY")
    print("-" * 120)

    for m in MODELS_NO_DELAY:
        try:
            popt = _fit_bez_L(m, u, y)
            y_pred = m["func"](u, *popt)
            met = compute_metrics(y, y_pred, len(popt))
            wyniki.append({"model": m["name"], "typ": "brak L", "popt": popt, "L": None,
                            "func": m["func"], **met})
            print(f"{m['name']:<8} | {'brak L':<8} | {met['r2']:8.4f} | {met['adj_r2']:8.4f} | "
                  f"{met['rmse']:8.4f} | {met['mae']:8.4f} | {met['aic']:12.2f} | {'—':>5} | {np.round(popt, 4)}")
        except Exception as e:
            print(f"{m['name']:<8} | BŁĄD: {e}")

    for m in MODELS_WITH_DELAY:
        try:
            L_best, popt_no_L = _znajdz_L(m, u, y)
            if popt_no_L is None:
                print(f"{m['name']:<8} | BŁĄD: brak zbieżności dla żadnego L")
                continue
            p0_full = list(popt_no_L) + [float(L_best)]
            popt, _ = curve_fit(m["func_with_L"], u, y, p0=p0_full, bounds=m["bounds_with_L"], maxfev=30000)
            y_pred = m["func_with_L"](u, *popt)
            met = compute_metrics(y, y_pred, len(popt))
            wyniki.append({"model": m["name"], "typ": "L iter.", "popt": popt, "L": popt[-1],
                            "func": m["func_with_L"], **met})
            print(f"{m['name']:<8} | {'L iter.':<8} | {met['r2']:8.4f} | {met['adj_r2']:8.4f} | "
                  f"{met['rmse']:8.4f} | {met['mae']:8.4f} | {met['aic']:12.2f} | "
                  f"{popt[-1] * RESAMPLE_S:5.0f} | {np.round(popt, 4)}")
        except Exception as e:
            print(f"{m['name']:<8} | BŁĄD: {e}")

    return wyniki


def wykres_przesiewania(t, y, u, wyniki, plik_png):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                                    gridspec_kw={'height_ratios': [3, 1]})
    ax1.plot(t, y, 'k--', label='CRT (pomiar)', alpha=0.5, lw=1.3)
    dobre = [w for w in wyniki if w["r2"] >= 0.3]
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(dobre), 1)))
    for i, w in enumerate(dobre):
        y_pred = w["func"](u, *w["popt"])
        etyk_L = f" L={w['L'] * RESAMPLE_S:.0f}s" if w["L"] is not None else ""
        ax1.plot(t, y_pred, color=colors[i], lw=1.6,
                  label=f"{w['model']}{etyk_L} (adj R²={w['adj_r2']:.4f})")
    ax1.legend(loc='lower right', fontsize=8, ncol=2)
    ax1.grid(True, alpha=0.2)
    ax1.set_ylabel("CRT [°C]")
    ax1.set_title("Przesiewanie modeli transmitancji AT -> CRT (szyna NIEogrzewana)")

    ax2.plot(t, u, color='steelblue', lw=1.0)
    ax2.fill_between(t, u, color='steelblue', alpha=0.3)
    ax2.set_ylabel("AT [°C]")
    ax2.set_xlabel("Czas")
    ax2.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(plik_png, dpi=150, bbox_inches='tight')
    plt.close(fig)


# ==========================================================================
# 6. MAIN
# ==========================================================================
def main():
    print("=" * 90)
    print("IDENTYFIKACJA TRANSMITANCJI AT -> CRT (szyna NIEogrzewana)")
    print("Dodatkowy model do całości - odpowiednik TF_WEATHER z symulacji fizycznej")
    print("=" * 90)

    df_raw, okna = wczytaj_log(LOG_PATH)
    if not okna:
        print("UWAGA: nie znaleziono okien testu skokowego - kontynuuję bez sprawdzenia "
              "wrażliwości CRT na moc (sekcja 0 niżej pominięta).")

    # --- SEKCJA 0: czy CRT faktycznie nie zależy od grzania? Sprawdzamy to
    # empirycznie w oknach testu skokowego (tam, gdzie moc JEST znana) -
    # zamiast wierzyć nazwie kolumny na słowo. ---
    if okna:
        print("\n" + "=" * 78)
        print("SEKCJA 0: czy CRT reaguje na moc grzania? (sprawdzone w oknach testu skokowego,")
        print("tam gdzie moc jest znana - CRT z definicji powinien być od niej niezależny)")
        for a, b in okna:
            sub = df_raw[(df_raw['Timestamp'] >= a) & (df_raw['Timestamp'] <= b)]
            pwr = (sub['PWRL1'].fillna(0) + sub['PWRL2'].fillna(0))
            crt_zakres = sub['CRT'].max() - sub['CRT'].min()
            hrt_zakres = sub['HRT'].max() - sub['HRT'].min()
            print(f"  Okno {a.date()} ({(b - a).total_seconds() / 60:.0f} min): moc {pwr.min():.0f}-{pwr.max():.0f}, "
                  f"rozstęp CRT={crt_zakres:.2f}°C, rozstęp HRT={hrt_zakres:.2f}°C "
                  f"(HRT rośnie z grzaniem, CRT powinien zostać płaski)")
        print("=" * 78)

    df_pog = resampluj(df_raw, RESAMPLE_S)
    if okna:
        maska_dni_skoku = pd.Series(False, index=df_pog.index)
        for a, b in okna:
            dzien_a, dzien_b = a.normalize(), b.normalize()
            maska_dni_skoku |= (df_pog['Timestamp'].dt.normalize() >= dzien_a) & (df_pog['Timestamp'].dt.normalize() <= dzien_b)
        df_pog = df_pog[~maska_dni_skoku].copy()
        print(f"\nWykluczono dni testu skokowego (jak w identyfikacja_miso.py, dla spójności "
              f"metodologii) - {int(maska_dni_skoku.sum())} próbek usuniętych.")
    df_pog = df_pog.dropna(subset=['AT', 'CRT']).reset_index(drop=True)

    t = df_pog['Timestamp'].to_numpy()
    u_at = df_pog['AT'].to_numpy()
    y_crt = df_pog['CRT'].to_numpy()
    rozpietosc_dni = (t[-1] - t[0]).astype('timedelta64[s]').astype(float) / 86400.0

    print(f"\nDane do identyfikacji AT -> CRT: {len(df_pog)} próbek, {rozpietosc_dni:.1f} dni "
          f"(krok {RESAMPLE_S}s).")
    print(f"AT: [{u_at.min():.1f}, {u_at.max():.1f}] °C   CRT: [{y_crt.min():.1f}, {y_crt.max():.1f}] °C")

    wyniki = przesiej(u_at, y_crt)
    if not wyniki:
        print("BŁĄD: żaden model się nie dopasował - przerywam.")
        return

    najlepszy = max(wyniki, key=lambda w: w["adj_r2"])
    print("\n" + "=" * 90)
    print("NAJLEPSZY MODEL TRANSMITANCJI AT -> CRT")
    print(f"  Postać          : {najlepszy['model']}  [{najlepszy['typ']}]")
    print(f"  R²              : {najlepszy['r2']:.4f}")
    print(f"  adj R²          : {najlepszy['adj_r2']:.4f}")
    print(f"  RMSE            : {najlepszy['rmse']:.4f} °C")
    print(f"  MAE             : {najlepszy['mae']:.4f} °C")
    print(f"  AIC             : {najlepszy['aic']:.2f}")
    if najlepszy["L"] is not None:
        print(f"  Opóźnienie L    : {najlepszy['L']:.1f} próbek = {najlepszy['L'] * RESAMPLE_S:.0f} s "
              f"= {najlepszy['L'] * RESAMPLE_S / 60:.1f} min")
    print(f"  Parametry       : {np.round(najlepszy['popt'], 4)}")
    print("=" * 90)

    wykres_przesiewania(t, y_crt, u_at, wyniki, os.path.join(OUTPUT_DIR, "przesiewanie_AT_CRT.png"))

    # --- porównanie z modelem AT -> HRT (jeśli wyniki identyfikacja_miso.py
    # już istnieją) - żeby od razu było widać różnicę względem dotychczasowego,
    # "zanieczyszczonego" nieznanym grzaniem modelu HRT. ---
    sciezka_miso = os.path.join(OUTPUT_DIR, "wyniki_identyfikacji_miso.csv")
    if os.path.exists(sciezka_miso):
        try:
            df_miso = pd.read_csv(sciezka_miso, encoding='utf-8-sig')
            df_at_hrt = df_miso[df_miso['kanal'] == 'AT']
            if not df_at_hrt.empty:
                best_hrt = df_at_hrt.loc[df_at_hrt['adj_R2'].idxmax()]
                print("\nPorównanie z dotychczasowym modelem AT -> HRT (identyfikacja_miso.py):")
                print(f"  AT -> HRT (grzanie w tym okresie NIEZNANE): {best_hrt['model']}, "
                      f"adj R²={best_hrt['adj_R2']:.4f}, RMSE={best_hrt['RMSE']:.4f}°C")
                print(f"  AT -> CRT (bez wpływu grzania z definicji): {najlepszy['model']}, "
                      f"adj R²={najlepszy['adj_r2']:.4f}, RMSE={najlepszy['rmse']:.4f}°C")
        except Exception as e:
            print(f"(Pominięto porównanie z modelem HRT: {e})")

    # --- zapis wyników ---
    wiersze = [{"kanal": "AT", "cel": "CRT", "model": w["model"], "typ": w["typ"],
                "R2": w["r2"], "adj_R2": w["adj_r2"], "AIC": w["aic"], "RMSE": w["rmse"], "MAE": w["mae"],
                "L_probek": w["L"], "L_s": (w["L"] * RESAMPLE_S) if w["L"] is not None else None,
                "parametry": np.round(w["popt"], 4).tolist()} for w in wyniki]
    df_wynik = pd.DataFrame(wiersze).sort_values("adj_R2", ascending=False).reset_index(drop=True)

    sciezka_csv = os.path.join(OUTPUT_DIR, "wyniki_identyfikacji_crt.csv")
    df_wynik.to_csv(sciezka_csv, index=False, encoding='utf-8-sig')
    print(f"\nZapisano tabelę: {sciezka_csv}")

    try:
        sciezka_xlsx = os.path.join(OUTPUT_DIR, "wyniki_identyfikacji_crt.xlsx")
        with pd.ExcelWriter(sciezka_xlsx, engine='openpyxl') as writer:
            df_wynik.to_excel(writer, sheet_name='Model_AT_CRT', index=False)
        print(f"Zapisano Excel: {sciezka_xlsx}")
    except ImportError:
        print("UWAGA: openpyxl niedostępny - zapisano tylko CSV.")

    print(f"Wykres zapisany: {os.path.join(OUTPUT_DIR, 'przesiewanie_AT_CRT.png')}")
    print("\nGOTOWE.")


if __name__ == "__main__":
    main()
