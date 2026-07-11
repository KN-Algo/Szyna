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
    Generuje płynne, referencyjne poziomy ryzyka (Ground Truth) w skali od 0.0 do 10.0.
    Eliminuje skokowe progi na rzecz ciągłych funkcji uzależnionych od czasu trwania 
    oraz chwilowej intensywności opadu (im silniejszy opad, tym szybciej rośnie ryzyko).
    """
    ref_risks = []
    rain_counter = 0.0
    
    for _, row in df.iterrows():
        at = row['temperatura_powietrza_C']
        rh = row['RH_wyliczona']
        opad = row['opad_mm']  # Intensywność opadu w [mm/s]
        
        is_opad = opad > 0.0001
        
        # --- 1. REJESTRATOR HISTORII (DYNAMICZNA AKUMULACJA OPADU) ---
        # Licznik sekund rośnie nieliniowo w zależności od intensywności opadu.
        # Silna śnieżyca czy ulewa degraduje rozjazd znacznie szybciej niż mała mżawka.
        if is_opad and at <= 2.0:
            # Bazowo dodajemy +1 sekundę, ale mocny opad (skalowany względem 0.0005 mm/s)
            # drastycznie przyspiesza przyrost licznika (mnożnik intensywności).
            intensywnosc_mnoznik = max(1.0, opad / 0.0005)
            rain_counter += 1.0 * intensywnosc_mnoznik
        else:
            # Bezwładność wysychania/topnienia: po ustaniu opadu ryzyko nie spada do zera od razu.
            # Szyna wraca do stanu suchego powoli (licznik maleje o 5 sekund na każdą sekundę bez opadu).
            rain_counter = max(0.0, rain_counter - 5.0)
            
        # --- 2. PŁYNNA MATRYCA WARUNKÓW POGODOWYCH (0.0 - 10.0) ---
        
        # [PROG BEZPIECZEŃSTWA] Ciepłe powietrze uniemożliwia powstanie lodu/szronu
        if at > 4.0:
            risk = 0.0
            
        # [WARUNEK 1: MARZNĄCY DESZCZ / ŚNIEŻYCA PRZY MROZIE - TABELA 5]
        # Krytyczny stan (opad przy temperaturze <= 1.0°C). Ryzyko płynnie dąży do absolutnego max (10.0).
        elif is_opad and at <= 1.0:
            base_risk = 7.5  # Startujemy z wysokiego pułapu, bo sytuacja od razu jest groźna
            
            # Wpływ czasu: Ryzyko rośnie płynnie o max +1.5 wraz z upływem minut (pełen efekt po ~20 min opadu)
            duration_bonus = min(1.5, rain_counter / 1200.0)
            
            # Wpływ intensywności: Im więcej śniegu/deszczu leci w tej sekundzie, tym mocniej 
            # dobijamy ryzyko w górę (max +1.0 dla ulewy powyżej 0.0015 mm/s)
            intensity_bonus = min(1.0, opad / 0.0015)
            
            risk = base_risk + duration_bonus + intensity_bonus
            
        # [WARUNEK 2: OPAD W STREFIE PRZEJŚCIOWEJ WOKÓŁ ZERA - TABELA 5]
        # Śnieg lub deszcz przy lekkim plusie (1.0°C do 2.0°C). Ryzyko narasta płynnie w przedziale 6.0 - 8.5.
        elif is_opad and at <= 2.0:
            base_risk = 6.0
            duration_bonus = min(1.5, rain_counter / 1500.0)  # wolniejszy przyrost czasu niż przy głębokim mrozie
            intensity_bonus = min(1.0, opad / 0.0020)         # duża ilość śniegu potrafi mocno podbić ten stan
            
            risk = base_risk + duration_bonus + intensity_bonus
            
        # [WARUNEK 3: WILGOĆ I LEKKI MRÓZ BEZ OPADÓW - KONDENSACJA / SZRON]
        # Nie pada z nieba, ale szyna ma poniżej 0.5°C, a wilgotność przekracza 85%.
        # Ryzyko rośnie całkowicie liniowo od 4.0 (dla RH=85%) do 6.5 (dla skrajnej mgły RH=100%).
        elif at <= 0.5 and rh > 85.0:
            # Mapujemy nadwyżkę wilgotności (przedział 85%-100%) na wartość od 0.0 do 1.0
            rh_scale = (rh - 85.0) / 15.0
            risk = 4.0 + (rh_scale * 2.5)
            
        # [WARUNEK 4: SUCHY, GŁĘBOKI MRÓZ - TABELA 6]
        # Brak opadów i brak szronu, ale stal się kurczy i gęstnieją smary mechaniczne zwrotnicy.
        # Ryzyko profilaktyczne rośnie liniowo: dla 0°C wynosi 1.0 pkt, a dla silnego mrozu -15°C osiąga 4.0 pkt.
        elif at <= 0.0:
            # Każde 5 stopni mrozu gładko podnosi ryzyko o +1.0 punktu
            risk = 1.0 + min(3.0, abs(at) / 5.0)
            
        # [WARUNEK 5: OPAD PRZY DODATNIEJ TEMPERATURZE - PROFILAKTYKA PRZED PRZYMROZKIEM]
        # Pada deszcz przy temperaturze od 2.0°C do 3.0°C. Ryzyko rośnie płynnie, im bliżej zera jest temperatura.
        elif is_opad and at <= 3.0:
            risk = 1.0 + (3.0 - at) * 0.5
            
        # [WARUNEK 6: ZIMNO, SUCHO I BEZPIECZNIE]
        # Temperatura lekko plusowa (do 3.0°C), brak jakichkolwiek zjawisk. Ryzyko jest śladowe (0.0 - 1.0).
        elif at <= 3.0:
            risk = (3.0 - at) * 0.33
            
        else:
            risk = 0.0
            
        # Ścisłe zabezpieczenie matematyczne przed wyjściem poza ramy skali 0-10
        final_risk = max(0.0, min(10.0, risk))
        ref_risks.append(final_risk)
        
    df['REF_RYZYKO'] = ref_risks
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