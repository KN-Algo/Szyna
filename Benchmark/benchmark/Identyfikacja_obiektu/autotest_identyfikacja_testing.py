# ==============================================================================
# SKRYPT WALIDACYJNY: jak dobrze "autotest" (skok temperatury + identyfikacja)
# jest w stanie rozpoznać obiekt inercyjny II rzędu z opóźnieniem (SOPDT),
# jeżeli NIE WOLNO nam czekać na pełną stabilizację (limit bezpieczeństwa 40°C).
#
# Ten plik NIE jest częścią sterownika. Służy wyłącznie do sprawdzenia jakości
# identyfikacji, zanim analogiczna logika trafi jako metoda do
# Algorytmy/rdzen_kontrolera.py (metoda KontrolerBazowy.autotest).
#
# ZASADA DZIAŁANIA:
# 1. "Prawdziwym obiektem" jest znany z symulacja_fizyczna.py model transmitancyjny
#    grzałki (K_H, T1_H, T2_H, L_H) - drugi rząd + opóźnienie transportowe.
#    Te wartości służą TYLKO do symulacji rzeczywistości i do policzenia błędu -
#    algorytm identyfikujący ich nie zna (tak jak w prawdziwym sterowniku).
# 2. Symulujemy skok: grzanie 0% -> 100% w chwili t=0 autotestu, a HRT liczymy
#    jako sumę składowej pogodowej (CRT, niezależnej od grzania) i składowej
#    grzewczej. Ponieważ CRT jest mierzone bezpośrednio przez czujnik szyny
#    nieogrzewanej, sygnałem do identyfikacji jest y(t) = HRT(t) - CRT(t),
#    co eliminuje wpływ zmiennej pogody w trakcie testu.
# 3. Test jest ucinany, gdy pierwsze z trzech zdarzeń nastąpi:
#       a) HRT osiąga próg bezpieczeństwa (margines przed twardym limitem 40°C),
#       b) odpowiedź się ustabilizowała (może się zdarzyć zimą - nie ma sensu
#          czekać dłużej, tylko marnujemy czas testu),
#       c) upłynął maksymalny dozwolony czas trwania autotestu.
# 4. Na (możliwie niepełnej) krzywej dopasowywany jest model SOPDT metodą
#    najmniejszych kwadratów (scipy.optimize.curve_fit) i porównywany z
#    prawdziwymi parametrami obiektu.
# ==============================================================================

import os
import sys
import numpy as np
import pandas as pd
from scipy import signal
from scipy.optimize import curve_fit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from symulacja_fizyczna import wczytaj_pogode_1s  # noqa: E402 - wspólny, ogólny wczytywacz pogody (dowolna rozdzielczość źródła)

# ==============================================================================
# 1. "PRAWDZIWY" OBIEKT (te same wartości co w main_test.py)
# ==============================================================================
K_W = 1.09075872
T1_W = 5771.977521
TZ_W = 780.0337376

K_H_TRUE = 51.1163668
T1_H_TRUE = 1120.914508
T2_H_TRUE = 2450.968465
L_H_TRUE = 1194.184089

tf_weather = signal.TransferFunction([K_W * TZ_W, K_W], [T1_W, 1])
tf_heating_true = signal.TransferFunction(
    [K_H_TRUE * 0.0, K_H_TRUE], np.polymul([T1_H_TRUE, 1], [T2_H_TRUE, 1]).tolist()
)

# ==============================================================================
# 2. PARAMETRY BEZPIECZEŃSTWA I ZATRZYMANIA AUTOTESTU
# ==============================================================================
DT = 1.0                          # Krok symulacji [s] (dane wejściowe są już 1-sekundowe).
HARD_MAX_HRT_C = 40.0              # Twardy limit konstrukcyjny szyny ogrzewanej.
SAFETY_MARGIN_C = 2.0              # Zapas na bezwładność/spóźnienie reakcji układu.
SAFETY_CUTOFF_HRT_C = HARD_MAX_HRT_C - SAFETY_MARGIN_C  # Realny próg przerwania testu.

