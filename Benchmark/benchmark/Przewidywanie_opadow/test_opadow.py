import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime, timedelta

# =====================================================================
# 1. ZAAWANSOWANY PREDIKTOR Z TRZYSTOPNIOWYM FILTREM DYNAMICZNYM
# =====================================================================
class EnhancedWinterForecaster:
    """
    Algorytm prognozowania opadów zimowych (śnieg / deszcz marznący) z wyprzedzeniem 1-2 godzin.
    
    DZIAŁANIE:
    - Wykorzystuje klasyczny algorytm Barometru Zambrettiego (trend ciśnienia z 3h).
    - Łączy go z fizyką atmosfery (Temperatura Mokrego Termometru - Tw).
    - Wykorzystuje 3-stopniowy filtr dynamiczny (antymgłowy), aby odróżnić gęstą mgłę od chmury opadowej.
    """
    def __init__(self):
        # BUFORY CZASOWE (Kolejki typu FIFO):
        # Przechowują historię pomiarów, by móc liczyć trendy (pochodne po czasie d/dt)
        self.pressure_buffer = deque()  # Przechowuje krotki: (timestamp, ciśnienie_hpa)
        self.spread_buffer = deque()    # Przechowuje krotki: (timestamp, niedosyt_rosy = T - Td)
        self.solar_buffer = deque()     # Przechowuje krotki: (timestamp, nasłonecznienie_sek)

        # TABLICA 32 STANÓW BAROMETRU ZAMBRETTIEGO (Rozziew od pięknej pogody do sztormu/ulewy)
        self.ZAMBRETTI_TABLE = {
            1: "Settled Fine", 2: "Fine Weather", 3: "Fine, Becoming Less Settled",
            4: "Fairly Fine, Showery Later", 5: "Showery, Becoming More Unsettled",
            6: "Unsettled, Rain Later", 7: "Rain at Times, Worse Later",
            8: "Rain at Times, Becoming Very Unsettled", 9: "Very Unsettled, Rain",
            10: "Settled Fine", 11: "Fine Weather", 12: "Fine, Possibly Showers",
            13: "Fairly Fine, Showers Likely", 14: "Showery, Bright Intervals",
            15: "Changeable, Some Rain", 16: "Unsettled, Rain at Times",
            17: "Rain at Frequent Intervals", 18: "Very Unsettled, Rain", 19: "Stormy, Much Rain",
            20: "Settled Fine", 21: "Fine Weather", 22: "Becoming Fine",
            23: "Fairly Fine, Improving", 24: "Fairly Fine, Possibly Showers Early",
            25: "Showery Early, Improving", 26: "Changeable, Mending",
            27: "Rather Unsettled, Clearing Later", 28: "Unsettled, Probably Improving",
            29: "Unsettled, Short Fine Intervals", 30: "Very Unsettled, Finer at Times",
            31: "Stormy, Possibly Improving", 32: "Stormy, Much Rain"
        }

    @staticmethod
    def calculate_wet_bulb(temp_c, rh_percent):
        """
        FIZYKA ATMOSFERY: Obliczanie Temperatury Mokrego Termometru (Tw) empirycznym wzorem Stulla (2011).
        """
        tw = (temp_c * np.arctan(0.151977 * np.sqrt(rh_percent + 8.313659)) +
              np.arctan(temp_c + rh_percent) - np.arctan(rh_percent - 1.676331) +
              0.00391838 * (rh_percent ** 1.5) * np.arctan(0.023101 * rh_percent) - 4.686035)
        return tw

    def calculate_zambretti(self, press_hpa, trend_3h, season='winter'):
        """
        Matematyczna implementacja algorytmu Zambrettiego na podstawie ciśnienia i trendu 3-godzinnego.
        """
        # Standaryzowane równania Zambrettiego (przelicznik dla ciśnienia na poziomie morza)
        if trend_3h <= -1.5:  # Ciśnienie spada (Falling)
            z = 127 - (0.12 * press_hpa)
        elif trend_3h >= 1.5: # Ciśnienie rośnie (Rising)
            z = 185 - (0.16 * press_hpa)
        else:                  # Ciśnienie stabilne (Steady)
            z = 144 - (0.13 * press_hpa)

        # # Poprawka sezonowa dla zimy
        # if season == 'winter':
        #     if trend_3h <= -1.5:
        #         z -= 1
        #     elif trend_3h >= 1.5:
        #         z += 1

        z_code = int(round(z))
        return max(1, min(32, z_code))

    def process_sample(self, timestamp, temp_c, dp_c, rh_percent, press_hpa, solar_sec=None):
        """
        Przetwarza pojedynczą próbkę danych pogodowych z kroku czasowego.
        """
        spread = temp_c - dp_c

        # 1. Aktualizacja buforów czasowych (FIFO)
        self.pressure_buffer.append((timestamp, press_hpa))
        self.spread_buffer.append((timestamp, spread))
        if solar_sec is not None:
            self.solar_buffer.append((timestamp, solar_sec))

        # Oczyszczanie buforów ze starych pomiarów (> 3 godziny)
        cutoff_time = timestamp - timedelta(hours=3)
        while self.pressure_buffer and self.pressure_buffer[0][0] < cutoff_time:
            self.pressure_buffer.popleft()
        while self.spread_buffer and self.spread_buffer[0][0] < cutoff_time:
            self.spread_buffer.popleft()
        while self.solar_buffer and self.solar_buffer[0][0] < cutoff_time:
            self.solar_buffer.popleft()

        # 2. Obliczenie trendu ciśnienia z ostatnich 3h
        if len(self.pressure_buffer) > 1:
            trend_3h = press_hpa - self.pressure_buffer[0][1]
        else:
            trend_3h = 0.0

        # 3. Liczenie wskaźnika Zambrettiego
        z_code = self.calculate_zambretti(press_hpa, trend_3h, season='winter')

        # 4. Liczenie temperatury mokrego termometru (Tw)
        tw = self.calculate_wet_bulb(temp_c, rh_percent)

        # 5. TRZYSTOPNIOWY FILTR DYNAMICZNY (Ochrona przed fałszywymi alarmami / mgłą)
        
        # Krok 1: Kryterium termiczne (Tw <= 1.0°C – faza opadu śnieg/deszcz marznący)
        thermal_risk = tw <= 1.0

        # Krok 2: Kryterium nasycenia wilgocią (Niedosyt punktu rosy <= 2.0°C)
        saturation_risk = spread <= 2.0

        # Krok 3: Kryterium barometryczno-chmurowe (Zambretti + Nasłonecznienie)
        # Kody Zambrettiego wskazujące na opady/niestabilność:
        precip_zambretti_codes = {4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19, 24, 25, 32}
        zambretti_indicates_precip = (z_code in precip_zambretti_codes) or (trend_3h < -1.0)

        # Detekcja rozpraszania mgły na podstawie nasłonecznienia (brak grubej chmury opadowej)
        solar_clearing = False
        if solar_sec is not None and solar_sec > 600:  # > 10 min silnego słońca w oknie 15-minutowym
            solar_clearing = True

        # Ostateczna flaga zagrożenia opadem zimowym
        hazard_flag = 1 if (thermal_risk and saturation_risk and zambretti_indicates_precip and not solar_clearing) else 0

        return {
            'hazard_flag': hazard_flag,
            'zambretti_code': z_code,
            'zambretti_text': self.ZAMBRETTI_TABLE.get(z_code, "Unknown"),
            'wet_bulb': tw,
            'trend_3h': trend_3h
        }


