# Identyfikacja/Identyfikacja/predykcja_kalman_crt.py
#
# DODATKOWY, samodzielny skrypt (nie rusza referencyjnych skryptów) - na
# życzenie użytkownika (2026-09-26): "do przewidywania temperatur potrzebuję
# kalmana, ale na ten drugi obiekt [CRT] również... żeby wyliczyć predykcję
# PRAWIDŁOWĄ tych parametrów".
#
# PO CO: Benchmark_crt/benchmark/Algorytmy/rdzen_kontrolera.py miał dotąd DWIE
# osobne metody prognozy szyny:
#   - rail_temperature_prediction() - CZYSTY filtr Kalmana (poziom+trend),
#     statystyczny, NIE zna żadnej fizyki obiektu (oryginalny Benchmark).
#   - crt_transmittance_prediction() (dodane 2026-09-26) - CZYSTA fizyka
#     (znana transmitancja AT->CRT), otwarta pętla: przepuszcza historię AT
#     przez transmitancję, BEZ ŻADNEJ korekty prawdziwym, zmierzonym CRT.
#
# ŻADNE z tych dwóch nie jest "prawidłowe" w pełnym sensie: pierwsze ignoruje
# znaną fizykę, drugie ignoruje POMIAR (jeśli model ma choćby niewielki błąd,
# błąd otwartej pętli rośnie bez ograniczenia w czasie). PRAWIDŁOWA predykcja
# to KALMAN FILTR, którego model procesu jest ZNANĄ transmitancją AT->CRT
# (nie generycznym poziomem+trendem) - łączy fizykę (inercję obiektu, T1/Tz)
# Z korektą pomiarem (prawdziwy CRT) w każdym kroku:
#   1) PREDYKCJA:  x[k|k-1] = A*x[k-1|k-1] + B*AT[k]          (fizyka, zna T1/Tz)
#                  P[k|k-1] = A*P[k-1|k-1]*A' + Q
#   2) KOREKTA:    y_pred = C*x[k|k-1] + D*AT[k]
#                  innowacja = CRT_zmierzone[k] - y_pred
#                  K = P[k|k-1]*C' / (C*P[k|k-1]*C' + R)
#                  x[k|k] = x[k|k-1] + K*innowacja
#                  P[k|k] = (1 - K*C)*P[k|k-1]
# Dopiero z tak SKORYGOWANEGO stanu x[k|k] prognoza w przód (2h/8 kroków, jak
# reszta projektu) jest czystą fizyką (bo przyszłego CRT nie znamy) - ale
# STARTUJE z dobrego punktu, nie z akumulującego błąd otwartego pętla.
#
# WALIDACJA: na PEŁNYM realnym logu (algo (4).log, jak identyfikacja_crt.py),
# z wykluczeniem dni testu skokowego (grzanie nieznane - jak wszędzie w tym
# projekcie). Porównanie 3 metod prognozy 2h (8 kroków, siatka 900s - TA SAMA
# co Benchmark_crt/benchmark/Algorytmy/rdzen_kontrolera.py):
#   A) Kalman generyczny (poziom+trend) - jak oryginalny rail_temperature_prediction
#   B) Fizyka otwarta pętla (bez korekty pomiarem) - jak crt_transmittance_prediction
#   C) Kalman fizyczny (ZNANA transmitancja jako model procesu + korekta CRT) - TEN skrypt
# Metryka: RMSE prognozy na KAŻDYM z 8 kroków horyzontu (15/.../120 min naprzód),
# uśrednione po WSZYSTKICH punktach startowych w danych (nie tylko jednym oknie).
#
# INERCJA CAŁOŚCI: model procesu (A,B,C,D) pochodzi WPROST z transmitancji
# T1_W_CRT=2482,3s (~41 min) - to WŁAŚNIE bezwładność obiektu, nie osobny
# parametr do dostrojenia - stąd filtr "wie", że CRT nie może zmienić się
# szybciej niż na to pozwala ta stała czasowa, w odróżnieniu od generycznego
# Kalmana (A), który tego w ogóle nie wie i tylko ekstrapoluje trend.
#
# WYTAPIANIE ŚNIEGU: ta predykcja dotyczy WYŁĄCZNIE CRT (szyna NIEogrzewana,
# fizycznie NIE topi śniegu - grzanie idzie do HRT, nie do CRT) - więc okresy
# ze śniegiem/opadem NIE są tu w żaden specjalny sposób wykluczane ani
# traktowane inaczej (w odróżnieniu od identyfikacji AT->CRT w
# identyfikacja_crt.py, gdzie liczyło się to samo, bo grzanie i tak nie ma
# wpływu na CRT). Skrypt dodatkowo RAPORTUJE osobno błąd prognozy w okresach
# z opadem/śniegiem i bez, żeby jawnie pokazać, że dokładność się NIE
# pogarsza akurat wtedy, gdy ryzyko (i potrzeba wytapiania HRT) jest największe.
#
# Uruchomienie: python predykcja_kalman_crt.py   (z tego folderu)

