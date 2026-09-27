import os
import numpy as np
import pandas as pd


class przewidywanie_opadow:
    def __init__(self, persistence_steps=1):
        # Ile kroków (kwadransów) po ustaniu opadu system ma jeszcze grzać
        self.persistence_steps = persistence_steps

    @staticmethod
    def calculate_rh(temp_c, dp_c):
        # Wylicza wilgotność względną
        a, b = 17.625, 243.04
        alpha_t = (a * temp_c) / (b + temp_c)
        alpha_dp = (a * dp_c) / (b + dp_c)
        return np.clip(100.0 * np.exp(alpha_dp - alpha_t), 0.0, 100.0)

    @staticmethod
    def calculate_wet_bulb(temp_c, rh_percent):
        # Wylicza temperaturę mokrego termometru (Tw)
        return (temp_c * np.arctan(0.151977 * np.sqrt(rh_percent + 8.313659)) +
                np.arctan(temp_c + rh_percent) - np.arctan(rh_percent - 1.676331) +
                0.00391838 * (rh_percent ** 1.5) * np.arctan(0.023101 * rh_percent) - 4.686035)

    def predict_winter_precipitation(self, past_precip_array, future_t_8steps, current_dp, current_wind):
        # Sprawdzamy opady z ostatniego czasu
        recent_precip = np.array(past_precip_array[-self.persistence_steps:])

        # Ignorujemy szumy czujnika, reagujemy dopiero gdy opad > 0.02
        is_front_active = np.sum(recent_precip) > 0.02

        horizon = 8
        predictions = np.zeros(horizon, dtype=int)

        # Jeśli nie padało, od razu zwracamy zera
        if not is_front_active:
            return predictions

        forecast_temps = list(future_t_8steps)
        while len(forecast_temps) < horizon:
            forecast_temps.append(forecast_temps[-1] if forecast_temps else 0.0)

        # Skoro pada, ustalamy poziom zagrożenia dla każdego z 8 przyszłych kwadransów
        for i in range(horizon):
            t_pred = float(forecast_temps[i])
            rh = self.calculate_rh(t_pred, current_dp)
            tw = self.calculate_wet_bulb(t_pred, rh)
            spread = t_pred - current_dp

            # Jeśli jest wystarczająco zimno, przypisujemy stopień od 1 do 3
            if tw <= 0.1 or t_pred <= -0.5:
                intensity = 1
                if spread <= 0.6:
                    intensity = 2
                if current_wind >= 6.0 and intensity == 2:
                    intensity = 3
                predictions[i] = intensity
            else:
                predictions[i] = 0

        return predictions

