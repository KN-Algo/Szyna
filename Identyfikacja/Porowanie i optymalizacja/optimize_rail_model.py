import argparse
import json
import time
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import signal
from scipy.optimize import differential_evolution, minimize
from scipy.stats import pearsonr


FILE_PATH = r"D:/Pulpit/KN ALGO/Szyna/Porowanie_modelu_z_obiektem/dane_miesieczne.csv"

AT_MIN = -30.0
AT_MAX = 30.0
HRT_MIN = -30.0
HRT_MAX = 80.0
MOC_MAX = 1e6


@dataclass
class ModelParams:
    K_W: float
    T1_W: float
    TZ_W: float
    L_W: float
    K_H: float
    T1_H: float
    T2_H: float
    TZ_H: float
    L_H: float
    offset: float = 0.0


BASE_PARAMS = ModelParams(
    K_W=1.0774,
    T1_W=5785.78,
    TZ_W=657.05,
    L_W=0.0,
    K_H=265.79,
    T1_H=792.71,
    T2_H=49947.65,
    TZ_H=5157.87,
    L_H=30.0,
)


def build_tf_weather(K, T1, Tz):
    num = [K * Tz, K]
    den = [T1, 1.0]
    return signal.TransferFunction(num, den)


def build_tf_heating(K, T1, T2, Tz):
    num = [K * Tz, K]
    den = np.polymul([T1, 1.0], [T2, 1.0]).tolist()
    return signal.TransferFunction(num, den)


def simulate_tf(tf_c, u, t_sec, L_sec=0.0, x0=None):
    if L_sec > 0:
        i_start = np.searchsorted(t_sec, L_sec)
        t_shifted = t_sec - L_sec
        if i_start < len(u):
            u_delayed = np.interp(t_sec, t_shifted[i_start:], u[i_start:], left=0.0)
        else:
            u_delayed = np.zeros_like(u)
    else:
        u_delayed = u.copy()

    dt_med = float(np.median(np.diff(t_sec)))
    dt_med = max(dt_med, 0.1)
    t_uniform = np.arange(t_sec[0], t_sec[-1] + dt_med, dt_med)
    u_uniform = np.interp(t_uniform, t_sec, u_delayed)

    if x0 == "steady":
        t_pre_end = max(10.0 * max(np.asarray(tf_c.den[:-1], dtype=float) / tf_c.den[-1]), dt_med)
        t_pre = np.linspace(0.0, t_pre_end, 500)
        u_pre = np.full_like(t_pre, u_uniform[0], dtype=float)
        _, _, x_pre = signal.lsim(tf_c, U=u_pre, T=t_pre)
        x0_vec = x_pre[-1]
    else:
        x0_vec = x0

    _, y_uniform, _ = signal.lsim(tf_c, U=u_uniform, T=t_uniform, X0=x0_vec)
    return np.interp(t_sec, t_uniform, y_uniform)


def clean_signal_at(u_raw):
    from scipy.signal import medfilt

    u = u_raw.copy().astype(float)
    bad = (u < AT_MIN) | (u > AT_MAX) | np.isnan(u)
    u[bad] = np.nan
    idx = np.arange(len(u))
    valid = ~np.isnan(u)
    if valid.sum() > 2:
        u = np.interp(idx, idx[valid], u[valid])
    return medfilt(u.astype(float), kernel_size=5)


def clean_signal_hrt(y_raw):
    y = y_raw.copy().astype(float)
    return np.clip(y, HRT_MIN, HRT_MAX)