MAX_TEST_DURATION_S = 4 * 3600     # Twardy limit czasowy autotestu (4 godziny) - nie czekamy w nieskończoność.
MIN_RESPONSE_FOR_STAB_CHECK_C = 1.0  # Zanim sprawdzamy stabilizację, odpowiedź musi realnie ruszyć (unikamy fałszywej "stabilizacji" w trakcie samego opóźnienia).
STAB_WINDOW_S = 600                # Okno, na którym regresją liniową liczymy szybkość zmian [s].
SMOOTH_WINDOW_S = 60                # Krótkie okno uśredniania sygnału przed sprawdzeniem progu startowego [s].
STAB_RATE_THRESHOLD_C_PER_S = 0.0008  # Poniżej tego tempa zmian (z regresji) uznajemy sygnał za ustabilizowany.

SENSOR_NOISE_STD_C = 0.05          # Realistyczny szum/rozdzielczość czujnika HRT i CRT.

RNG = np.random.default_rng(42)


# ==============================================================================
# 3. SYMULACJA "PRAWDZIWEJ" ODPOWIEDZI OBIEKTU NA SKOK GRZANIA
# ==============================================================================
def compute_weather_baseline(at_array, dt=DT):
    """Liczy trajektorię CRT (składowa czysto pogodowa) dla całej serii AT na raz."""
    sys_w_continuous = signal.tf2ss(tf_weather.num, tf_weather.den)
    A_wd, B_wd, C_wd, D_wd, _ = signal.cont2discrete(sys_w_continuous, dt, method='zoh')
    _, hrt_weather_all, _ = signal.dlsim((A_wd, B_wd, C_wd, D_wd, dt), at_array)
    return hrt_weather_all.flatten()


def simulate_heating_step(duration_steps, dt=DT, k=K_H_TRUE, t1=T1_H_TRUE, t2=T2_H_TRUE, l=L_H_TRUE):
    """Symuluje odpowiedź SAMEJ grzałki (bez wpływu pogody) na skok 0 -> 100% w t=0."""
    tf_heating = signal.TransferFunction([k * 0.0, k], np.polymul([t1, 1], [t2, 1]).tolist())
    sys_h_continuous = signal.tf2ss(tf_heating.num, tf_heating.den)
    A_hd, B_hd, C_hd, D_hd, _ = signal.cont2discrete(sys_h_continuous, dt, method='zoh')

    delay_steps = int(round(l / dt))
    x_h = np.zeros((A_hd.shape[0], 1))
    response = np.zeros(duration_steps)
    for i in range(duration_steps):
        u_delayed = 1.0 if i >= delay_steps else 0.0
        x_h = A_hd @ x_h + B_hd * u_delayed
        response[i] = float((C_hd @ x_h + D_hd * u_delayed)[0, 0])
    return response


