# Identyfikacja/Identyfikacja/identyfikacja_miso.py
#
# DODATKOWY skrypt (NIE modyfikuje idetyfikacja_modele.py ani
# idetyfikacja_modelu_temperatrua_poweitrza.py - te dwa pozostają
# nietknięte, są "tablicą prawdy") - liczy TO SAMO co tamte dwa (identyfikacja
# transmitancji metodą najmniejszych kwadratów, ta sama biblioteka postaci
# modeli: FO/SO/TO z zerem/opóźnieniem, ta sama symulacja przez
# scipy.signal.TransferFunction.to_discrete + lfilter), ale:
#   1) źródłem danych jest SUROWY log urządzenia (algo (4).log), nie gotowe
#      CSV - dzięki temu mamy PEŁNE ~3 tygodnie danych (04-15..05-06), nie
#      tylko dwa krótkie okna testu skokowego,
#   2) oprócz mocy grzania (PWRL1+PWRL2 -> HRT, jak w idetyfikacja_modele.py)
#      i temperatury powietrza (AT -> HRT, jak w drugim skrypcie) sprawdza
#      WSZYSTKIE pozostałe parametry obecne w danych: DPT (punkt rosy), RH
#      (wilgotność), PRESS (ciśnienie), PRECIP/SNOW (flagi 0/1) - UWAGA: w
#      tych danych NIE MA wiatru ani nasłonecznienia (potwierdzone opisem pól
#      urządzenia - patrz notatki_identyfikacja/README.md) - nie są więc
#      sprawdzane, bo fizycznie ich tu nie ma,
#   3) buduje z najlepszych transmitancji per-kanał JEDEN wspólny model MISO
#      (Multi-Input-Single-Output): HRT = y0 + Σ G_i(kanał_i), dopasowany
#      WSPÓLNIE (MNK łącznie na wszystkich parametrach naraz), plus analizę
#      ablacyjną (usunięcie po jednym kanale -> spadek R² = miara wpływu).
#
# Wynik: tabela zbiorcza (CSV + Excel jeśli openpyxl dostępne) i wykresy w
# STYLU takim samym jak referencyjne skrypty (patrz notatki_identyfikacja/),
# zapisywane do OSOBNEGO folderu wyniki_identyfikacja/ (nie miesza się z
# Wyniki/ referencyjnych skryptów). Pasek postępu w konsoli (uruchamiane
# lokalnie, może trwać - dużo dopasowań MNK).
#
# Uruchomienie: python identyfikacja_miso.py   (z tego folderu)

import os
import re
import sys
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy import signal

# Wymuś UTF-8 na stdout - domyślna strona kodowa konsoli Windows (cp1250)
# nie obsługuje znaku "²" używanego wszędzie niżej (R², adj R²). Bez tego
# skrypt wywala się UnicodeEncodeError w trakcie działania (po długim
# przeliczaniu), nie na starcie - stąd wymuszenie na samej górze pliku.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

