import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =====================================================================
# 1. KLASA STEROWNIKA (TWÓJ ALGORYTM)
# =====================================================================
class RailHeatingController:
    def __init__(self, target_temp=4.0, hysteresis=1.0):
        self.target_temp = target_temp      
        self.hysteresis = hysteresis        
        self.heating_on = False
        
        # Pamięć wewnętrzna – licznik czasu trwania niebezpiecznego opadu
        self.rain_duration_seconds = 0

    def calculate_risk_level(self, row_data) -> int:
        """
        Metoda oceniająca ryzyko oblodzenia w skali od 0 do 10.
        Ryzyko rośnie liniowo wraz z czasem trwania opadu w niskiej temperaturze.
        """
        at = float(row_data['AT_temp_powietrza'])
        rh = float(row_data['RH_wilgotnosc'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        crt = float(row_data.get('CRT_temp_niegrzana', at))

        is_raining = precip > 0.0001
        is_snowing = snow > 0.0001

        # LINIOWY WZROST PAMIĘCI: Jeśli pada przy mrozie/blisko zera, akumulujemy sekundy
        if (is_raining or is_snowing) and at <= 1.0:
            self.rain_duration_seconds += 1
        else:
            # Gdy opad ustaje, licznik powoli maleje
            self.rain_duration_seconds = max(0, self.rain_duration_seconds - 5)

        # --- 10 & 9: MARZNĄCY DESZCZ / DŁUGOTRWAŁY OPAD (Krytyczne zagrożenie) ---
        if is_raining and (crt <= 1.0 or at <= 1.0):
            # Im dłużej pada, tym wyższe ryzyko (liniowy wzrost w czasie)
            if self.rain_duration_seconds > 1800:   # Powyżej 30 minut ulewy -> krytyk
                return 10
            elif self.rain_duration_seconds > 600:  # Powyżej 10 minut
                return 9
            return 8

        # --- 8 & 7: INTENSYWNY ŚNIEG / ZASYPYWANIE ---
        if is_snowing and crt <= 2.0:
            if self.rain_duration_seconds > 1800:
                return 8
            return 7

        # --- 6 & 5: WILGOĆ I MRÓZ (Szron, punkt rosy) ---
        if crt <= 0.5 and rh > 85.0:
            return 6 if rh > 95.0 else 5       

        # --- 4 & 3: SUCHY MRÓZ ---
        if crt <= -3.0:
            return 4                           
        if crt <= 0.0:
            return 3                           

        # --- 2 & 1: POTENCJALNE ZAGROŻENIE ---
        if (is_raining or is_snowing) and crt <= 3.0:
            return 2                           
        if at <= 3.0:
            return 1                           

        return 0


# =====================================================================
# 2. POMOCNICZE FUNKCJE MATEMATYCZNE I GENERATOR ETYKIET
# =====================================================================
def calculate_relative_humidity(temp, dew_point):
    """Wyliczanie wilgotności względnej % ze wzoru Augusta-Roche'a-Magnusa"""
    a = 17.625
    b = 243.04
    alpha_tr = (a * temp) / (b + temp)
    alpha_dp = (a * dew_point) / (b + dew_point)
    rh = 100 * np.exp(alpha_dp - alpha_tr)
    return np.clip(rh, 0.0, 100.0)

def generate_reference_labels(df):
    """
    Generuje płynne, referencyjne poziomy ryzyka (0.0 - 10.0), analizując CAŁE SPEKTRUM
    nadchodzących warunków pogodowych w oknie 1 godziny w przód. Dzięki temu etykiety
    uwzględniają bezwładność cieplną szyny i potrzebę wyprzedzenia grzewczego.
    """
    # KROK 1: ANALIZA SPEKTRUM PRZYSZŁOŚCI (Sprytny trik z odwróconym oknem kroczącym)
    # Patrzymy 3600 sekund (1 godzina) w przód, żeby wiedzieć, co nadchodzi
    print("🔮 Analiza spektrum przyszłości: Obliczanie trendów długoterminowych...")
    
    # Odwracamy serię, liczymy rolling min/sum i odwracamy z powrotem, by poznać przyszłość
    future_window = 3600  # 1 godzina w sekundach
    
    df['future_min_temp'] = df['temperatura_powietrza_C'].iloc[::-1].rolling(window=future_window, min_periods=1).min().iloc[::-1]
    df['future_total_opad'] = df['opad_mm'].iloc[::-1].rolling(window=future_window, min_periods=1).sum().iloc[::-1]
    df['future_max_rh'] = df['RH_wyliczona'].iloc[::-1].rolling(window=future_window, min_periods=1).max().iloc[::-1]

    ref_risks = []
    rain_counter = 0.0
    
    # KROK 2: ITERACYJNE WYLICZANIE RYZYKA Z UWZGLĘDNIENIEM PRZYSZŁOŚCI
    for idx, row in df.iterrows():
        at = row['temperatura_powietrza_C']
        rh = row['RH_wyliczona']
        opad = row['opad_mm']
        
        # Pobieramy dane o nadchodzącym spektrum pogody dla tej konkretnej sekundy
        f_min_temp = row['future_min_temp']
        f_total_opad = row['future_total_opad']
        f_max_rh = row['future_max_rh']
        
        is_opad = opad > 0.0001
        is_opad_w_przyszlosci = f_total_opad > 0.01  # czy w ciągu godziny spadnie łącznie jakaś woda/śnieg
        
        # --- REJESTRATOR HISTORII ---
        if is_opad and at <= 2.0:
            intensywnosc_mnoznik = max(1.0, opad / 0.0005)
            rain_counter += 1.0 * intensywnosc_mnoznik
        else:
            rain_counter = max(0.0, rain_counter - 5.0)
            
        # --- MATRYCA RYZYKA OPARTA O SPEKTRUM (TERAZ + PRZYSZŁOŚĆ) ---
        
        # [STAN KRYTYCZNY: NADCHODZĄCY KATAKLIZM] 
        # Teraz może być spokojnie (+1°C, lekka mżawka), ale spektrum godziny pokazuje uderzenie mrozu i ulewę.
        # Wymuszamy natychmiastowe ryzyko 9-10, by zmusić grzałki do uderzenia wyprzedzającego.
        if is_opad_w_przyszlosci and f_min_temp <= 0.5:
            base_risk = 8.0
            # Skalujemy ryzyko w zależności od tego, jak silny opad idzie i jak głęboki mróz nadchodzi
            temp_severity = min(1.0, abs(min(0.0, f_min_temp)) / 5.0)  # max dla -5°C
            opad_severity = min(1.0, f_total_opad / 5.0)               # skumulowany opad z godziny
            
            risk = base_risk + (temp_severity * 1.0) + (opad_severity * 1.0)

        # [STAN 2: TRWAJĄCY MARZNĄCY OPAD LUB ŚNIEŻYCA]
        elif is_opad and at <= 1.0:
            base_risk = 7.5
            duration_bonus = min(1.5, rain_counter / 1200.0)
            intensity_bonus = min(1.0, opad / 0.0015)
            risk = base_risk + duration_bonus + intensity_bonus
            
        # [STAN 3: OPAD W STREFIE ZERA]
        elif is_opad and at <= 2.0:
            base_risk = 6.0
            duration_bonus = min(1.5, rain_counter / 1500.0)
            intensity_bonus = min(1.0, opad / 0.0020)
            risk = base_risk + duration_bonus + intensity_bonus
            
        # [STAN 4: NADCHODZĄCY SZRON / MGŁA ROSY]
        # Nie pada, ale widzimy w spektrum, że wilgotność za chwilę dobije do 100% przy ujemnej temperaturze
        elif (at <= 0.5 or f_min_temp <= 0.5) and f_max_rh > 90.0:
            rh_gap = (f_max_rh - 90.0) / 10.0  # 0.0 do 1.0
            risk = 4.5 + (rh_gap * 2.0)
            
        # [STAN 5: WILGOĆ I LEKKI MRÓZ (AKTUALNY SZRON)]
        elif at <= 0.5 and rh > 85.0:
            rh_scale = (rh - 85.0) / 15.0
            risk = 4.0 + (rh_scale * 2.5)
            
        # [STAN 6: SUCHY MRÓZ]
        elif at <= 0.0:
            risk = 1.0 + min(3.0, abs(at) / 5.0)
            
        # [STAN 7: AKTUALNY OPAD NA PLUSIE LUB DROBNE ZIMNO]
        elif is_opad and at <= 3.0:
            risk = 1.0 + (3.0 - at) * 0.5
        elif at <= 3.0:
            risk = (3.0 - at) * 0.33
        else:
            risk = 0.0

        # Niezależnie od opadów, poniżej -10°C ryzyko drastycznie wymusza grzanie, a przy -15°C osiąga maksimum.
        if at <= -10.0:
            if at <= -15.0:
                risk = 10.0  # Krytyczny mróz konstrukcyjny - pełna blokada na 10
            else:
                # Płynna interpolacja liniowa przyrostu ryzyka (0.0 dla -10°C, 1.0 dla -15°C)
                progres_mrozu = (at - (-10.0)) / (-15.0 - (-10.0))
                # Bezpiecznie podnosimy aktualną wartość ryzyka w stronę 10.0
                risk = max(risk, risk + (10.0 - risk) * progres_mrozu)
            
        final_risk = max(0.0, min(10.0, risk))
        ref_risks.append(final_risk)
        
    # Czyszczenie kolumn pomocniczych, żeby nie śmiecić w pliku cache
    df['REF_RYZYKO'] = ref_risks
    df.drop(columns=['future_min_temp', 'future_total_opad', 'future_max_rh'], inplace=True)
    return df


# =====================================================================
# 3. GŁÓWNY PROCES WALIDACJI I AGREGACJI GODZINOWEJ
# =====================================================================
def run_validation(file_path):
    if not os.path.exists(file_path):
        print(f"❌ Błąd: Plik {file_path} nie istnieje!")
        return

    # --- AUTOMATYCZNE ZARZĄDZANIE PLIKIEM CACHE W TYM SAMYM FOLDERZE ---
    folder = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    name_no_ext, ext = os.path.splitext(base_name)
    # Plik cache powstanie dokładnie tam, gdzie plik wejściowy
    cache_file_path = os.path.join(folder, f"{name_no_ext}_1s_cache{ext}")

    # Sprawdzamy, czy plik cache już istnieje
    if os.path.exists(cache_file_path):
        print(f"📦 Znaleziono gotowy plik cache: {cache_file_path}")
        print("⏳ Ładowanie przygotowanych danych 1-sekundowych (pomijam interpolację i generowanie etykiet)...")
        df_1s = pd.read_csv(cache_file_path)
        df_1s['Timestamp'] = pd.to_datetime(df_1s['Timestamp'])
        print(f"📊 Załadowano bazę. Liczba próbek 1-sekundowych: {len(df_1s)}")
    else:
        print(f"✨ Brak pliku cache. Rozpoczynam pełne przetwarzanie surowych danych...")
        
        # A. Wczytanie danych
        print(f"📖 Wczytywanie pliku surowego: {file_path}")
        df_raw = pd.read_csv(file_path)
        
        if 'data_czas' in df_raw.columns:
            df_raw.rename(columns={'data_czas': 'Timestamp'}, inplace=True)
            
        # Przycinamy do 1 tygodnia (672 wiersze 15-minutowe)
        df_15min = df_raw.head(672).copy()
        df_15min['Timestamp'] = pd.to_datetime(df_15min['Timestamp'])
        df_15min.set_index('Timestamp', inplace=True)

        # B. Interpolacja do 1 sekundy
        print("⏳ Interpolacja danych do 1 sekundy (tworzenie gęstej osi czasu)...")
        df_1s = df_15min.resample('1s').asfreq()
        df_1s['temperatura_powietrza_C'] = df_1s['temperatura_powietrza_C'].interpolate(method='linear')
        df_1s['punkt_rosy_C'] = df_1s['punkt_rosy_C'].interpolate(method='linear')
        df_1s['wiatr_m_s'] = df_1s['wiatr_m_s'].interpolate(method='linear')
        df_1s['opad_mm'] = df_1s['opad_mm'].ffill() / 900.0  # Rozbicie sumy opadu na sekundy
        df_1s.reset_index(inplace=True)
        print(f"📊 Zagęszczono bazę. Liczba próbek 1-sekundowych: {len(df_1s)}")

        # C. Przygotowanie zmiennych wejściowych
        df_1s['RH_wyliczona'] = calculate_relative_humidity(df_1s['temperatura_powietrza_C'], df_1s['punkt_rosy_C'])
        
        # D. Wygenerowanie etykiet referencyjnych (Ground Truth)
        df_1s = generate_reference_labels(df_1s)

        # Zapisujemy w pełni gotowy plik jako cache na przyszłość
        print(f"💾 Zapisywanie przetworzonych danych do pamięci podręcznej: {cache_file_path}")
        df_1s.to_csv(cache_file_path, index=False)

    # E. Uruchomienie Twojego algorytmu sekunda po sekundzie (Zawsze uruchamiane)
    print("🏃 Symulacja: Twój algorytm przetwarza dane sekunda po sekundzie...")
    controller = RailHeatingController()
    calculated_risks = []

    for _, row in df_1s.iterrows():
        is_mroz = row['temperatura_powietrza_C'] <= 0.0
        row_data = {
            'AT_temp_powietrza': row['temperatura_powietrza_C'],
            'RH_wilgotnosc': row['RH_wyliczona'],
            'PRECIP_opad': 0.0 if is_mroz else row['opad_mm'],
            'SNOW_snieg': row['opad_mm'] if is_mroz else 0.0,
            'CRT_temp_niegrzana': row['temperatura_powietrza_C']
        }
        calculated_risks.append(controller.calculate_risk_level(row_data))

    df_1s['ALGO_RYZYKO'] = calculated_risks

    # =====================================================================
    # AGREGACJA DO POSTACI GODZINOWEJ DLA ANALIZY TRENDÓW
    # =====================================================================
    print("\n📊 Agregowanie wyników sekundy -> godziny dla dokładnej analizy...")
    df_1s.set_index('Timestamp', inplace=True)
    
    df_hourly = df_1s.resample('1h').agg({
        'temperatura_powietrza_C': 'mean',
        'opad_mm': 'sum',  
        'REF_RYZYKO': 'mean',
        'ALGO_RYZYKO': 'mean'
    }).reset_index()

    # E. WYŚWIETLENIE ANALIZY GODZINOWEJ W KONSOLI (Pokazuje pierwsze 24 godziny testu)
    print("\n🔎 PODGLĄD GODZINA PO GODZINIE (Pierwsza doba symulacji):")
    print(f"{'Data i Godzina':<20} | {'Temp [°C]':<9} | {'Opad [mm/h]':<11} | {'Ryzyko REF':<10} | {'Ryzyko ALGO':<11}")
    print("-" * 70)
    for _, row in df_hourly.head(24).iterrows():
        opad_godzinowy = row['opad_mm'] * 900 
        print(f"{row['Timestamp'].strftime('%Y-%m-%d %H:%M'):<20} | {row['temperatura_powietrza_C']:9.2f} | {opad_godzinowy:11.4f} | {row['REF_RYZYKO']:10.1f} | {row['ALGO_RYZYKO']:11.1f}")

    # F. Statystyki błędu na danych godzinowych
    df_hourly['Blad'] = np.abs(df_hourly['REF_RYZYKO'] - df_hourly['ALGO_RYZYKO'])
    print("\n================ STATYSTYKI JAKOŚCI (UJĘCIE GODZINOWE) ================")
    print(f"📐 Średni błąd godzinowy:  {df_hourly['Blad'].mean():.4f} pkt")
    print(f"🚨 Maksymalny błąd:        {df_hourly['Blad'].max():.1f} pkt")
    print("=======================================================================")

    # W tym miejscu znajduje się sekcja G (generowanie interaktywnego wykresu), którą dodałeś wcześniej...

# G. GENEROWANIE ROZBUDOWANEGO INTERAKTYWNEGO WYKRESU Z PRZEWIJANIEM CO 24H
    print("\n📈 Uruchamianie rozbudowanego wykresu interaktywnego (Przegląd w oknach 24-godzinnych)...")
    from matplotlib.widgets import Button

    # ZABEZPIECZENIE: Upewniamy się, że wilgotność jest w df_hourly, jeśli nie została dodana wcześniej
    if 'RH_wyliczona' not in df_hourly.columns and 'df_1s' in locals():
        df_1s_temp = df_1s.copy()
        if 'Timestamp' not in df_1s_temp.columns:
            df_1s_temp = df_1s_temp.reset_index()
        df_rh_hourly = df_1s_temp.set_index('Timestamp').resample('1h').agg({'RH_wyliczona': 'mean'}).reset_index()
        df_hourly['RH_wyliczona'] = df_rh_hourly['RH_wyliczona']

    # Tworzymy 3 podwykresy dzielące wspólną oś X
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    plt.subplots_adjust(bottom=0.12, hspace=0.25) 

    # --- PANEL 1: POZIOMY RYZYKA ---
    ax1.plot(df_hourly['Timestamp'], df_hourly['REF_RYZYKO'], label='Referencyjne Ryzyko (Ekspert)', color='green', linewidth=2)
    ax1.plot(df_hourly['Timestamp'], df_hourly['ALGO_RYZYKO'], label='Twoje Ryzyko (ALGO)', color='red', linestyle='--', linewidth=2)
    ax1.set_ylabel('Ryzyko (0-10)', fontweight='bold')
    ax1.set_ylim(-0.5, 10.5)
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='upper right')

    # --- PANEL 2: TEMPERATURA I WILGOTNOŚĆ (DWIE OSIE Y) ---
    color_temp = 'blue'
    ax2.plot(df_hourly['Timestamp'], df_hourly['temperatura_powietrza_C'], label='Temperatura powietrza', color=color_temp, linewidth=1.5)
    ax2.set_ylabel('Temperatura [°C]', color=color_temp, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor=color_temp)
    ax2.grid(True, linestyle=':', alpha=0.6)

    # Druga oś Y dla wilgotności na tym samym panelu
    ax2_twin = ax2.twinx()
    color_rh = 'orange'
    ax2_twin.plot(df_hourly['Timestamp'], df_hourly['RH_wyliczona'], label='Wilgotność (RH)', color=color_rh, linestyle=':', linewidth=1.5)
    ax2_twin.set_ylabel('Wilgotność [%]', color=color_rh, fontweight='bold')
    ax2_twin.tick_params(axis='y', labelcolor=color_rh)
    ax2_twin.set_ylim(-5, 105)

    # Wspólna legenda dla temperatury i wilgotności
    lines2, labels2 = ax2.get_legend_handles_labels()
    lines2_tw, labels2_tw = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines2 + lines2_tw, labels2 + labels2_tw, loc='upper right')

    # --- PANEL 3: OPADY ATMOSFERYCZNE ---
    # Ponieważ wartości w sekundach były bardzo małe, prezentujemy zsumowany opad godzinowy
    ax3.bar(df_hourly['Timestamp'], df_hourly['opad_mm'], width=0.03, label='Suma opadu w ciągu godziny', color='purple', alpha=0.6)
    ax3.set_ylabel('Opad [mm/h]', color='purple', fontweight='bold')
    ax3.tick_params(axis='y', labelcolor='purple')
    ax3.grid(True, linestyle=':', alpha=0.6)
    ax3.legend(loc='upper right')
    ax3.set_xlabel('Data i Czas', fontweight='bold')

    # Parametry stronicowania (24 godziny)
    hours_per_page = 24
    total_hours = len(df_hourly)
    
    # Klasa sterująca przesuwaniem okna czasowego
    class ChartNavigator:
        def __init__(self):
            self.current_offset = 0

        def update_view(self):
            start_idx = self.current_offset
            end_idx = min(self.current_offset + hours_per_page, total_hours - 1)
            
            start_time = df_hourly['Timestamp'].iloc[start_idx]
            end_time = df_hourly['Timestamp'].iloc[end_idx]
            
            # sharex=True sprawia, że ustawienie xlim na ax1 automatycznie przesunie ax2 i ax3
            ax1.set_xlim(start_time, end_time)
            
            # Dynamiczny tytuł główny całego okna
            fig.suptitle(f"Analiza Sterownika EOR | Okno: {start_time.strftime('%d.%m %H:%M')} do {end_time.strftime('%d.%m %H:%M')}", fontsize=14, fontweight='bold')
            fig.canvas.draw_idle()

        def next_page(self, event):
            if self.current_offset + hours_per_page < total_hours:
                self.current_offset += hours_per_page
                self.update_view()

        def prev_page(self, event):
            if self.current_offset - hours_per_page >= 0:
                self.current_offset -= hours_per_page
                self.update_view()

    # Uruchomienie widoku początkowego
    navigator = ChartNavigator()
    navigator.update_view()

    # Definicja i pozycjonowanie przycisków nawigacyjnych na samym dole figury
    ax_prev = plt.axes([0.35, 0.02, 0.12, 0.04])
    ax_next = plt.axes([0.53, 0.02, 0.12, 0.04])
    
    btn_prev = Button(ax_prev, '◀ Poprzednie 24h', color='lightgray', hovercolor='tomato')
    btn_next = Button(ax_next, 'Następne 24h ▶', color='lightgray', hovercolor='tomato')
    
    btn_prev.on_clicked(navigator.prev_page)
    btn_next.on_clicked(navigator.next_page)

    # Przechowanie referencji do przycisków, zapobiegające usunięciu ich przez Garbage Collector
    ax1._nav_buttons = [btn_prev, btn_next]

    print("💡 Wykres otworzy się w osobnym oknie. Przyciskami na dole możesz analizować pełne korelacje pogody i ryzyka!")
    plt.show()

if __name__ == "__main__":
    # Nazwa Twojego surowego pliku CSV
    sciezka_do_pliku = "Benchmark\\benchmark\\Pogoda_pomiary_15_minut\\suwalki_pogoda_15_min_model_2010.csv" 
    run_validation(sciezka_do_pliku)