# ==============================================================================
# 4. LOGIKA AUTOTESTU: SKOK + UCIĘCIE W BEZPIECZNYM MOMENCIE
# ==============================================================================
def run_autotest_simulation(crt_baseline_segment, max_steps=MAX_TEST_DURATION_S, add_noise=True,
                             noise_std=SENSOR_NOISE_STD_C):
    """
    Symuluje jeden przebieg autotestu (skok grzania 0->100%) na tle zadanej
    trajektorii pogodowej CRT (niezależnej od grzania) i ucina go zgodnie
    z regułami bezpieczeństwa. Zwraca zebrane próbki i powód zatrzymania.
    """
    heating_response_full = simulate_heating_step(max_steps)

    t_list, hrt_list, crt_list = [], [], []
    stop_reason = 'max_duration'
    stop_step = max_steps

    for i in range(max_steps):
        crt_true = crt_baseline_segment[i]
        hrt_true = crt_true + heating_response_full[i]

        if add_noise:
            crt_meas = crt_true + RNG.normal(0.0, noise_std)
            hrt_meas = hrt_true + RNG.normal(0.0, noise_std)
        else:
            crt_meas, hrt_meas = crt_true, hrt_true

        t_list.append(i * DT)
        hrt_list.append(hrt_meas)
        crt_list.append(crt_meas)

        # a) TWARDY WARUNEK BEZPIECZEŃSTWA - nadrzędny nad wszystkim innym.
        # UWAGA: sprawdzamy na ZMIERZONEJ (zaszumionej) wartości, bo tylko taką
        # ma do dyspozycji prawdziwy sterownik - stąd margines SAFETY_MARGIN_C.
        if hrt_meas >= SAFETY_CUTOFF_HRT_C:
            stop_reason = 'safety_cap'
            stop_step = i + 1
            break

        # b) DETEKCJA NATURALNEJ STABILIZACJI (typowe zimą - nie ma sensu ciągnąć testu dalej).
        # Zamiast porównywać dwie pojedyncze (zaszumione) próbki, uśredniamy sygnał
        # na krótkim oknie i liczymy nachylenie regresją liniową na całym oknie
        # stabilizacji - to odporne na szum pomiarowy czujników HRT/CRT.
        window_steps = int(STAB_WINDOW_S / DT)
        smooth_steps = min(int(SMOOTH_WINDOW_S / DT), i + 1)
        y_smoothed_now = float(np.mean(
            [hrt_list[j] - crt_list[j] for j in range(i + 1 - smooth_steps, i + 1)]
        ))
        if y_smoothed_now > MIN_RESPONSE_FOR_STAB_CHECK_C and i * DT > STAB_WINDOW_S:
            t_window = np.array(t_list[i + 1 - window_steps:i + 1])
            y_window = (
                np.array(hrt_list[i + 1 - window_steps:i + 1])
                - np.array(crt_list[i + 1 - window_steps:i + 1])
            )
            slope = float(np.polyfit(t_window, y_window, 1)[0])
            if abs(slope) < STAB_RATE_THRESHOLD_C_PER_S:
                stop_reason = 'stabilized'
                stop_step = i + 1
                break

    t_arr = np.array(t_list)
    hrt_arr = np.array(hrt_list)
    crt_arr = np.array(crt_list)
    y_arr = hrt_arr - crt_arr

    return {
        't': t_arr,
        'hrt': hrt_arr,
        'crt': crt_arr,
        'y': y_arr,
        'stop_reason': stop_reason,
        'stop_step': stop_step,
        'max_hrt_reached': float(np.max(hrt_arr)),
    }


# ==============================================================================
# 5. IDENTYFIKACJA MODELU SOPDT (K, T1, T2, L) Z (MOŻLIWIE NIEPEŁNEJ) KRZYWEJ
# ==============================================================================
def _sopdt_step_response(t, k, t1, t2, l):
    tau = t - l
    tau = np.clip(tau, 0.0, None)  # przed opóźnieniem odpowiedź = 0

    if abs(t1 - t2) < 1e-3:
        y = k * (1.0 - np.exp(-tau / t1) * (1.0 + tau / t1))
    else:
        y = k * (1.0 - (t1 * np.exp(-tau / t1) - t2 * np.exp(-tau / t2)) / (t1 - t2))

    y = np.where(t < l, 0.0, y)
    return y