# ==========================================================================
# 1. KONFIGURACJA
# ==========================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "algo (4).log")
# Wiatr/nasłonecznienie dla DOKŁADNEJ lokalizacji szyny (Wrocław Popowice,
# 51.121933, 17.005006) - urządzenie ich nie mierzy, więc pobrane OSOBNYM
# skryptem (pobierz_pogode_wroclaw_popowice.py, Open-Meteo, siatka 15-min) do
# OSOBNEGO pliku - wczytywane tu i dołączane jako dodatkowe kanały. Jeśli
# plik nie istnieje (nie uruchomiono skryptu pobierającego), te 2 kanały są
# pomijane - reszta analizy (moc, AT z logu, DPT/RH/PRESS/PRECIP) działa
# normalnie.
POGODA_ZEWNETRZNA_PATH = os.path.join(SCRIPT_DIR, "pogoda_wroclaw_popowice_15min.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "wyniki_identyfikacja")
os.makedirs(OUTPUT_DIR, exist_ok=True)

R2_MIN_PLOT = 0.3          # próg R² do narysowania kandydata na wykresie przesiewowym
RESAMPLE_S = 10             # siatka czasowa po resamplingu [s] - jak dt=10 w skrypcie pogodowym

# Tryb szybki: dzieli gęstość siatki przeszukiwania opóźnienia L przez ten
# współczynnik (1 = pełna dokładność jak w referencyjnych skryptach, ale WOLNO
# na 3 tygodniach danych; 4-8 = znacznie szybciej, kosztem gęstości siatki L).
# Zmień wg potrzeb - to JEDYNY "dial" na czas obliczeń w tym skrypcie.
QUICK_MODE_DZIELNIK = 4

L_SEARCH_MIN_MOC = 0
L_SEARCH_MAX_MOC = 200        # próbki po resamplingu (200 x 10s = ~33 min)
L_SEARCH_STEP_MOC = max(1, 5 * QUICK_MODE_DZIELNIK // 4)

L_SEARCH_MIN_POG = 0
L_SEARCH_MAX_POG = 360        # próbki (360 x 10s = 1h, jak w skrypcie pogodowym)
L_SEARCH_STEP_POG = max(1, 5 * QUICK_MODE_DZIELNIK)

INF = 50_000

# ==========================================================================
# 2. PASEK POSTĘPU (bez zewnętrznych zależności - uruchamiane lokalnie)
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
# 3. PARSOWANIE SUROWEGO LOGU URZĄDZENIA
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
    """
    Parsuje surowy log urządzenia (linie ALGOp1/p2/p3 + zmiany trybu
    sterowania obwodu 7) do jednego DataFrame na wspólnej osi czasu (merge_asof,
    tolerancja 2s - linie p1/p2/p3 dla tej samej próbki są zapisywane w
    odstępie pojedynczych milisekund) + listy okien testu skokowego
    (IndOn -> najbliższa kolejna zmiana trybu, zwykle Group/IndAuto/IndOff).
    """
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

    # --- okna testu skokowego: IndOn -> pierwsza kolejna zmiana trybu ---
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

    print(f"Wczytano log: {len(df_p1)} próbek ALGOp1, {len(df_p2)} ALGOp2, {len(df_p3)} ALGOp3 (moc).")
    print(f"Zakres czasu: {df['Timestamp'].min()}  ->  {df['Timestamp'].max()}")
    print(f"Wykryto {len(okna)} okien testu skokowego (IndOn->koniec trybu ręcznego):")
    for a, b in okna:
        print(f"    {a}  ->  {b}   ({(b - a).total_seconds() / 60:.1f} min)")

    return df, okna


def wczytaj_i_dolacz_pogode_zewnetrzna(df_raw):
    """
    Dołącza WIATR (wiatr_m_s) i NASŁONECZNIENIE (naslonecznienie_sekundy) z
    zewnętrznego pliku (pobierz_pogode_wroclaw_popowice.py, Open-Meteo, siatka
    15-min, DOKŁADNA lokalizacja szyny 51.121933,17.005006 - urządzenie tych
    dwóch wielkości nie mierzy). merge_asof (najbliższy w czasie, tolerancja
    10 min - siatka źródłowa jest 15-minutowa). Jeśli plik nie istnieje, zwraca
    df_raw bez zmian (te 2 kanały zostaną pominięte w dalszej analizie).
    """
    if not os.path.exists(POGODA_ZEWNETRZNA_PATH):
        print(f"UWAGA: brak pliku {POGODA_ZEWNETRZNA_PATH} - uruchom najpierw "
              f"pobierz_pogode_wroclaw_popowice.py, żeby dołączyć wiatr/nasłonecznienie. "
              f"Kontynuuję bez nich.")
        return df_raw

    df_zew = pd.read_csv(POGODA_ZEWNETRZNA_PATH, parse_dates=['Timestamp'])
    df_zew = df_zew.rename(columns={'wiatr_m_s': 'WIATR', 'naslonecznienie_sekundy': 'NASLONECZNIENIE'})
    df_raw = pd.merge_asof(
        df_raw.sort_values('Timestamp'),
        df_zew[['Timestamp', 'WIATR', 'NASLONECZNIENIE']].sort_values('Timestamp'),
        on='Timestamp', tolerance=pd.Timedelta('10min'), direction='nearest',
    )
    print(f"Dołączono wiatr/nasłonecznienie z Open-Meteo (Wrocław Popowice) - "
          f"{df_raw['WIATR'].notna().sum()}/{len(df_raw)} próbek pokrytych.")
    return df_raw


def resampluj(df, dt_s):
    """
    Resampling do jednolitej siatki co dt_s sekund - wymagane, bo
    scipy.signal.TransferFunction.to_discrete(dt=...) zakłada RÓWNY odstęp
    między próbkami, a surowe znaczniki czasu z urządzenia mają jitter
    (nieregularne odstępy ~1-10s). Ciągłe kanały (CRT/HRT/AT/DPT/RH/PRESS) -
    interpolacja liniowa. Dyskretne/flagi (PRECIP/SNOW) i moc (PWRL1/PWRL2) -
    "nearest" (nie wygładzamy sztucznie skoku 0/1 ani mocy).
    """
    df = df.drop_duplicates(subset='Timestamp').sort_values('Timestamp').reset_index(drop=True)
    siatka = pd.date_range(df['Timestamp'].min(), df['Timestamp'].max(), freq=f'{dt_s}s')
    siatka_df = pd.DataFrame({'Timestamp': siatka})

    # WIATR/NASLONECZNIENIE (z zewnętrznego API, patrz wczytaj_i_dolacz_pogode_zewnetrzna)
    # są ciągłe jak reszta - dołączane TYLKO jeśli obecne w df (plik z Open-Meteo pobrany).
    ciagle = [k for k in ['CRT', 'HRT', 'AT', 'DPT', 'RH', 'PRESS', 'WIATR', 'NASLONECZNIENIE'] if k in df.columns]
    dyskretne = [k for k in ['PRECIP', 'SNOW', 'PWRL1', 'PWRL2'] if k in df.columns]

    out = pd.DataFrame({'Timestamp': siatka})
    idx_num = df['Timestamp'].to_numpy().astype('int64')
    siatka_num = siatka.to_numpy().astype('int64')
    for k in ciagle:
        out[k] = np.interp(siatka_num, idx_num, df[k].to_numpy())
    # dyskretne/moc - "poprzednia znana wartość" (merge_asof, odporne na
    # zduplikowane/nieregularne znaczniki czasu, w przeciwieństwie do reindex)
    reszta = pd.merge_asof(siatka_df, df[['Timestamp'] + dyskretne], on='Timestamp', direction='backward')
    for k in dyskretne:
        out[k] = reszta[k].to_numpy()

    return out


# ==========================================================================
# 4. RDZEŃ TRANSMITANCJI (identyczna matematyka jak w referencyjnych
#    skryptach - apply_delay/get_sim/build_poly/compute_metrics - powielone
#    tutaj CELOWO zamiast importu, żeby ten plik był w pełni samodzielny i
#    NIGDY nie musiał importować/modyfikować referencyjnych skryptów)
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
    sys_d = signal.TransferFunction(num, den).to_discrete(dt=1, method='gbt', alpha=0.5)
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
# 5. BIBLIOTEKA POSTACI MODELI (SISO, per kanał)
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


def m_FOS(u, K, T1, T2, T3, T4, T5):
    return get_sim([K], build_poly([T1, T2, T3, T4, T5]), u)


def _wrap_delay(func_no_L, n_no_L):
    def func_with_L(u, *params):
        *p, L = params
        return func_no_L(apply_delay(u, L), *p)
    return func_with_L


# Biblioteka MOCY (kanał PWR, sygnał ~binarny/skokowy) - IDENTYCZNA postaciami
# jak MODELS_NO_DELAY/MODELS_WITH_DELAY w idetyfikacja_modele.py (tablica
# prawdy), więc wyniki dla kanału mocy są bezpośrednio porównywalne.
def modele_mocy(K0=34.0, T0=1000.0):
    bez_L = [
        {"name": "FOLP", "func": m_FO, "p0": [K0, T0], "bounds": (0, [500, INF]), "n": 2},
        {"name": "FOLP_Z", "func": m_FO_Z, "p0": [K0, T0, -60], "bounds": ([-500, -INF, -INF], [500, INF, INF]), "n": 3},
        {"name": "SOSP", "func": m_SO, "p0": [K0, T0 * 0.9, 95], "bounds": (0, [500, INF, INF]), "n": 3},
        {"name": "SOSP_Z", "func": m_SO_Z, "p0": [K0, T0 * 0.9, 80, -11], "bounds": ([-500, -INF, -INF, -INF], [500, INF, INF, INF]), "n": 4},
        {"name": "TOSP", "func": m_TO, "p0": [K0, T0 * 0.9, 45, 45], "bounds": (0, [500, INF, INF, INF]), "n": 4},
        {"name": "FOSP", "func": m_FOS, "p0": [K0, T0 * 0.9, 45, 45, 0.1, 0.1], "bounds": (0, [500, INF, INF, INF, INF, INF]), "n": 6},
    ]
    z_L = [
        {"name": "FOLPD", "func_no_L": m_FO, "p0": [K0, T0], "bounds_no_L": (0, [500, INF]), "bounds_with_L": (0, [500, INF, 1000])},
        {"name": "FOLPD_Z", "func_no_L": m_FO_Z, "p0": [K0, T0, 0.01], "bounds_no_L": ([-500, -INF, -INF], [500, INF, INF]), "bounds_with_L": ([-500, -INF, -INF, 0], [500, INF, INF, 1000])},
        {"name": "SOSPD", "func_no_L": m_SO, "p0": [K0, T0 * 0.9, 75], "bounds_no_L": (0, [500, INF, INF]), "bounds_with_L": (0, [500, INF, INF, 1000])},
        {"name": "TOSPD", "func_no_L": m_TO, "p0": [K0, T0 * 0.9, 45, 45], "bounds_no_L": (0, [500, INF, INF, INF]), "bounds_with_L": (0, [500, INF, INF, INF, 1000])},
    ]
    return bez_L, z_L


# Biblioteka kanałów POGODOWYCH (AT/DPT/RH/PRESS) - sygnał wolnozmienny, jak w
# idetyfikacja_modelu_temperatrua_poweitrza.py (MODELS_NO_DELAY/WITH_DELAY).
def modele_pogodowe():
    bez_L = [
        {"name": "I", "func": m_I, "p0": [0.01], "bounds": ([-10], [10]), "n": 1},
        {"name": "FO", "func": m_FO, "p0": [0.5, 600], "bounds": ([-2.0, 1], [2.0, 200_000]), "n": 2},
        {"name": "FO_Z", "func": m_FO_Z, "p0": [0.5, 600, 100], "bounds": ([-2.0, 1, -100_000], [2.0, 200_000, 100_000]), "n": 3},
        {"name": "SO", "func": m_SO, "p0": [0.5, 3000, 500], "bounds": ([-2.0, 1, 1], [2.0, 200_000, 200_000]), "n": 3},
        {"name": "SO_Z", "func": m_SO_Z, "p0": [0.5, 3000, 500, 100], "bounds": ([-2.0, 1, 1, -100_000], [2.0, 200_000, 200_000, 100_000]), "n": 4},
        {"name": "TO", "func": m_TO, "p0": [0.5, 2000, 500, 100], "bounds": ([-2.0, 1, 1, 1], [2.0, 200_000, 200_000, 200_000]), "n": 4},
    ]
    z_L = [
        {"name": "FOD", "func_no_L": m_FO, "p0": [0.5, 600], "bounds_no_L": ([-2.0, 1], [2.0, 200_000]), "bounds_with_L": ([-2.0, 1, 0], [2.0, 200_000, L_SEARCH_MAX_POG])},
        {"name": "SOD", "func_no_L": m_SO, "p0": [0.5, 3000, 500], "bounds_no_L": ([-2.0, 1, 1], [2.0, 200_000, 200_000]), "bounds_with_L": ([-2.0, 1, 1, 0], [2.0, 200_000, 200_000, L_SEARCH_MAX_POG])},
    ]
    return bez_L, z_L


# ==========================================================================
# 6. SILNIK DOPASOWANIA (SISO) - z paskiem postępu
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
    """
    Dopasowuje WSZYSTKIE postacie z biblioteki dla jednego kanału wejściowego,
    zwraca listę wyników. UWAGA: dopasowanie na SUROWYCH (u, y) - próba
    przesunięcia TYLKO y o y[0] (bez analogicznego przesunięcia u) była
    testowana i dawała ISTOTNIE GORSZE dopasowania (niespójne skale
    wejścia/wyjścia - np. AT: adj R² spadło z 0.969 do -0.209) - wycofane.
    Poprawne wspólne centrowanie (u i y względem średnich, jak w
    idetyfikacja_modelu_temperatrua_poweitrza.py, preprocess_signals
    mode='mean') wymagałoby spójnego przenoszenia offsetu przez etap MISO
    (inne okno czasowe) - zostawione jako możliwe dalsze usprawnienie, nie
    krytyczne: obecne dopasowania mają wysokie R² mimo kosmetycznego
    transientu na starcie długich serii (patrz notatki_identyfikacja/).
    """
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


def policz_liczba_krokow(kanaly_info, L_min, L_max, L_step):
    liczba_L = len(range(L_min, L_max + 1, L_step))
    total = 0
    for _, modele_bez_L, modele_z_L, *_ in kanaly_info:
        total += len(modele_bez_L) + len(modele_z_L)
    return total


# ==========================================================================
# 7. MODEL MISO WSPÓLNY (suma transmitancji per-kanał, L ustalone z etapu
#    przesiewania, dopasowanie WSPÓLNE metodą najmniejszych kwadratów)
# ==========================================================================
def zbuduj_funkcje_miso(wybrane_kanaly):
    """
    wybrane_kanaly: lista (nazwa, u_array, najlepszy_wynik_przesiewania).
    Zwraca (func_miso, p0, granice_dolne, granice_gorne, opis_parametrow)
    - func_miso(X, *params) gdzie X to macierz (n_kanalow, n_probek), params
    to POŁĄCZONE parametry wszystkich kanałów (BEZ L - L ustalone na sztywno
    z etapu przesiewania, korzysta wprost z func_base/popt_bez_L zapisanych
    tam - żadnego odgadywania funkcji po nazwie modelu) + y0 na końcu.
    """
    segmenty = []  # (nazwa, func_bazowa_bez_L_stale, n_param, L_ustalone)
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

    p0.append(0.0)  # y0
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
        pasek.krok("model MISO (wszystkie kanały)")
    return {"y_pred": y_pred, "popt": popt, "opis_param": opis, "segmenty": segmenty, **met}


def analiza_ablacyjna(wybrane_kanaly, y, pelny_wynik, pasek=None):
    """Dla każdego kanału: dopasuj model BEZ NIEGO, zmierz spadek adj R² = wpływ tego kanału."""
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
# 8. WYKRESY (styl zgodny z referencyjnymi skryptami)
# ==========================================================================
def wykres_przesiewania(t, y, u, wyniki, nazwa_kanalu, etykieta_wejscia, plik_png):
    """Jak w idetyfikacja_modele.py: pomiar + nałożone dopasowania >= R2_MIN_PLOT, + panel wejścia."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                                    gridspec_kw={'height_ratios': [3, 1]})
    ax1.plot(t, y, 'k--', label='Dane pomiarowe (HRT)', alpha=0.4, lw=1.2)

    pokazane = [w for w in wyniki if not np.isnan(w.get("r2", np.nan)) and w["r2"] >= R2_MIN_PLOT]
    colors = plt.cm.tab20(np.linspace(0, 1, max(len(wyniki), 1)))
    for i, w in enumerate(pokazane):
        y_pred = w["func"](u, *w["popt"])
        L_info = f" L={w['L']}" if w["L"] else ""
        ax1.plot(t, y_pred, color=colors[i % len(colors)], lw=1.5,
                  label=f"{w['model']}{L_info} (R²={w['r2']:.3f})")

    ax1.set_title(f"Przesiewanie postaci transmitancji — kanał: {nazwa_kanalu}  "
                   f"(pokazane: R² ≥ {R2_MIN_PLOT}, {len(pokazane)}/{len(wyniki)})")
    ax1.legend(loc='lower right', fontsize=7, ncol=2)
    ax1.grid(True, alpha=0.2)
    ax1.set_ylabel("HRT [°C]")

    ax2.plot(t, u, color='steelblue', lw=1.0)
    ax2.fill_between(t, u, color='steelblue', alpha=0.3)
    ax2.set_ylabel(etykieta_wejscia)
    ax2.set_xlabel("Czas")
    ax2.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(plik_png, dpi=150, bbox_inches='tight')
    plt.close(fig)


def wykres_miso(t, y, y_pred, plik_png, tytul):
    """Styl ciemny jak w idetyfikacja_modelu_temperatrua_poweitrza.py."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                                    gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#0f1117')
    for ax in (ax1, ax2):
        ax.set_facecolor('#181c27')
        ax.tick_params(colors='#aab4c8', labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor('#2a3045')

    ax1.plot(t, y, color='#e8eaf6', lw=1.2, alpha=0.75, label='HRT (pomiar)')
    ax1.plot(t, y_pred, color='#4fc3f7', lw=1.5, alpha=0.9, label='HRT (model MISO)')
    ax1.set_ylabel("HRT [°C]", color='#aab4c8')
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
    """Wykres słupkowy wpływu każdego kanału (spadek R² po jego usunięciu z modelu MISO)."""
    nazwy = [a["kanal"] for a in ablacja]
    delty = [a["delta_r2"] for a in ablacja]
    colors = plt.cm.tab20(np.linspace(0, 1, len(nazwy)))

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(nazwy, delty, color=colors)
    ax.set_xlabel("ΔR² (spadek dopasowania po usunięciu kanału z modelu MISO)")
    ax.set_title("Wpływ poszczególnych parametrów na model MISO")
    ax.grid(True, axis='x', alpha=0.3)
    plt.tight_layout()
    plt.savefig(plik_png, dpi=150, bbox_inches='tight')
    plt.close(fig)


# ==========================================================================
# 9. GŁÓWNY PRZEBIEG
# ==========================================================================
def main():
    print("=" * 90)
    print("IDENTYFIKACJA MISO - dodatkowy skrypt (nie modyfikuje skryptów referencyjnych)")
    print("=" * 90)

    df_raw, okna = wczytaj_log(LOG_PATH)
    if not okna:
        print("BŁĄD: nie znaleziono żadnego okna testu skokowego (IndOn) w logu - przerywam.")
        return
    df_raw = wczytaj_i_dolacz_pogode_zewnetrzna(df_raw)
    ma_pogode_zewnetrzna = 'WIATR' in df_raw.columns

    # --- kanał MOCY: dane z OKIEN testu skokowego (tam gdzie PWRL jest mierzone) ---
    a, b = okna[0]
    df_moc = df_raw[(df_raw['Timestamp'] >= a) & (df_raw['Timestamp'] <= b)].copy()
    df_moc = resampluj(df_moc, RESAMPLE_S).dropna().reset_index(drop=True)
    df_moc['PWR'] = df_moc['PWRL1'].fillna(0) + df_moc['PWRL2'].fillna(0)
    u_moc = (df_moc['PWR'] > 0).astype(float).to_numpy()
    y_moc = df_moc['HRT'].to_numpy()
    t_moc = df_moc['Timestamp'].to_numpy()

    # --- kanały POGODOWE: PEŁEN log, Z WYŁĄCZENIEM dni testu skokowego (żeby
    # nie mylić efektu mocy z efektem pogody - w oknach IndOn moc jest znana,
    # ale POZA nimi moc NIE JEST LOGOWANA, więc może być niezerowa i
    # niezaobserwowana - używamy tylko dni bez żadnego zdarzenia IndOn).
    # WAŻNE: resampling NAJPIERW na PEŁNYM, ciągłym logu (CRT/HRT/AT/DPT/RH/
    # PRESS SĄ logowane normalnie również w dni testu skokowego - tylko
    # PWRL nie jest), a dopiero POTEM wykluczamy dni testu z wyniku. Gdyby
    # zrobić to w odwrotnej kolejności (wyklucz -> resampluj), interpolacja
    # (np.interp) próbowałaby wypełnić powstałą ~24h dziurę PROSTĄ LINIĄ
    # między ostatnim punktem przed i pierwszym po wykluczonym dniu - sztucznie
    # "wymyślając" dane tam, gdzie realnie nic nie brakuje (CRT/HRT/AT SĄ
    # zmierzone w te dni, tylko je świadomie pomijamy z powodu nieznanej mocy).
    df_pog = resampluj(df_raw, RESAMPLE_S)
    maska_dni_skoku = pd.Series(False, index=df_pog.index)
    for a, b in okna:
        dzien_a, dzien_b = a.normalize(), b.normalize()
        maska_dni_skoku |= (df_pog['Timestamp'].dt.normalize() >= dzien_a) & (df_pog['Timestamp'].dt.normalize() <= dzien_b)
    df_pog = df_pog[~maska_dni_skoku].copy()
    # PWRL1/PWRL2 są NaN tu CELOWO (moc nie jest logowana poza oknami testu
    # skokowego) - dropna TYLKO po kolumnach faktycznie używanych do
    # identyfikacji kanałów pogodowych, nie po całym wierszu.
    kolumny_wymagane_pog = ['CRT', 'HRT', 'AT', 'DPT', 'RH', 'PRESS', 'PRECIP', 'SNOW']
    if ma_pogode_zewnetrzna:
        kolumny_wymagane_pog += ['WIATR', 'NASLONECZNIENIE']
    df_pog = df_pog.dropna(subset=kolumny_wymagane_pog).reset_index(drop=True)
    # Ograniczenie (udokumentowane, nie naprawiane - wpływ marginalny wobec
    # wysokiego R² uzyskanego mimo to): po wycięciu dni testu skokowego w
    # danych zostają 2 rzeczywiste nieciągłości czasowe (~24h każda). get_sim
    # (lfilter) traktuje tablicę jako RÓWNOMIERNĄ siatkę czasu - w 2 miejscach
    # zszycia licznik czasu "przeskakuje" mimo że fizycznie minęła doba, co
    # może dać krótkotrwały artefakt w symulacji tuż po każdym zszyciu
    # (rząd pojedynczych stałych czasowych modelu, czyli od kilkunastu minut
    # do ~kilku godzin z ~19 dni użytych danych - pomijalne wobec uzyskanego
    # R²).
    t_pog = df_pog['Timestamp'].to_numpy()
    y_pog = df_pog['HRT'].to_numpy()

    print(f"\nDane kanału MOCY: {len(df_moc)} próbek (okno {okna[0][0]} -> {okna[0][1]}).")
    print(f"Dane kanałów POGODOWYCH: {len(df_pog)} próbek (dni bez testu skokowego).")

    # --- WAŻNE: ile w tych danych jest w ogóle momentów, gdy grzanie jest
    # ZNANE/aktywne? Model MISO (z kanałem mocy) jest wiarygodny TYLKO w
    # oknie, gdzie moc jest logowana - to trzeba jawnie pokazać, żeby nie
    # sugerować skuteczności "w całości" tam, gdzie faktycznie nie mamy o
    # grzaniu żadnej informacji. ---
    calkowity_czas_s = (df_raw['Timestamp'].max() - df_raw['Timestamp'].min()).total_seconds()
    czas_z_moca_s = sum((b - a).total_seconds() for a, b in okna)
    print("\n" + "=" * 78)
    print("ILE JEST W TYCH DANYCH MOMENTÓW, GDZIE GRZANIE JEST ZNANE?")
    print(f"  Cały log:                         {calkowity_czas_s / 86400:.2f} dni")
    print(f"  Moc (PWRL) w ogóle LOGOWANA:       {czas_z_moca_s / 60:.1f} min "
          f"= {czas_z_moca_s / calkowity_czas_s * 100:.3f}% całego logu")
    for a, b in okna:
        sub = df_raw[(df_raw['Timestamp'] >= a) & (df_raw['Timestamp'] <= b)]
        pwr = sub['PWRL1'].fillna(0) + sub['PWRL2'].fillna(0)
        aktywne = int((pwr > 0).sum())
        print(f"    okno {a.date()}: grzanie AKTYWNE (PWR>0) w {aktywne}/{len(sub)} "
              f"= {aktywne / max(len(sub), 1) * 100:.1f}% próbek TEGO okna (cały czas praktycznie załączone - "
              f"to wymuszony test skokowy, nie ma tu fazy 'wyłączone')")
    print(f"  Reszta logu ({(calkowity_czas_s - czas_z_moca_s) / 86400:.2f} dni, "
          f"{(calkowity_czas_s - czas_z_moca_s) / calkowity_czas_s * 100:.1f}%): stan grzania "
          f"NIEZNANY (niezalogowany poza trybem ręcznym IndOn).")
    print("  WNIOSEK: model MISO z kanałem mocy (niżej) jest wiarygodny WYŁĄCZNIE")
    print("  w tym krótkim oknie testu skokowego. Zachowanie w DŁUGIM okresie")
    print("  (tygodnie, gdy moc nie jest znana) opisuje OSOBNY model, wyłącznie")
    print("  na podstawie pogody (bez mocy) - patrz sekcja 'MODEL DŁUGOTERMINOWY' niżej.")
    print("=" * 78)

    kanaly_pogodowe = {
        'AT': df_pog['AT'].to_numpy(),
        'DPT': df_pog['DPT'].to_numpy(),
        'RH': df_pog['RH'].to_numpy(),
        'PRESS': df_pog['PRESS'].to_numpy(),
    }
    if ma_pogode_zewnetrzna:
        # WIATR/NASŁONECZNIENIE - z Open-Meteo dla dokładnej lokalizacji szyny
        # (urządzenie ich nie mierzy) - patrz wczytaj_i_dolacz_pogode_zewnetrzna.
        kanaly_pogodowe['WIATR'] = df_pog['WIATR'].to_numpy()
        kanaly_pogodowe['NASLONECZNIENIE'] = df_pog['NASLONECZNIENIE'].to_numpy()
    # PRECIP/SNOW - dołącz TYLKO jeśli mają jakąkolwiek wariancję (inaczej dopasowanie MNK jest bez sensu)
    for nazwa in ('PRECIP', 'SNOW'):
        kol = df_pog[nazwa].to_numpy()
        if np.nanstd(kol) > 1e-9:
            kanaly_pogodowe[nazwa] = kol
        else:
            print(f"UWAGA: kanał {nazwa} jest stały (brak wariancji w danych) - pominięty w identyfikacji.")

    # --- policz łączną liczbę kroków (pasek postępu) ---
    moc_bez_L, moc_z_L = modele_mocy()
    pog_bez_L, pog_z_L = modele_pogodowe()
    total_kroki = len(moc_bez_L) + len(moc_z_L)
    total_kroki += len(kanaly_pogodowe) * (len(pog_bez_L) + len(pog_z_L))
    total_kroki += 1  # MISO
    total_kroki += len(kanaly_pogodowe) + 1  # ablacja (moc + każdy kanał pogodowy)
    pasek = PasekPostepu(total_kroki, etykieta="Identyfikacja")

    # --- przesiewanie: MOC ---
    print("\n--- Przesiewanie: kanał MOCY (PWR -> HRT) ---")
    wyniki_moc = przesiej_kanal("PWR", u_moc, y_moc, moc_bez_L, moc_z_L,
                                 L_SEARCH_MIN_MOC, L_SEARCH_MAX_MOC, L_SEARCH_STEP_MOC, pasek)
    najlepszy_moc = max(wyniki_moc, key=lambda w: w["adj_r2"])
    wykres_przesiewania(t_moc, y_moc, u_moc, wyniki_moc, "PWR (moc grzania)",
                         "Moc [1=załączona]", os.path.join(OUTPUT_DIR, "przesiewanie_PWR.png"))

    # --- przesiewanie: kanały pogodowe ---
    wszystkie_wyniki_pogodowe = {}
    for nazwa, u_k in kanaly_pogodowe.items():
        print(f"\n--- Przesiewanie: kanał {nazwa} -> HRT ---")
        w = przesiej_kanal(nazwa, u_k, y_pog, pog_bez_L, pog_z_L,
                            L_SEARCH_MIN_POG, L_SEARCH_MAX_POG, L_SEARCH_STEP_POG, pasek)
        wszystkie_wyniki_pogodowe[nazwa] = w
        najlepszy = max(w, key=lambda x: x["adj_r2"])
        wykres_przesiewania(t_pog, y_pog, u_k, w, nazwa, nazwa,
                             os.path.join(OUTPUT_DIR, f"przesiewanie_{nazwa}.png"))
        print(f"\n  Najlepszy dla {nazwa}: {najlepszy['model']} (adj R²={najlepszy['adj_r2']:.4f})")

    pasek.zakoncz()

    # --- MODEL DŁUGOTERMINOWY: jak model zachowuje się w DŁUGIM okresie (całe
    # ~19-21 dni logu), NIE tylko w krótkim oknie testu skokowego, gdzie moc
    # jest znana - patrz "ILE JEST W TYCH DANYCH MOMENTÓW..." wyżej. Model
    # MISO z kanałem mocy da się dopasować/zweryfikować TYLKO na 162 minutach
    # (0.5% logu) - to, co się dzieje przez pozostałe ~21 dni, opisuje
    # WYŁĄCZNIE najlepszy kanał pogodowy (moc w tym czasie nieznana, więc nie
    # wchodzi do tego modelu). UWAGA interpretacyjna: to dopasowanie łapie
    # zachowanie CAŁEGO układu zamkniętego (pogoda -> ewentualne automatyczne
    # grzanie -> HRT), NIE czystej fizyki szyny bez grzania - bo nie wiemy,
    # czy/kiedy grzanie automatyczne było w tym czasie aktywne.
    nazwa_dlugoterminowa = max(wszystkie_wyniki_pogodowe,
                                key=lambda n: max(w["adj_r2"] for w in wszystkie_wyniki_pogodowe[n]))
    najlepszy_dlugoterminowy = max(wszystkie_wyniki_pogodowe[nazwa_dlugoterminowa], key=lambda w: w["adj_r2"])
    u_dlugoterminowy = kanaly_pogodowe[nazwa_dlugoterminowa]
    y_pred_dlugoterminowy = najlepszy_dlugoterminowy["func"](u_dlugoterminowy, *najlepszy_dlugoterminowy["popt"])
    rozpietosc_dni = (t_pog[-1] - t_pog[0]).astype('timedelta64[s]').astype(float) / 86400.0

    print("\n" + "=" * 78)
    print("MODEL DŁUGOTERMINOWY (bez kanału mocy - moc nieznana poza oknem testu)")
    print(f"  Rozpiętość danych: {rozpietosc_dni:.1f} dni ({len(df_pog)} próbek)")
    print(f"  Najlepszy kanał:   {nazwa_dlugoterminowa} / model {najlepszy_dlugoterminowy['model']}")
    print(f"  R²={najlepszy_dlugoterminowy['r2']:.4f}  adj R²={najlepszy_dlugoterminowy['adj_r2']:.4f}  "
          f"RMSE={najlepszy_dlugoterminowy['rmse']:.4f}°C")
    print("  UWAGA: to dopasowanie opisuje zachowanie CAŁEGO układu zamkniętego")
    print("  (pogoda -> ew. automatyczne grzanie -> HRT), NIE czystej fizyki bez")
    print("  grzania - stan grzania w tym okresie jest nieznany (patrz wyżej).")
    print("=" * 78)

    wykres_miso(t_pog, y_pog, y_pred_dlugoterminowy,
                os.path.join(OUTPUT_DIR, "model_dlugoterminowy.png"),
                f"Model DŁUGOTERMINOWY (bez mocy - nieznana poza testem skokowym) — "
                f"{rozpietosc_dni:.0f} dni — kanał {nazwa_dlugoterminowa}/{najlepszy_dlugoterminowy['model']} — "
                f"R²={najlepszy_dlugoterminowy['r2']:.4f}, RMSE={najlepszy_dlugoterminowy['rmse']:.3f}°C")

    # --- tabela zbiorcza wszystkich przesiewań ---
    wiersze = []
    for w in wyniki_moc:
        wiersze.append({"kanal": w["kanal"], "model": w["model"], "typ": w["typ"],
                         "R2": w.get("r2"), "adj_R2": w.get("adj_r2"), "AIC": w.get("aic"),
                         "RMSE": w.get("rmse"), "L": w.get("L"),
                         "parametry": np.round(w["popt"], 4).tolist() if w.get("popt") is not None else None})
    for nazwa, w_lista in wszystkie_wyniki_pogodowe.items():
        for w in w_lista:
            wiersze.append({"kanal": w["kanal"], "model": w["model"], "typ": w["typ"],
                             "R2": w.get("r2"), "adj_R2": w.get("adj_r2"), "AIC": w.get("aic"),
                             "RMSE": w.get("rmse"), "L": w.get("L"),
                             "parametry": np.round(w["popt"], 4).tolist() if w.get("popt") is not None else None})
    df_tabela = pd.DataFrame(wiersze)

    # --- wybór kanałów do modelu MISO: moc (zawsze) + kanały pogodowe z adj_R² > 0.05 ---
    # WAŻNE ZABEZPIECZENIE przed współliniowością: kanał pogodowy dostał dobre
    # adj_R² na DŁUGIM (19-dniowym) oknie, ale model MISO jest dopasowywany na
    # KRÓTKIM (80-min) oknie testu skokowego - jeśli w TYM krótkim oknie kanał
    # jest praktycznie STAŁY (np. nasłonecznienie już w pełni "nasycone" o
    # poranku testu, wariancja <5% jego pełnej skali), model nie ma jak
    # odróżnić jego wpływu od wpływu mocy (też ~stałej w tym oknie - to czysty
    # skok) - dopasowanie wspólne wtedy fałszywie "przepisuje" część efektu
    # mocy na ten kanał (zaobserwowane: ΔR² mocy spadło z 0.237 do 0.019 po
    # dodaniu nasłonecznienia, mimo że moc fizycznie DOMINUJE ogrzewanie szyny
    # w 80 minut - ewidentny artefakt, nie realny wynik). Taki kanał zostaje
    # WYŁĄCZONY z modelu MISO (ale jego SAMODZIELNY wynik z długiego okna
    # pozostaje w tabeli/wykresach - to wciąż ważna, wiarygodna informacja).
    PROG_WLACZENIA_MISO = 0.05
    PROG_MIN_WARIANCJI_W_OKNIE = 0.05  # min. 5% pełnej (długoterminowej) zmienności w krótkim oknie
    wybrane_kanaly_do_miso = [("PWR", u_moc, najlepszy_moc)]
    for nazwa, w_lista in wszystkie_wyniki_pogodowe.items():
        najlepszy = max(w_lista, key=lambda x: x["adj_r2"])
        if najlepszy["adj_r2"] <= PROG_WLACZENIA_MISO:
            continue
        # UWAGA: model MISO liczony jest na oknie testu skokowego (gdzie
        # znana jest moc) - potrzebujemy więc wartości tego kanału pogodowego
        # W TYM SAMYM oknie co df_moc, nie w oknie pogodowym df_pog.
        u_w_oknie_miso = df_moc[nazwa].to_numpy()
        std_dlugoterminowy = np.std(kanaly_pogodowe[nazwa])
        std_w_oknie = np.std(u_w_oknie_miso)
        if std_dlugoterminowy > 1e-9 and (std_w_oknie / std_dlugoterminowy) < PROG_MIN_WARIANCJI_W_OKNIE:
            print(f"  UWAGA: {nazwa} pominięty w MISO - w oknie testu skokowego prawie "
                  f"STAŁY (odchylenie std {std_w_oknie:.2f} = "
                  f"{std_w_oknie / std_dlugoterminowy * 100:.1f}% jego długoterminowej zmienności) - "
                  f"współliniowy z mocą (też stałą w tym oknie), dołączenie fałszywie "
                  f"'kradnie' wpływ mocy. Jego samodzielny wynik z długiego okna zostaje w tabeli.")
            continue
        wybrane_kanaly_do_miso.append((nazwa, u_w_oknie_miso, najlepszy))

    print("\n--- Budowa wspólnego modelu MISO ---")
    print("Kanały włączone do modelu MISO (adj R² SISO > "
          f"{PROG_WLACZENIA_MISO}): {[k[0] for k in wybrane_kanaly_do_miso]}")

    try:
        wynik_miso = dopasuj_miso(wybrane_kanaly_do_miso, y_moc, pasek)
        wykres_miso(t_moc, y_moc, wynik_miso["y_pred"],
                    os.path.join(OUTPUT_DIR, "model_MISO.png"),
                    f"Model MISO — R²={wynik_miso['r2']:.4f}, adj R²={wynik_miso['adj_r2']:.4f}, "
                    f"RMSE={wynik_miso['rmse']:.3f}°C  (kanały: {', '.join(k[0] for k in wybrane_kanaly_do_miso)})")

        print(f"\nMODEL MISO: R²={wynik_miso['r2']:.4f}  adj R²={wynik_miso['adj_r2']:.4f}  "
              f"RMSE={wynik_miso['rmse']:.4f}°C  AIC={wynik_miso['aic']:.2f}")

        ablacja = analiza_ablacyjna(wybrane_kanaly_do_miso, y_moc, wynik_miso, pasek)
        wykres_wplywu(ablacja, os.path.join(OUTPUT_DIR, "wplyw_parametrow.png"))

        print("\nWPŁYW PARAMETRÓW NA MODEL MISO (ΔR² po usunięciu kanału, malejąco):")
        for a in ablacja:
            print(f"  {a['kanal']:<8} ΔR²={a['delta_r2']:.4f}  Δadj R²={a['delta_adj_r2']:.4f}")

        df_ablacja = pd.DataFrame(ablacja)
    except Exception as e:
        print(f"BŁĄD przy budowie modelu MISO: {e}")
        wynik_miso = None
        df_ablacja = pd.DataFrame()

    pasek.zakoncz()

    # --- zapis wyników ---
    sciezka_csv = os.path.join(OUTPUT_DIR, "wyniki_identyfikacji_miso.csv")
    df_tabela.to_csv(sciezka_csv, index=False, encoding='utf-8-sig')
    sciezka_ablacja_csv = os.path.join(OUTPUT_DIR, "wplyw_parametrow.csv")
    df_ablacja.to_csv(sciezka_ablacja_csv, index=False, encoding='utf-8-sig')

    try:
        sciezka_xlsx = os.path.join(OUTPUT_DIR, "wyniki_identyfikacji_miso.xlsx")
        with pd.ExcelWriter(sciezka_xlsx, engine='openpyxl') as writer:
            df_tabela.to_excel(writer, sheet_name='Przesiewanie_SISO', index=False)
            df_ablacja.to_excel(writer, sheet_name='Wplyw_parametrow_MISO', index=False)
            if wynik_miso is not None:
                pd.DataFrame({
                    'metryka': ['R2', 'adj_R2', 'RMSE', 'MAE', 'AIC'],
                    'wartosc': [wynik_miso['r2'], wynik_miso['adj_r2'], wynik_miso['rmse'],
                                wynik_miso['mae'], wynik_miso['aic']],
                }).to_excel(writer, sheet_name='Model_MISO_podsumowanie', index=False)
        print(f"\nZapisano Excel: {sciezka_xlsx}")
    except ImportError:
        print("\nUWAGA: openpyxl niedostępny - zapisano tylko CSV (bez .xlsx).")

    print(f"Zapisano tabelę: {sciezka_csv}")
    print(f"Zapisano wpływ parametrów: {sciezka_ablacja_csv}")
    print(f"Wykresy zapisane w: {OUTPUT_DIR}")
    print("\nGOTOWE.")


if __name__ == "__main__":
    main()