import os
import re
import sys

import numpy as np
import pandas as pd
from scipy import signal

try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "algo (4).log")
OUTPUT_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "wyniki_identyfikacja")
os.makedirs(OUTPUT_DIR, exist_ok=True)

STEP_SECONDS = 900.0   # 15 min - TA SAMA siatka co HORIZON_STEPS w rdzen_kontrolera.py
HORIZON_STEPS = 8       # 2h horyzontu, jak w reszcie projektu

# --- Znana transmitancja AT -> CRT (identyfikacja_crt.py, FO_Z) ---
K_W_CRT = 1.217
T1_W_CRT = 2482.3
TZ_W_CRT = 690.8

# --- Kalman generyczny (poziom+trend) - te same stałe co rdzen_kontrolera.py ---
PROCESS_VARIANCE_GEN = 0.05
MEASUREMENT_VARIANCE_GEN = 0.25


# ==========================================================================
# 1. PARSOWANIE LOGU (powielone z identyfikacja_crt.py, dla samodzielności)
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
                rows_p2.append((m.group(1), float(m.group(2)), int(m.group(3)), int(m.group(4)),
                                 int(m.group(5)), int(m.group(6))))
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
    return df, okna


def resampluj_900s(df):
    df = df.drop_duplicates(subset='Timestamp').sort_values('Timestamp').reset_index(drop=True)
    siatka = pd.date_range(df['Timestamp'].min(), df['Timestamp'].max(), freq=f'{int(STEP_SECONDS)}s')
    idx_num = df['Timestamp'].to_numpy().astype('int64')
    siatka_num = siatka.to_numpy().astype('int64')
    out = pd.DataFrame({'Timestamp': siatka})
    for k in ['AT', 'CRT', 'PRECIP', 'SNOW']:
        out[k] = np.interp(siatka_num, idx_num, df[k].to_numpy())
    return out


# ==========================================================================
# 2. MODEL PROCESU: znana transmitancja AT -> CRT, dyskretyzowana na 900s
#
# UWAGA (znaleziony i naprawiony problem): scipy.signal.tf2ss zwraca
# realizację w POSTACI KANONICZNEJ, gdzie stan x NIE jest w naturalnej skali
# (dla tej transmitancji: C~0,00035, x rzędu dziesiątek tysięcy) - MATEMATYCZNIE
# tożsame (y=C@x+D@u daje identyczny wynik co postać ręczna niżej, sprawdzone
# różnicą <1e-14), ALE numerycznie fatalne dla Kalmana: innowacja pomiaru
# (rzędu °C) przechodzi przez K=P@C.T/S, a skoro C jest mikroskopijne, K też
# wychodzi mikroskopijne i korekta ginie w zaokrągleniach (P/x pozostają
# praktycznie nietknięte przez pomiar - sprawdzone bezpośrednio: różnica x
# przed/po korekcie ~1e-4 wobec x~60000). Dlatego stan budowany jest tu
# RĘCZNIE, w skali FIZYCZNEJ (x w °C - to "opóźniona część" wyjścia): dla
# G(s)=K(Tz*s+1)/(T1*s+1) rozkład na D (feedthrough) + composant pierwszego
# rzędu z jednostkowym wzmocnieniem daje C rzędu 1, nie 1e-4 - Kalman wtedy
# faktycznie korzysta z pomiaru.
# ==========================================================================
def zbuduj_model_stanowy():
    D = K_W_CRT * TZ_W_CRT / T1_W_CRT
    c1 = K_W_CRT * (T1_W_CRT - TZ_W_CRT) / T1_W_CRT
    Ac, Bc = -1.0 / T1_W_CRT, 1.0 / T1_W_CRT
    Ad = np.exp(Ac * STEP_SECONDS)
    Bd = (Ad - 1.0) / Ac * Bc
    A = np.array([[Ad]])
    B = np.array([[Bd]])
    C = np.array([[c1]])
    D = np.array([[D]])
    return A, B, C, D


