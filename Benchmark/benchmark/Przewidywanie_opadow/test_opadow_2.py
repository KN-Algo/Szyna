import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# =====================================================================
# 1. ZOPTYMALIZOWANY SILNIK FIZYCZNY (BEZ TWARDEJ BLOKADY CIŚNIENIA)
# =====================================================================
class PhysicalWinterForecaster8Steps:
    """
    Algorytm prognozowania opadów zimowych w horyzoncie 8 kroków (2 godziny do przodu co 15 min).
    """
    def __init__(self, config=None):
        self.config = config or {
            'spread_max_precip': 1.5,       # Max niedosyt rosy (T - Td) aktywujący opad [°C]
            'spread_heavy_precip': 0.6,     # Niedosyt rosy aktywujący średni opad [°C]
            'tw_max_winter': 1.0,           # Max Tw dla opadu w fazie zimowej [°C]
            'wind_high_threshold': 6.0,     # Prędkość wiatru podnosząca stopień zagrożenia [m/s]
            'dp_strong_fall': -1.5,         # Spadek ciśnienia dla poziomu 3 [hPa/3h]
            'dp_moderate_fall': -0.8,       # Spadek ciśnienia dla poziomu 2 [hPa/3h]
        }

    @staticmethod
    def calculate_rh(temp_c, dp_c):
        a, b = 17.625, 243.04
        alpha_t = (a * temp_c) / (b + temp_c)
        alpha_dp = (a * dp_c) / (b + dp_c)
        return np.clip(100.0 * np.exp(alpha_dp - alpha_t), 0.0, 100.0)

    @staticmethod
    def calculate_wet_bulb(temp_c, rh_percent):
        return (temp_c * np.arctan(0.151977 * np.sqrt(rh_percent + 8.313659)) +
                np.arctan(temp_c + rh_percent) - np.arctan(rh_percent - 1.676331) +
                0.00391838 * (rh_percent ** 1.5) * np.arctan(0.023101 * rh_percent) - 4.686035)

    def predict_8_steps(self, p_history_3h, future_t_8steps, future_td_8steps, future_wind_8steps):
        trend_3h = (p_history_3h[-1] - p_history_3h[0]) if len(p_history_3h) > 1 else 0.0

        forecast = []
        for step in range(8):
            t_pred = float(future_t_8steps[step])
            td_pred = float(future_td_8steps[step])
            wind_pred = float(future_wind_8steps[step])

            spread = t_pred - td_pred
            rh = self.calculate_rh(t_pred, td_pred)
            tw = self.calculate_wet_bulb(t_pred, rh)

            # Warunki fizyczne do opadu zimowego
            is_saturated = (spread <= self.config['spread_max_precip'])
            is_winter_phase = (tw <= self.config['tw_max_winter']) or (t_pred <= 0.0)

            if not is_saturated or not is_winter_phase:
                forecast.append(0)
                continue

            # --- DYNAMIKA INTENSYWNOŚCI (0-3) ---
            # Bazowy poziom przy spełnieniu nasycenia wilgocią
            intensity = 1

            # Podbicie intensywności przy bardzo głębokim nasyceniu
            if spread <= self.config['spread_heavy_precip']:
                intensity = 2

            # Modyfikacja na podstawie dynamiki ciśnienia (frontu)
            if trend_3h <= self.config['dp_strong_fall']:
                intensity = 3
            elif trend_3h <= self.config['dp_moderate_fall']:
                intensity = max(intensity, 2)

            # Modyfikacja na podstawie wiatru (zamiecie / zamarzanie)
            if wind_pred >= self.config['wind_high_threshold'] and intensity < 3:
                intensity += 1

            forecast.append(intensity)

        return np.array(forecast, dtype=int)