# =====================================================================
# MODUŁ TESTUJĄCY
# =====================================================================
def algorytm_opadu(file_path):
    print("=" * 75)
    print(f"📖 ŁADOWANIE PLIKU TESTOWEGO I ANALIZA DANYCH...")
    print("=" * 75)

    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Błąd: Nie znaleziono pliku: {file_path}")
        return

    if 'data_czas' in df.columns:
        df.rename(columns={'data_czas': 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df.sort_values('Timestamp', inplace=True)
    df.reset_index(drop=True, inplace=True)

    if 'wiatr_m_s' not in df.columns:
        df['wiatr_m_s'] = 3.0

    forecaster = przewidywanie_opadow(persistence_steps=1)

    PROBKA_GODZINY = 0.25
    LOOKBACK = 4
    LOOKAHEAD = 8

    print("⚙️ Generowanie danych referencyjnych (Ground Truth)...")
    gt_all = []

    # Ustalanie faktycznych opadów zimowych z historii
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

    print("🏃 Symulacja algorytmu próbka po próbce (horyzont 8 kroków)...")
    pred_matrix = []
    eval_indices = range(LOOKBACK - 1, len(df) - LOOKAHEAD)

    # Odpalamy algorytm dla każdej próbki w pliku
    for i in eval_indices:
        past_precip = df['opad_mm'].iloc[i - LOOKBACK + 1 : i + 1].values
        future_slice = df.iloc[i + 1 : i + 1 + LOOKAHEAD]
        future_t = future_slice['temperatura_powietrza_C'].values
        current_dp = df['punkt_rosy_C'].iloc[i]
        current_wind = df['wiatr_m_s'].iloc[i]

        pred_8 = forecaster.predict_winter_precipitation(past_precip, future_t, current_dp, current_wind)
        pred_matrix.append(pred_8)

    pred_matrix = np.array(pred_matrix)

    # Statystyki poprawności działań
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
    wszystkie_alarmy = tp_samples + early_start_samples + late_stop_samples + pure_false_samples
    procent_trafnych_alarmow = (tp_samples / wszystkie_alarmy * 100) if wszystkie_alarmy > 0 else 0.0

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

    # =====================================================================
    # WYDRUK RAPORTU
    # =====================================================================
    INTENSITY_DEFS = {
        0: {"nazwa": "Brak opadu", "prog": "0.00 mm / 15 min"},
        1: {"nazwa": "Słaby opad", "prog": "0.01 - 0.35 mm / 15 min (lekki śnieg / mżawka marznąca)"},
        2: {"nazwa": "Średni opad", "prog": "0.36 - 1.00 mm / 15 min (umiarkowany śnieg / deszcz marznący)"},
        3: {"nazwa": "Mocny opad / Nawałnica", "prog": "> 1.00 mm / 15 min lub średni opad przy wietrze > 6 m/s"}
    }

    print("\n" + "=" * 75)
    print("📖 DEFINICJE POZIOMÓW INTENSYWNOŚCI OPADU ZIMOWEGO (0 - 3)")
    print("=" * 75)
    for lvl, info in INTENSITY_DEFS.items():
        print(f"  Poziom {lvl}: {info['nazwa']:<23} | Progi: {info['prog']}")

    print("\n" + "=" * 75)
    print("📋 RAPORT SKUTECZNOŚCI ALGORYTMU")
    print("=" * 75)
    print(f"⏱️  Łączny czas w pliku testowym:        {godziny_analizy:.1f} godzin ({godziny_analizy / 24:.1f} dni)")
    print(f"❄️  Łączny czas opadów zimowych:        {godziny_opadu_ogolem:.2f} godzin")
    print("-" * 75)
    print(f"🛡️  BEZPIECZEŃSTWO (Wyłapany opad):      {godziny_wykryte:.2f} h / {godziny_opadu_ogolem:.2f} h  ({skutecznosc_oslony:.1f}% opadów pod ochroną)")
    print(f"⚠️  RYZYKO (Przegapiony opad):          {godziny_przegapione:.2f} godzin nieogrzewanej szyny podczas opadu")
    print(f"💸  KOSZT ENERGII (Puste grzanie):       {godziny_pustego_grzania:.2f} godzin niepotrzebnego grzania (brak opadu)")
    print("-" * 75)
    print("⏳ DYNAMIKA CZASOWA WŁĄCZANIA / WYŁĄCZANIA SYSTEMU:")
    print(f"   ⏱️  Za wcześnie włączone (pre-heating): {godziny_za_wczesnie:.2f} h (grzanie tuż przed opadem)")
    print(f"   ⏱️  Za późno wyłączone (timer suszenia): {godziny_za_pozno:.2f} h (podtrzymanie grzania po opadzie)")
    print(f"   🚫 Czysto fałszywe grzanie (brak opadu): {godziny_zbędne:.2f} h")
    print("-" * 75)
    print(f"🎯  Trafność alarmu (Precyzja):         W {procent_trafnych_alarmow:.1f}% przypadków grzania na szynie leżał opad")
    print(f"🔢  Dokładność numerków (0-3):           {dokladnosc_numerkow:.1f}% idealnych trafień stopnia zagrożenia")
    print("-" * 75)
    print("📈 DOKŁADNOŚĆ PROGNOZY DLA POSZCZEGÓLNYCH HORYZONTÓW WYPRZEDZENIA:")
    for minuty, acc in horizon_acc.items():
        print(f"   • Prognoza na +{minuty:<3} minut do przodu: {acc:.1f}% dokładności")

    print("\n" + "=" * 75)
    print("📊 TRAFNOŚĆ DLA POSZCZEGÓLNYCH POZIOMÓW (NUMERKÓW 0-3 NA najbliższe 15 MIN):")
    NAZWY_POZIOMOW = {
        0: "Brak opadu",
        1: "Słaby śnieg/Szron",
        2: "Umiarkowany śnieg",
        3: "Zamieć/Nawałnica"
    }
    for lvl in range(4):
        total_lvl = level_totals[lvl]
        match_lvl = level_matches[lvl]
        acc_lvl = (match_lvl / total_lvl * 100) if total_lvl > 0 else 0.0
        print(f"   • Poziom {lvl} ({NAZWY_POZIOMOW[lvl]:<17}): {match_lvl:<6} / {total_lvl:<6} trafień ({acc_lvl:.1f}%)")
    print("=" * 75)


if __name__ == '__main__':
    sciezka = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            'Pogoda_pomiary_15_minut',
            'wroclaw_15min_2024.csv'
        )
    )
    algorytm_opadu(sciezka)