def load_and_clean(file_path):
    df = pd.read_csv(file_path, sep=";")

    def to_num(col):
        return pd.to_numeric(col.astype(str).str.replace(",", "."), errors="coerce")

    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df = df.sort_values("Timestamp").reset_index(drop=True)

    hrt = to_num(df["HRT_temp_grzana"])
    at = to_num(df["AT_temp_powietrza"])
    p1 = to_num(df["PWRL1_moc"]).fillna(0.0)
    p2 = to_num(df["PWRL2_moc"]).fillna(0.0)

    df = pd.DataFrame(
        {
            "Timestamp": df["Timestamp"],
            "HRT_temp_grzana": hrt,
            "AT_temp_powietrza": at,
            "PWRL1_moc": p1,
            "PWRL2_moc": p2,
        }
    ).dropna(subset=["HRT_temp_grzana", "AT_temp_powietrza"])
    df = df.reset_index(drop=True)

    t_abs = df["Timestamp"].values.astype("datetime64[ns]").astype(np.int64) / 1e9
    t_sec = t_abs - t_abs[0]

    y_clean = clean_signal_hrt(df["HRT_temp_grzana"].to_numpy())
    u_at = clean_signal_at(df["AT_temp_powietrza"].to_numpy())

    p1 = df["PWRL1_moc"].to_numpy(dtype=float)
    p2 = df["PWRL2_moc"].to_numpy(dtype=float)
    p1 = np.nan_to_num(p1, nan=0.0)
    p2 = np.nan_to_num(p2, nan=0.0)
    p1[(p1 < 0.0) | (p1 > MOC_MAX)] = 0.0
    p2[(p2 < 0.0) | (p2 > MOC_MAX)] = 0.0
    u_heat = ((p1 + p2) > 0.0).astype(float)

    return t_sec, u_at, u_heat, y_clean


def choose_fit_subset(t_sec, u_at, u_heat, y_meas, max_points):
    if max_points <= 0 or len(t_sec) <= max_points:
        return t_sec, u_at, u_heat, y_meas
    idx = np.unique(np.linspace(0, len(t_sec) - 1, max_points).astype(int))
    return t_sec[idx], u_at[idx], u_heat[idx], y_meas[idx]


def r2_score(y_meas, y_model):
    mask = ~(np.isnan(y_meas) | np.isnan(y_model))
    ym = y_meas[mask]
    yp = y_model[mask]
    ss_res = np.sum((ym - yp) ** 2)
    ss_tot = np.sum((ym - np.mean(ym)) ** 2)
    return 1.0 - ss_res / (ss_tot + 1e-30)


def metrics(y_meas, y_model):
    mask = ~(np.isnan(y_meas) | np.isnan(y_model))
    ym = y_meas[mask]
    yp = y_model[mask]
    ss_res = np.sum((ym - yp) ** 2)
    rmse = np.sqrt(ss_res / len(ym))
    mae = np.mean(np.abs(ym - yp))
    r2 = r2_score(ym, yp)
    rp, pval = pearsonr(ym, yp)
    return {"r2": r2, "rmse": rmse, "mae": mae, "pearson_r": rp, "pearson_p": pval}


def model_response(params, t_sec, u_at, u_heat, y_meas):
    tf_w = build_tf_weather(params.K_W, params.T1_W, params.TZ_W)
    tf_h = build_tf_heating(params.K_H, params.T1_H, params.T2_H, params.TZ_H)

    y_weather = simulate_tf(tf_w, u_at, t_sec, L_sec=params.L_W, x0="steady")
    y_heat = simulate_tf(tf_h, u_heat, t_sec, L_sec=params.L_H, x0=None)
    y_raw = y_weather + y_heat

    # Najlepszy offset dla R2/RMSE to srednia roznica pomiar-model.
    offset = float(np.nanmean(y_meas - y_raw))
    y_model = y_raw + offset
    params = ModelParams(**{**asdict(params), "offset": offset})
    return y_model, y_weather + offset, y_heat, params


def vector_to_params(x):
    return ModelParams(
        K_W=float(x[0]),
        T1_W=float(10 ** x[1]),
        TZ_W=float(10 ** x[2]),
        L_W=0.0,
        K_H=float(x[3]),
        T1_H=float(10 ** x[4]),
        T2_H=float(10 ** x[5]),
        TZ_H=float(10 ** x[6]),
        L_H=float(x[7]),
    )


def params_to_vector(params):
    return np.array(
        [
            params.K_W,
            np.log10(params.T1_W),
            np.log10(max(params.TZ_W, 1.0)),
            params.K_H,
            np.log10(params.T1_H),
            np.log10(params.T2_H),
            np.log10(max(params.TZ_H, 1.0)),
            params.L_H,
        ],
        dtype=float,
    )


def objective_factory(t_sec, u_at, u_heat, y_meas):
    cache = {"n": 0, "best": -np.inf, "best_params": None}

    def objective(x):
        cache["n"] += 1
        try:
            params = vector_to_params(x)
            y_model, _, _, params = model_response(params, t_sec, u_at, u_heat, y_meas)
            r2 = r2_score(y_meas, y_model)
            if np.isfinite(r2) and r2 > cache["best"]:
                cache["best"] = r2
                cache["best_params"] = params
                print(f"[{cache['n']:5d}] best R2={r2:.6f}  {compact_params(params)}", flush=True)
            if not np.isfinite(r2):
                return 1e9
            return -r2
        except Exception:
            return 1e9

    objective.cache = cache
    return objective