# =====================================================================
# 2. RAPORT EWALUACJI INŻYNIERYJNEJ (JEDNOSTKI CZASOWE I KOSZTY)
# =====================================================================
def run_engineering_benchmark(file_path):
    print("=" * 75)
    print(f"📖 ŁADOWANIE PLIKU TESTOWEGO: {file_path}")
    print("=" * 75)

    # Wczytanie pliku CSV i uporządkowanie według chronologii czasu
    df = pd.read_csv(file_path)
    if 'data_czas' in df.columns:
        df.rename(columns={'data_czas': 'Timestamp'}, inplace=True)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df.sort_values('Timestamp', inplace=True)

    # Obliczenie wilgotności względnej RH (%) wzorem Augusta-Roche'a-Magnusa (jeśli brak w CSV)
    a, b = 17.625, 243.04
    alpha_t = (a * df['temperatura_powietrza_C']) / (b + df['temperatura_powietrza_C'])
    alpha_dp = (a * df['punkt_rosy_C']) / (b + df['punkt_rosy_C'])
    df['RH_wyliczona'] = np.clip(100 * np.exp(alpha_dp - alpha_t), 0.0, 100.0)

    # Zabezpieczenie na przypadek braku czujnika ciśnienia
    if 'PRESS_cisnienie' not in df.columns:
        df['PRESS_cisnienie'] = 1013.25

    # --- TWORZENIE CELU REFERENCYJNEGO (GROUND TRUTH) ---
    # Patrzymy 4 próbki w przód (czyli o 1 godzinę do przodu przy próbkowaniu co 15 minut).
    # Opad uważamy za groźny zimowo, gdy za godzinę spadnie >0.0001 mm deszczu/śniegu PRZY Temp <= 1.0°C.
    future_opad = df['opad_mm'].shift(-4).fillna(0.0)
    future_temp = df['temperatura_powietrza_C'].shift(-4).fillna(0.0)
    df['TARGET_opad_zimowy'] = ((future_opad > 0.0001) & (future_temp <= 1.0)).astype(int)

    # Inicjalizacja sterownika
    forecaster = EnhancedWinterForecaster()
    hazard_flags = []

    print("🏃 Uruchamianie algorytmu próbka po próbce...")
    for idx, row in df.iterrows():
        ts = row['Timestamp']
        t = float(row['temperatura_powietrza_C'])
        dp = float(row['punkt_rosy_C'])
        rh = float(row['RH_wyliczona'])
        p = float(row['PRESS_cisnienie'])
        solar = float(row['naslonecznienie_sekundy']) if 'naslonecznienie_sekundy' in row else None

        # Pętla wykonuje predykcję dla każdego znacznika czasu
        res = forecaster.process_sample(ts, t, dp, rh, p, solar)
        hazard_flags.append(res['hazard_flag'])

    df['ALGO_FLAGA'] = hazard_flags

    # =====================================================================
    # PRZELICZENIE STANÓW NA GODZINY I JEDNOSTKI INŻYNIERYJNE
    # =====================================================================
    PROBKA_GODZINY = 0.25  # Pomiary są co 15 minut (15 min = 0.25h)

    y_true = df['TARGET_opad_zimowy'].values
    y_pred = df['ALGO_FLAGA'].values

    # Klasyczna Macierz Błędów:
    tp = np.sum((y_true == 1) & (y_pred == 1))  # TP: Trafny opad (Opad nastąpił, system grzał)
    fp = np.sum((y_true == 0) & (y_pred == 1))  # FP: Puste grzanie (System grzał, nic nie spadło)
    fn = np.sum((y_true == 1) & (y_pred == 0))  # FN: Przegapienie (Opad spadł, system NIE grzał)
    tn = np.sum((y_true == 0) & (y_pred == 0))  # TN: Prawidłowy spokój (Brak opadu, brak grzania)

    # Zamiana liczby próbek na czas wyrażony w godzinach:
    godziny_analizy = len(df) * PROBKA_GODZINY
    godziny_opadu_ogolem = np.sum(y_true) * PROBKA_GODZINY
    godziny_wykryte = tp * PROBKA_GODZINY
    godziny_przegapione = fn * PROBKA_GODZINY
    godziny_pustego_grzania = fp * PROBKA_GODZINY

    # Wyznaczenie procentów inżynieryjnych:
    skutecznosc_oslony = (godziny_wykryte / godziny_opadu_ogolem * 100) if godziny_opadu_ogolem > 0 else 0.0
    procent_trafnych_alarmow = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0.0

    # Drukujemy czytelny, inżynieryjny podsumowujący raport w konsoli
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
    print(f"🎯  Trafność alarmu:                    W {procent_trafnych_alarmow:.1f}% przypadków po podniesieniu alarmu FAKTYCZNIE nastąpił opad")
    print("=" * 75)

if __name__ == "__main__":
    sciezka = "Benchmark\\benchmark\\Pogoda_pomiary_15_minut\\suwalki_pogoda_15_min_model_2010.csv"
    run_engineering_benchmark(sciezka)