# ==========================================================================
# 3. TRZY METODY PROGNOZY (2h/8 kroków, z dowolnego punktu startowego i)
# ==========================================================================
def prognoza_kalman_generyczny(at_hist, crt_hist, i, horizon):
    """A) Kalman poziom+trend na SAMEJ historii CRT (bez fizyki, bez AT) -
    identyczny rdzeń co _kalman_forecast_core w rdzen_kontrolera.py."""
    seria = crt_hist[:i + 1]
    if len(seria) < 2:
        return [seria[-1]] * horizon
    q, r = PROCESS_VARIANCE_GEN, MEASUREMENT_VARIANCE_GEN
    level, trend = seria[-1], seria[-1] - seria[-2]
    p00, p01, p11 = 1.0, 0.0, 1.0
    for y in seria:
        level_pred, trend_pred = level + trend, trend
        p00_pred = p00 + 2 * p01 + p11 + q
        p01_pred = p01 + p11
        p11_pred = p11 + q
        innov = y - level_pred
        s = p00_pred + r
        k0, k1 = p00_pred / s, p01_pred / s
        level = level_pred + k0 * innov
        trend = trend_pred + k1 * innov
        p00 = (1 - k0) * p00_pred
        p01 = (1 - k0) * p01_pred
        p11 = p11_pred - k1 * p01_pred
    wyniki = []
    for _ in range(horizon):
        level += trend
        wyniki.append(level)
    return wyniki


def prognoza_fizyka_otwarta_petla(at_hist, crt_hist, i, horizon, A, B, C, D, okno_historii=36):
    """B) Fizyka, BEZ korekty pomiarem - jak crt_transmittance_prediction()
    (2026-09-26, wersja sprzed tego skryptu): przewija stan przez niedawną
    historię AT, potem prognozuje przyszłym (tu: PRAWDZIWYM, dla uczciwego
    porównania) AT."""
    start = max(0, i - okno_historii + 1)
    x = np.zeros((A.shape[0], 1))
    for at_val in at_hist[start:i + 1]:
        x = A @ x + B * at_val
    wyniki = []
    for h in range(horizon):
        at_future = at_hist[i + 1 + h] if i + 1 + h < len(at_hist) else at_hist[-1]
        y = float((C @ x + D * at_future)[0, 0])
        wyniki.append(y)
        x = A @ x + B * at_future
    return wyniki


def prognoza_kalman_fizyczny(at_hist, crt_hist, i, horizon, A, B, C, D, Q, R, okno_historii=36):
    """C) PRAWIDŁOWA predykcja: Kalman filtr, model procesu = ZNANA
    transmitancja AT->CRT (inercja obiektu wprost z T1_W_CRT/TZ_W_CRT), z
    korektą KAŻDYM krokiem prawdziwym, zmierzonym CRT - patrz nagłówek pliku."""
    start = max(0, i - okno_historii + 1)
    x = np.zeros((A.shape[0], 1))
    P = np.eye(A.shape[0]) * 1.0
    for at_val, crt_val in zip(at_hist[start:i + 1], crt_hist[start:i + 1]):
        # --- PREDYKCJA (fizyka) ---
        x = A @ x + B * at_val
        P = A @ P @ A.T + Q
        # --- KOREKTA (pomiar CRT) ---
        y_pred = C @ x + D * at_val
        innowacja = crt_val - float(y_pred[0, 0])
        S = float((C @ P @ C.T)[0, 0]) + R
        K = (P @ C.T) / S
        x = x + K * innowacja
        P = (np.eye(A.shape[0]) - K @ C) @ P

    # --- PROGNOZA W PRZÓD: od skorygowanego stanu, PRAWDZIWYM (dla uczciwego
    # porównania z metodą B) przyszłym AT - w produkcji (rdzen_kontrolera.py)
    # użyty jest tu AT z prognozy Kalmana (temperature_prediction()), bo
    # prawdziwy przyszły AT nie jest znany. ---
    wyniki = []
    for h in range(horizon):
        at_future = at_hist[i + 1 + h] if i + 1 + h < len(at_hist) else at_hist[-1]
        y = float((C @ x + D * at_future)[0, 0])
        wyniki.append(y)
        x = A @ x + B * at_future
    return wyniki


