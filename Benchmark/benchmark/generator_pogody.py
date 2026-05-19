import requests
import pandas as pd
import matplotlib.pyplot as plt  # <-- DODANA BIBLIOTEKA DO WYKRESÓW

def get_wroclaw_15min_historical_forecast():
    print("🌍 Łączenie z API Open-Meteo (Historical Forecast - 15 min)...")
    
    url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
    
    params = {
        "latitude": 51.1079,
        "longitude": 17.0385,
        "start_date": "2024-11-01",
        "end_date": "2025-03-31",
        "minutely_15": [
            "temperature_2m",       
            "dewpoint_2m",          
            "precipitation",        
            "wind_speed_10m",       
            "sunshine_duration"     
        ],
        "timezone": "Europe/Warsaw"
    }
    
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"❌ Błąd serwera API: Kod statusu {response.status_code}")
            print(response.text)
            return None
            
        data = response.json()
        raw_15min = data["minutely_15"]
        
        df = pd.DataFrame({
            'data_czas': pd.to_datetime(raw_15min["time"]),
            'temperatura_powietrza_C': raw_15min["temperature_2m"],
            'punkt_rosy_C': raw_15min["dewpoint_2m"],
            'opad_mm': raw_15min["precipitation"],
            'wiatr_m_s': [round(w / 3.6, 2) for w in raw_15min["wind_speed_10m"]], 
            'naslonecznienie_sekundy': raw_15min["sunshine_duration"]
        })
        
        return df

    except Exception as e:
        print(f"❌ Wystąpił nieoczekiwany błąd: {e}")
        return None


# --- MODYFIKACJA FUNKCJI WYKRESU ---
def pokaz_wykres_kontrolny_grudzien(df):
    print("\n📊 Przygotowywanie wykresu dla tygodnia w grudniu...")
    
    # Kopiujemy dane i ustawiamy czas jako indeks
    df_plot = df.copy()
    df_plot.set_index('data_czas', inplace=True)
    
    # Wycinamy pełny tydzień: od poniedziałku 9 grudnia do niedzieli 15 grudnia 2024
    wycinek = df_plot.loc['2024-12-09':'2024-12-15']
    
    if wycinek.empty:
        print("❌ Brak danych w podanym zakresie grudniowym. Upewnij się, że end_date w API to co najmniej 2024-12-15!")
        return

    fig, ax1 = plt.subplots(figsize=(14, 7))

    # OŚ 1: Temperatura (Linia czerwona)
    color = '#e74c3c'
    ax1.set_xlabel('Data i godzina odczytu (Siatka 15-minutowa)')
    ax1.set_ylabel('Temperatura (°C)', color=color, fontweight='bold')
    ax1.plot(wycinek.index, wycinek['temperatura_powietrza_C'], color=color, linewidth=2, label='Temperatura (°C)')
    ax1.tick_params(axis='y', labelcolor=color)
    
    # Dodanie linii 0°C dla lepszej orientacji w zimowych danych
    ax1.axhline(0, color='black', linestyle='--', linewidth=1.2, alpha=0.7, label='Próg 0°C')
    ax1.grid(True, linestyle='--', alpha=0.5)

    # OŚ 2: Opady (Obszar niebieski)
    ax2 = ax1.twinx()  
    color = '#3498db'
    ax2.set_ylabel('Suma opadów (mm)', color=color, fontweight='bold')
    ax2.fill_between(wycinek.index, wycinek['opad_mm'], color=color, alpha=0.4, label='Opad (mm)')
    ax2.tick_params(axis='y', labelcolor=color)

    # Łączenie legend z obu osi w jedną
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

    plt.title('Kontrola jakośći danych: Tydzień w Grudniu 2024 (Wrocław co 15 minut)', fontsize=14, fontweight='bold', pad=15)
    fig.tight_layout()
    
    print("📈 Wyświetlam okno wykresu...")
    plt.show()

# --- URUCHOMIENIE ---
df_pogoda = get_wroclaw_15min_historical_forecast()

if df_pogoda is not None:
    output_file = "wroclaw_pogoda_15min_model.csv"
    df_pogoda.to_csv(output_file, index=False)
    print(f"\n🎯 ZAKOŃCZONO! Dane zapisane w: {output_file}")
    
    # Odpalamy nowy wykres grudniowy
    pokaz_wykres_kontrolny_grudzien(df_pogoda)
else:
    print("❌ Nie udało się pobrać danych.")