# =====================================================================
# 2. POPRAWIONA EWALUACJA CZASOWA Z DOKŁADNYM ROZLICZENIEM PRÓBEK
# =====================================================================
def run_engineering_benchmark_fixed(file_path):
    INTENSITY_DEFS = {
        0: {"nazwa": "Brak opadu", "prog": "0.00 mm / 15 min"},
        1: {"nazwa": "Słaby opad", "prog": "0.01 - 0.35 mm / 15 min (lekki śnieg / mżawka marznąca)"},
        2: {"nazwa": "Średni opad", "prog": "0.36 - 1.00 mm / 15 min (umiarkowany śnieg / deszcz marznący)"},
        3: {"nazwa": "Mocny opad / Nawałnica", "prog": "> 1.00 mm / 15 min lub średni opad przy wietrze > 6 m/s"}
    }

    df = pd.read_csv(file_path)
    if 'data_czas' in df.columns:
        df.rename(columns={'data_czas': 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df.sort_values('Timestamp', inplace=True)
    df.reset_index(drop=True, inplace=True)

    if 'PRESS_cisnienie' not in df.columns:
        df['PRESS_cisnienie'] = 1013.25
    if 'wiatr_m_s' not in df.columns:
        df['wiatr_m_s'] = 3.0

    forecaster = PhysicalWinterForecaster8Steps()

    PROBKA_GODZINY = 0.25  # Próbki co 15 minut (0.25 h)
    LOOKBACK = 12          # 3 godziny historii ciśnienia
    LOOKAHEAD = 8          # 2 godziny w przód

    # Ground Truth dla każdego wiersza
    gt_all = []
    for idx in range(len(df)):
        opad_val = float(df['opad_mm'].iloc[idx])
        t_val = float(df['temperatura_powietrza_C'].iloc[idx])
        w_val = float(df['wiatr_m_s'].iloc[idx])
        
        if opad_val > 0.0001 and t_val <= 1.0:
            if opad_val <= 0.35:
                int_val = 1
            elif opad_val <= 1.0:
                int_val = 2 if w_val < 6.0 else 3
            else:
                int_val = 3
        else:
            int_val = 0
        gt_all.append(int_val)

    gt_all = np.array(gt_all, dtype=int)

    # Generowanie prognoz
    pred_matrix = [] 
    eval_indices = range(LOOKBACK, len(df) - LOOKAHEAD)

    for i in eval_indices:
        p_history = df['PRESS_cisnienie'].iloc[i - LOOKBACK : i + 1].values
        future_slice = df.iloc[i + 1 : i + 1 + LOOKAHEAD]
        future_t = future_slice['temperatura_powietrza_C'].values
        future_td = future_slice['punkt_rosy_C'].values
        future_wind = future_slice['wiatr_m_s'].values

        pred_8 = forecaster.predict_8_steps(p_history, future_t, future_td, future_wind)
        pred_matrix.append(pred_8)

    pred_matrix = np.array(pred_matrix)

    # ANALYSIS 1: STANY SYSTEMU (1 wiersz = 15 min)
    tp_samples = 0
    fn_samples = 0
    early_start_samples = 0  
    late_stop_samples = 0    
    pure_false_samples = 0   
    tn_samples = 0

    total_eval_samples = len(eval_indices)

    for idx_pos, i in enumerate(eval_indices):
        target_idx = i + 1  
        actual_g = gt_all[target_idx]
        pred_p = pred_matrix[idx_pos, 0]

        if pred_p > 0 and actual_g > 0:
            tp_samples += 1
        elif pred_p == 0 and actual_g > 0:
            fn_samples += 1
        elif pred_p == 0 and actual_g == 0:
            tn_samples += 1
        elif pred_p > 0 and actual_g == 0:
            future_gt = gt_all[target_idx + 1 : min(target_idx + 9, len(gt_all))]
            past_gt = gt_all[max(0, target_idx - 8) : target_idx]

            if np.any(future_gt > 0):
                early_start_samples += 1
            elif np.any(past_gt > 0):
                late_stop_samples += 1
            else:
                pure_false_samples += 1

    godziny_analizy = total_eval_samples * PROBKA_GODZINY
    godziny_opadu_ogolem = np.sum(gt_all[eval_indices] > 0) * PROBKA_GODZINY
    godziny_wykryte = tp_samples * PROBKA_GODZINY
    godziny_przegapione = fn_samples * PROBKA_GODZINY
    godziny_pustego_grzania = (early_start_samples + late_stop_samples + pure_false_samples) * PROBKA_GODZINY

    godziny_za_wczesnie = early_start_samples * PROBKA_GODZINY
    godziny_za_pozno = late_stop_samples * PROBKA_GODZINY
    godziny_zbędne = pure_false_samples * PROBKA_GODZINY

    skutecznosc_oslony = (godziny_wykryte / godziny_opadu_ogolem * 100) if godziny_opadu_ogolem > 0 else 0.0
    procent_trafnych_alarmow = (tp_samples / (tp_samples + early_start_samples + late_stop_samples + pure_false_samples) * 100) if (tp_samples + early_start_samples + late_stop_samples + pure_false_samples) > 0 else 0.0

    # ANALYSIS 2: DOKŁADNOŚĆ NUMERKÓW (0-3)
    level_matches = {0: 0, 1: 0, 2: 0, 3: 0}
    level_totals = {0: 0, 1: 0, 2: 0, 3: 0}

    for idx_pos, i in enumerate(eval_indices):
        g = gt_all[i + 1]
        p = pred_matrix[idx_pos, 0]
        level_totals[g] += 1
        if p == g:
            level_matches[g] += 1

    dokladnosc_numerkow = (sum(level_matches.values()) / total_eval_samples * 100)

    horizon_acc = {}
    for step_h in range(8):
        matches_h = 0
        for idx_pos, i in enumerate(eval_indices):
            if pred_matrix[idx_pos, step_h] == gt_all[i + 1 + step_h]:
                matches_h += 1
        horizon_acc[(step_h + 1) * 15] = (matches_h / total_eval_samples) * 100

    # DRUKOWANIE RAPORTU
    print("\n" + "=" * 75)
    print("📖 DEFINICJE POZIOMÓW INTENSYWNOŚCI OPADU ZIMOWEGO (0 - 3)")
    print("=" * 75)
    for lvl, info in INTENSITY_DEFS.items():
        print(f"  Poziom {lvl}: {info['nazwa']:<23} | Progi: {info['prog']}")

    print("\n" + "=" * 75)
    print("📋 INŻYNIERYJNY RAPORT SKUTECZNOŚCI ALGORYTMU ZAMBRETTI-DYNAMIC")
    print("=" * 75)
    print(f"⏱️  Łączny czas w pliku testowym:        {godziny_analizy:.1f} godzin ({godziny_analizy / 24:.1f} dni)")
    print(f"❄️  Łączny czas opadów zimowych:        {godziny_opadu_ogolem:.2f} godzin")
    print("-" * 75)
    print(f"🛡️  BEZPIECZEŃSTWO (Wyłapany opad):      {godziny_wykryte:.2f} h / {godziny_opadu_ogolem:.2f} h  ({skutecznosc_oslony:.1f}% opadów pod ochroną)")
    print(f"⚠️  RYZYKO (Przegapiony opad):          {godziny_przegapione:.2f} godzin nieogrzewanej szyny podczas opadu")
    print(f"💸  KOSZT ENERGII (Puste grzanie):       {godziny_pustego_grzania:.2f} godzin niepotrzebnego grzania (brak opadu)")
    print("-" * 75)
    print("⏳ DYNAMIKA CZASOWA WŁĄCZANIA / WYŁĄCZANIA SYSTEMU:")
    print(f"   ⏱️  Za wcześnie włączone (pre-heating): {godziny_za_wczesnie:.2f} h (grzanie przed nadchodzącym opadem)")
    print(f"   ⏱️  Za późno wyłączone (post-cooling): {godziny_za_pozno:.2f} h (podtrzymanie grzania po opadzie)")
    print(f"   🚫 Czysto fałszywe grzanie (brak opadu): {godziny_zbędne:.2f} h")
    print("-" * 75)
    print(f"🎯  Trafność alarmu:                    W {procent_trafnych_alarmow:.1f}% przypadków po podniesieniu alarmu FAKTYCZNIE nastąpił opad")
    print(f"🔢  Dokładność numerków (Poziomy 0-3):   {dokladnosc_numerkow:.1f}% idealnych trafień dokładnego poziomu (+15 min)")
    
    print("-" * 75)
    print("📊 TRAFNOŚĆ DLA POSZCZEGÓLNYCH POZIOMÓW (NUMERKÓW 0-3 NA najbliższe 15 MIN):")
    for lvl in range(4):
        total_lvl = level_totals[lvl]
        match_lvl = level_matches[lvl]
        acc_lvl = (match_lvl / total_lvl * 100) if total_lvl > 0 else 0.0
        print(f"   • Poziom {lvl} ({INTENSITY_DEFS[lvl]['nazwa']:<21}): {match_lvl:<6} / {total_lvl:<6} trafień ({acc_lvl:.1f}%)")

    print("-" * 75)
    print("📈 DOKŁADNOŚĆ PROGNOZY DLA POSZCZEGÓLNYCH HORYZONTÓW WYPRZEDZENIA:")
    for minuty, acc in horizon_acc.items():
        print(f"   • Prognoza na +{minuty:<3} minut do przodu: {acc:.1f}% dokładności")
    print("=" * 75)


if __name__ == "__main__":
    sciezka = "Benchmark\\benchmark\\Pogoda_pomiary_15_minut\\suwalki_pogoda_15_min_model_2010.csv"
    run_engineering_benchmark_fixed(sciezka)