def compact_params(params):
    return (
        f"K_W={params.K_W:.5g}, T1_W={params.T1_W:.1f}, TZ_W={params.TZ_W:.1f}, "
        f"K_H={params.K_H:.5g}, T1_H={params.T1_H:.1f}, T2_H={params.T2_H:.1f}, "
        f"TZ_H={params.TZ_H:.1f}, L_H={params.L_H:.1f}, off={params.offset:.3f}"
    )


def print_report(title, params, metric_values):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(f"R2          : {metric_values['r2']:.8f}")
    print(f"RMSE        : {metric_values['rmse']:.6f} degC")
    print(f"MAE         : {metric_values['mae']:.6f} degC")
    print(f"Pearson r   : {metric_values['pearson_r']:.8f}")
    print("\nNastawy:")
    for key, value in asdict(params).items():
        print(f"  {key:7s} = {value:.10g}")


def main():
    parser = argparse.ArgumentParser(description="Szerokie strojenie modelu szyny pod maksymalne R2.")
    parser.add_argument("--file", default=FILE_PATH)
    parser.add_argument("--maxiter", type=int, default=25)
    parser.add_argument("--popsize", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fit-points", type=int, default=4000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--no-polish", action="store_true")
    parser.add_argument("--out", default="best_rail_model_params.json")
    args = parser.parse_args()

    t_sec, u_at, u_heat, y_meas = load_and_clean(args.file)
    t_fit, at_fit, heat_fit, y_fit = choose_fit_subset(t_sec, u_at, u_heat, y_meas, args.fit_points)

    print(f"Probki pelne: {len(t_sec)}")
    print(f"Probki do strojenia: {len(t_fit)}")

    y_base, _, _, base_with_offset = model_response(BASE_PARAMS, t_sec, u_at, u_heat, y_meas)
    print_report("PARAMETRY STARTOWE - OCENA NA CALYCH DANYCH", base_with_offset, metrics(y_meas, y_base))

    # Zakresy sa celowo szerokie. Stale czasowe optymalizujemy w skali log10.
    bounds = [
        (0.05, 3.0),          # K_W
        (np.log10(30), 5.2),  # T1_W: 30 s .. ok. 158 000 s
        (0.0, 5.0),           # TZ_W: 1 s .. 100 000 s
        (1.0, 700.0),         # K_H
        (np.log10(10), 5.0),  # T1_H: 10 s .. 100 000 s
        (np.log10(100), 6.0), # T2_H: 100 s .. 1 000 000 s
        (0.0, 5.5),           # TZ_H: 1 s .. ok. 316 000 s
        (0.0, 1800.0),        # L_H: 0 s .. 30 min
    ]

    objective = objective_factory(t_fit, at_fit, heat_fit, y_fit)
    started = time.time()
    result = differential_evolution(
        objective,
        bounds=bounds,
        maxiter=args.maxiter,
        popsize=args.popsize,
        seed=args.seed,
        tol=1e-5,
        polish=False,
        workers=args.workers,
        updating="deferred" if args.workers != 1 else "immediate",
    )

    best_x = result.x
    if not args.no_polish:
        print("\nLokalne dopolerowanie wyniku L-BFGS-B...")
        local = minimize(objective, best_x, method="L-BFGS-B", bounds=bounds, options={"maxiter": 120})
        if local.fun < result.fun:
            best_x = local.x

    best_params = vector_to_params(best_x)
    y_best_full, _, _, best_params = model_response(best_params, t_sec, u_at, u_heat, y_meas)
    best_metrics = metrics(y_meas, y_best_full)
    elapsed = time.time() - started

    print_report("NAJLEPSZE PARAMETRY - OCENA NA CALYCH DANYCH", best_params, best_metrics)
    print(f"\nCzas strojenia: {elapsed:.1f} s")

    payload = {
        "metrics_full": best_metrics,
        "params": asdict(best_params),
        "base_params": asdict(base_with_offset),
        "optimizer": {
            "maxiter": args.maxiter,
            "popsize": args.popsize,
            "seed": args.seed,
            "fit_points": args.fit_points,
        },
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nZapisano wynik: {args.out}")


if __name__ == "__main__":
    main()