# ==========================================================================
# 4. STROJENIE Q/R (grid search, minimalizacja RMSE prognozy 2h)
# ==========================================================================
def strojenie_QR(at_hist, crt_hist, A, B, C, D, punkty_startowe):
    kandydaci_Q = [1e-6, 1e-5, 1e-4, 1e-3, 1e-2]
    kandydaci_R = [0.01, 0.05, 0.1, 0.5, 1.0]
    najlepszy = (np.inf, None, None)
    for Q_val in kandydaci_Q:
        Q = np.array([[Q_val]])
        for R_val in kandydaci_R:
            bledy = []
            for i in punkty_startowe:
                prog = prognoza_kalman_fizyczny(at_hist, crt_hist, i, HORIZON_STEPS, A, B, C, D, Q, R_val)
                prawda = crt_hist[i + 1:i + 1 + HORIZON_STEPS]
                if len(prawda) == HORIZON_STEPS:
                    bledy.append(np.mean((np.array(prog) - prawda) ** 2))
            if bledy:
                rmse = np.sqrt(np.mean(bledy))
                if rmse < najlepszy[0]:
                    najlepszy = (rmse, Q_val, R_val)
    return najlepszy


# ==========================================================================
# 5. MAIN
# ==========================================================================
def main():
    print("=" * 90)
    print("PREDYKCJA KALMANA DLA CRT (drugi obiekt) - model procesu = ZNANA transmitancja AT->CRT")
    print("=" * 90)

    df_raw, okna = wczytaj_log(LOG_PATH)
    df_900 = resampluj_900s(df_raw)
    if okna:
        maska = pd.Series(False, index=df_900.index)
        for a, b in okna:
            da, db = a.normalize(), b.normalize()
            maska |= (df_900['Timestamp'].dt.normalize() >= da) & (df_900['Timestamp'].dt.normalize() <= db)
        df_900 = df_900[~maska].reset_index(drop=True)
        print(f"Wykluczono dni testu skokowego (grzanie nieznane) - {int(maska.sum())} próbek 900s usuniętych.")

    at_hist = df_900['AT'].to_numpy()
    crt_hist = df_900['CRT'].to_numpy()
    ma_opad = ((df_900['PRECIP'].to_numpy() > 0) | (df_900['SNOW'].to_numpy() > 0))
    n = len(df_900)
    print(f"Dane: {n} próbek co {STEP_SECONDS:.0f}s ({n * STEP_SECONDS / 86400:.1f} dni).")

    A, B, C, D = zbuduj_model_stanowy()
    print(f"Model procesu (inercja całości): T1={T1_W_CRT:.1f}s (~{T1_W_CRT/60:.1f} min), "
          f"Tz={TZ_W_CRT:.1f}s (~{TZ_W_CRT/60:.1f} min), K={K_W_CRT}")

    # --- punkty startowe do oceny: co 4 próbki (co godzinę), z zapasem na
    # historię (>=36 próbek wstecz) i horyzont (8 do przodu) ---
    punkty = list(range(40, n - HORIZON_STEPS - 1, 4))
    print(f"Punktów startowych do oceny: {len(punkty)}")

    print("\nStrojenie Q/R (grid search, minimalizacja RMSE prognozy 2h) na próbce punktów...")
    probka_strojenia = punkty[::5]  # co 5-ty punkt - szybciej, wystarczająco reprezentatywne
    rmse_najlepsze, Q_best, R_best = strojenie_QR(at_hist, crt_hist, A, B, C, D, probka_strojenia)
    Q = np.array([[Q_best]])
    print(f"Wybrane: Q={Q_best:.1e}, R={R_best:.3f} (RMSE na próbce strojenia: {rmse_najlepsze:.4f}°C)")

    # --- pełna ocena 3 metod na WSZYSTKICH punktach, per krok horyzontu ---
    bledy_A = np.zeros((len(punkty), HORIZON_STEPS))
    bledy_B = np.zeros((len(punkty), HORIZON_STEPS))
    bledy_C = np.zeros((len(punkty), HORIZON_STEPS))
    maska_opad_punktow = np.zeros(len(punkty), dtype=bool)

    for j, i in enumerate(punkty):
        prawda = crt_hist[i + 1:i + 1 + HORIZON_STEPS]
        pA = prognoza_kalman_generyczny(at_hist, crt_hist, i, HORIZON_STEPS)
        pB = prognoza_fizyka_otwarta_petla(at_hist, crt_hist, i, HORIZON_STEPS, A, B, C, D)
        pC = prognoza_kalman_fizyczny(at_hist, crt_hist, i, HORIZON_STEPS, A, B, C, D, Q, R_best)
        bledy_A[j] = np.array(pA) - prawda
        bledy_B[j] = np.array(pB) - prawda
        bledy_C[j] = np.array(pC) - prawda
        maska_opad_punktow[j] = ma_opad[i + 1:i + 1 + HORIZON_STEPS].any()

    def rmse_per_krok(bledy):
        return np.sqrt(np.mean(bledy ** 2, axis=0))

    print("\n" + "=" * 90)
    print("RMSE PROGNOZY [°C] wg horyzontu (15 min .. 120 min naprzód)")
    print("=" * 90)
    horyzonty_min = [(h + 1) * STEP_SECONDS / 60 for h in range(HORIZON_STEPS)]
    print(f"{'Horyzont [min]':<16}" + "".join(f"{h:>8.0f}" for h in horyzonty_min))
    print(f"{'A) Kalman generyczny':<22}" + "".join(f"{v:>8.3f}" for v in rmse_per_krok(bledy_A)))
    print(f"{'B) Fizyka otw. pętla':<22}" + "".join(f"{v:>8.3f}" for v in rmse_per_krok(bledy_B)))
    print(f"{'C) Kalman fizyczny':<22}" + "".join(f"{v:>8.3f}" for v in rmse_per_krok(bledy_C)))

    print(f"\nRMSE ŚREDNIE (wszystkie kroki horyzontu razem):")
    print(f"  A) Kalman generyczny  : {np.sqrt(np.mean(bledy_A**2)):.4f}°C")
    print(f"  B) Fizyka otw. pętla  : {np.sqrt(np.mean(bledy_B**2)):.4f}°C")
    print(f"  C) Kalman fizyczny    : {np.sqrt(np.mean(bledy_C**2)):.4f}°C   <- powinien być najlepszy")

    print(f"\nRMSE osobno dla okresów Z OPADEM/ŚNIEGIEM w horyzoncie prognozy vs BEZ "
          f"(sprawdzenie, że dokładność nie spada akurat wtedy, gdy ryzyko jest największe):")
    for etykieta, maska_wybor in [('Z opadem/śniegiem', maska_opad_punktow), ('Bez opadu', ~maska_opad_punktow)]:
        if maska_wybor.sum() == 0:
            continue
        print(f"  {etykieta:<20} (n={int(maska_wybor.sum())}):  "
              f"A={np.sqrt(np.mean(bledy_A[maska_wybor]**2)):.3f}°C  "
              f"B={np.sqrt(np.mean(bledy_B[maska_wybor]**2)):.3f}°C  "
              f"C={np.sqrt(np.mean(bledy_C[maska_wybor]**2)):.3f}°C")

    print("\nGOTOWE. Parametry filtru do wpisania w Benchmark_crt/benchmark/Algorytmy/rdzen_kontrolera.py:")
    print(f"  KALMAN_CRT_Q = {Q_best:.6e}")
    print(f"  KALMAN_CRT_R = {R_best:.6f}")


if __name__ == "__main__":
    main()