def identify_sopdt(t_arr, y_arr):
    """
    Dopasowuje model K/((T1 s+1)(T2 s+1)) z opóźnieniem L do zaobserwowanej
    (możliwie ucietej) krzywej odpowiedzi skokowej. Zwraca None, jeśli
    dopasowanie się nie powiodło.
    """
    y_max = max(float(np.max(y_arr)), 0.1)
    t_max = float(t_arr[-1]) if len(t_arr) else 1.0

    # Prosty szacunek opóźnienia: pierwszy moment, gdy sygnał wyraźnie ruszył.
    threshold = max(0.05 * y_max, 0.2)
    above = np.where(y_arr > threshold)[0]
    l_guess = float(t_arr[above[0]]) if len(above) else 0.0

    bounds_lower = [0.1, 5.0, 5.0, 0.0]
    bounds_upper = [300.0, 30000.0, 30000.0, max(t_max, 10.0)]

    best_fit = None
    best_sse = np.inf

    # Kilka wariantów startowych dla K, bo przy nieukończonym skoku wzmocnienie
    # ustalone (K) jest najtrudniejszym do odgadnięcia parametrem.
    k_candidates = [y_max * 1.1, y_max * 1.5, y_max * 2.5, y_max * 4.0, y_max * 8.0]
    t_span = max(t_max - l_guess, 10.0)

    for k0 in k_candidates:
        t1_0 = max(t_span / 4.0, 10.0)
        t2_0 = max(t_span / 2.0, 20.0)
        p0 = [k0, t1_0, t2_0, max(l_guess, 0.0)]
        p0 = [min(max(p0[i], bounds_lower[i]), bounds_upper[i]) for i in range(4)]

        try:
            popt, _ = curve_fit(
                _sopdt_step_response, t_arr, y_arr, p0=p0,
                bounds=(bounds_lower, bounds_upper), maxfev=20000,
            )
        except RuntimeError:
            continue

        pred = _sopdt_step_response(t_arr, *popt)
        sse = float(np.sum((y_arr - pred) ** 2))
        if sse < best_sse:
            best_sse = sse
            best_fit = popt

    if best_fit is None:
        return None

    k_fit, t1_fit, t2_fit, l_fit = best_fit
    pred = _sopdt_step_response(t_arr, *best_fit)
    ss_res = float(np.sum((y_arr - pred) ** 2))
    ss_tot = float(np.sum((y_arr - np.mean(y_arr)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    return {
        'K': float(k_fit), 'T1': float(t1_fit), 'T2': float(t2_fit), 'L': float(l_fit),
        'r_squared': r_squared,
    }


def relative_error_pct(estimated, true_value):
    if true_value == 0:
        return float('nan')
    return 100.0 * (estimated - true_value) / true_value


# ==============================================================================
# 6. SCENARIUSZE TESTOWE
# ==============================================================================
def build_summer_synthetic_series(baseline_c, length_s=MAX_TEST_DURATION_S + 100, amplitude_c=3.0):
    """Prosta syntetyczna seria AT dla scenariusza letniego (danych CSV nie ma latem)."""
    t = np.arange(length_s)
    daily_wave = amplitude_c * np.sin(2 * np.pi * t / 86400.0)
    return baseline_c + daily_wave


def run_one_trial(label, at_segment, results, noise_std=SENSOR_NOISE_STD_C):
    crt_baseline = compute_weather_baseline(at_segment)
    sim = run_autotest_simulation(
        crt_baseline, max_steps=min(MAX_TEST_DURATION_S, len(crt_baseline)),
        add_noise=(noise_std > 0), noise_std=noise_std,
    )
    fit = identify_sopdt(sim['t'], sim['y'])

    row = {
        'label': label,
        'stop_reason': sim['stop_reason'],
        'duration_s': float(sim['t'][-1]),
        'max_hrt_reached': sim['max_hrt_reached'],
    }
    if fit is None:
        row['fit_ok'] = False
    else:
        row['fit_ok'] = True
        row['K_fit'], row['T1_fit'], row['T2_fit'], row['L_fit'] = fit['K'], fit['T1'], fit['T2'], fit['L']
        row['K_err_pct'] = relative_error_pct(fit['K'], K_H_TRUE)
        row['T1_err_pct'] = relative_error_pct(fit['T1'], T1_H_TRUE)
        row['T2_err_pct'] = relative_error_pct(fit['T2'], T2_H_TRUE)
        row['L_err_pct'] = relative_error_pct(fit['L'], L_H_TRUE)
        row['r_squared'] = fit['r_squared']
    results.append(row)
    return sim, fit


def print_row(row):
    if not row['fit_ok']:
        print(f"{row['label']:<28} | powod={row['stop_reason']:<11} | czas={row['duration_s']:7.0f}s | "
              f"maxHRT={row['max_hrt_reached']:6.2f} | DOPASOWANIE NIEUDANE")
        return
    print(
        f"{row['label']:<28} | powod={row['stop_reason']:<11} | czas={row['duration_s']:7.0f}s | "
        f"maxHRT={row['max_hrt_reached']:6.2f} | "
        f"K={row['K_fit']:6.2f}({row['K_err_pct']:+6.1f}%) "
        f"T1={row['T1_fit']:7.0f}({row['T1_err_pct']:+6.1f}%) "
        f"T2={row['T2_fit']:7.0f}({row['T2_err_pct']:+6.1f}%) "
        f"L={row['L_fit']:6.0f}({row['L_err_pct']:+6.1f}%) "
        f"R2={row['r_squared']:.3f}"
    )


def main():
    print("=" * 100)
    print("WALIDACJA AUTOTESTU: identyfikacja obiektu SOPDT z (niepełnego) skoku temperatury")
    print(f"Prawdziwy obiekt:  K={K_H_TRUE:.3f}  T1={T1_H_TRUE:.1f}s  T2={T2_H_TRUE:.1f}s  L={L_H_TRUE:.1f}s")
    print(f"Limit bezpieczenstwa: przerwanie testu przy HRT >= {SAFETY_CUTOFF_HRT_C:.1f}C "
          f"(twardy limit konstrukcyjny {HARD_MAX_HRT_C:.1f}C)")
    print(f"Maksymalny czas trwania autotestu: {MAX_TEST_DURATION_S/3600:.1f}h")
    print("=" * 100)

    results = []

    # --- SCENARIUSZE ZIMOWE: prawdziwe dane pomiarowe (Suwałki, styczeń) ---
    csv_path = os.path.normpath(os.path.join(
        os.path.dirname(__file__), '..', 'Pogoda_pomiary_15_minut',
        'suwalki_15min_2010.csv',
    ))
    print(f"\n📖 Wczytywanie danych zimowych: {csv_path}")
    df = wczytaj_pogode_1s(csv_path)
    at_array = df['temperatura_powietrza_C'].to_numpy(dtype=float)
    print(f"   Zakres temperatur w danych: {at_array.min():.1f}C .. {at_array.max():.1f}C, {len(at_array)} probek 1s")

    total_len = len(at_array)
    step_between_starts = 12 * 3600  # co 12h nowy start autotestu
    latest_start = total_len - MAX_TEST_DURATION_S - 10
    starts = list(range(0, max(latest_start, 1), step_between_starts))

    print(f"\n🧪 SCENARIUSZE ZIMOWE (dane rzeczywiste) - {len(starts)} testow:")
    print("-" * 100)
    for start_idx in starts:
        ts = df['Timestamp'].iloc[start_idx]
        label = f"zima {ts.strftime('%m-%d %H:%M')}"
        at_segment = at_array[start_idx:start_idx + MAX_TEST_DURATION_S]
        if len(at_segment) < MAX_TEST_DURATION_S:
            continue
        _, _ = run_one_trial(label, at_segment, results)
        print_row(results[-1])

    # --- SCENARIUSZE LETNIE: dane syntetyczne (CSV nie zawiera lata) ---
    print(f"\n🧪 SCENARIUSZE LETNIE (dane syntetyczne, brak lata w CSV) - baza 15C..35C:")
    print("-" * 100)
    for baseline_c in [15.0, 20.0, 25.0, 30.0, 35.0]:
        at_segment = build_summer_synthetic_series(baseline_c)
        label = f"lato baza {baseline_c:.0f}C"
        _, _ = run_one_trial(label, at_segment, results)
        print_row(results[-1])

    # --- PODSUMOWANIE ---
    res_df = pd.DataFrame(results)
    print("\n" + "=" * 100)
    print("PODSUMOWANIE")
    print("=" * 100)
    print(f"Liczba testow ogolem: {len(res_df)} | Nieudane dopasowania: {(~res_df['fit_ok']).sum()}")
    print("\nRozklad powodow zatrzymania autotestu:")
    print(res_df['stop_reason'].value_counts().to_string())

    ok = res_df[res_df['fit_ok']]
    if len(ok):
        print("\nJakosc dopasowania R^2 (jak dobrze model SOPDT wyjasnia zebrane probki y=HRT-CRT):")
        print(f"  min={ok['r_squared'].min():.6f}  srednia={ok['r_squared'].mean():.6f}  "
              f"mediana={ok['r_squared'].median():.6f}  max={ok['r_squared'].max():.6f}")
        print("  R^2 wg powodu zatrzymania testu:")
        for reason, group in ok.groupby('stop_reason'):
            print(f"    {reason:<12} (n={len(group):2d}): min={group['r_squared'].min():.6f}  "
                  f"srednia={group['r_squared'].mean():.6f}  max={group['r_squared'].max():.6f}")
        print("  Pelna lista R^2 dla kazdego testu:")
        for _, row in ok.iterrows():
            print(f"    {row['label']:<28} R^2={row['r_squared']:.6f}")

        print("\nSredni blad bezwzgledny identyfikacji parametrow (wszystkie udane testy):")
        for col in ['K_err_pct', 'T1_err_pct', 'T2_err_pct', 'L_err_pct']:
            print(f"  {col:<12}: {ok[col].abs().mean():6.2f} %  (mediana {ok[col].abs().median():6.2f} %)")

        print("\nSredni blad bezwzgledny wg powodu zatrzymania testu:")
        for reason, group in ok.groupby('stop_reason'):
            k_err = group['K_err_pct'].abs().mean()
            t1_err = group['T1_err_pct'].abs().mean()
            t2_err = group['T2_err_pct'].abs().mean()
            l_err = group['L_err_pct'].abs().mean()
            print(f"  {reason:<12} (n={len(group):2d}): K={k_err:6.2f}%  T1={t1_err:6.2f}%  T2={t2_err:6.2f}%  L={l_err:6.2f}%")

    print("=" * 100)

    # --- ANALIZA WRAZLIWOSCI NA SZUM POMIAROWY CZUJNIKOW (jak dobra jest metoda w praktyce) ---
    print("\n" + "=" * 100)
    print("WRAZLIWOSC NA SZUM CZUJNIKOW HRT/CRT (ten sam start, rosnacy szum pomiarowy)")
    print("=" * 100)
    noise_levels = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    noise_results = []

    winter_at_segment = at_array[0:MAX_TEST_DURATION_S]
    for noise_std in noise_levels:
        row_results = []
        run_one_trial(f"zima szum={noise_std:.2f}C", winter_at_segment, row_results, noise_std=noise_std)
        noise_results.append(row_results[0])
        print_row(row_results[0])

    summer_at_segment = build_summer_synthetic_series(25.0)
    for noise_std in noise_levels:
        row_results = []
        run_one_trial(f"lato szum={noise_std:.2f}C", summer_at_segment, row_results, noise_std=noise_std)
        noise_results.append(row_results[0])
        print_row(row_results[0])

    noise_df = pd.DataFrame(noise_results)
    print("\nR^2 i blad K w funkcji poziomu szumu pomiarowego:")
    for _, row in noise_df.iterrows():
        if row['fit_ok']:
            print(f"  {row['label']:<24}: R^2={row['r_squared']:.6f}  K_err={row['K_err_pct']:+6.2f}%")
        else:
            print(f"  {row['label']:<24}: DOPASOWANIE NIEUDANE")
    print("=" * 100)

    return res_df, noise_df


if __name__ == '__main__':
    main()
