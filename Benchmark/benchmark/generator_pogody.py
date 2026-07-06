import requests
import pandas as pd
import matplotlib.pyplot as plt

def get_snowy_historical_forecast():
    print("🌍 Łączenie z API Open-Meteo (Atak Śnieżycy - Grudzień 2023)...")
    
    url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
    
    params = {
        "latitude": 50.04,  # Współrzędne południowo-wschodniej Polski (Rzeszów i okolice)
        "longitude": 22.00, # Tam zasypało drogi i tory całkowicie w grudniu 2023
        "start_date": "2023-12-01",
        "end_date": "2023-12-25",
        "minutely_15": [
            "temperature_2m",       
            "dewpoint_2m",          
            "precipitation",  # Łączny opad (w ujemnej temperaturze to czysty śnieg)      
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


def pokaz_wykres_kontrolny_snieg(df):
    print("\n📊 Przygotowywanie wykresu dla śnieżnego kataklizmu...")
    
    df_plot = df.copy()
    df_plot.set_index('data_czas', inplace=True)
    
    # Wycinamy najciekawszy okres: pierwsze dwa tygodnie grudnia 2023
    wycinek = df_plot.loc['2023-12-01':'2023-12-10']
    
    if wycinek.empty:
        print("❌ Brak danych w podanym zakresie.")
        return

    fig, ax1 = plt.subplots(figsize=(14, 7))

    # OŚ 1: Temperatura (Linia czerwona)
    color = '#e74c3c'
    ax1.set_xlabel('Data i godzina odczytu (Siatka 15-minutowa)')
    ax1.set_ylabel('Temperatura (°C)', color=color, fontweight='bold')
    ax1.plot(wycinek.index, wycinek['temperatura_powietrza_C'], color=color, linewidth=2, label='Temperatura (°C)')
    ax1.tick_params(axis='y', labelcolor=color)
    
    ax1.axhline(0, color='black', linestyle='--', linewidth=1.2, alpha=0.7, label='Próg 0°C')
    ax1.grid(True, linestyle='--', alpha=0.5)

    # OŚ 2: Opady (Obszar jasnoniebieski)
    ax2 = ax1.twinx()  
    color = '#34495e'
    ax2.set_ylabel('Intensywność śnieżycy (mm opadu / 15min)', color=color, fontweight='bold')
    ax2.fill_between(wycinek.index, wycinek['opad_mm'], color='#3498db', alpha=0.5, label='Opad (śnieg w ujemnej temp.)')
    ax2.tick_params(axis='y', labelcolor=color)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

    plt.title('Kontrola jakości danych: Rekordowe Śnieżyce w Polsce (Grudzień 2023, krok 15-minutowy)', fontsize=14, fontweight='bold', pad=15)
    fig.tight_layout()
    
    print("📈 Wyświetlam okno wykresu...")
    plt.show()

# --- URUCHOMIENIE ---
df_pogoda = get_snowy_historical_forecast()

if df_pogoda is not None:
    # 💡 Zapisujemy dokładnie pod taką samą nazwą, jakiej szuka Twój zintegrowany skrypt!
    output_file = "suwalki_pogoda_15_min_model.csv" 
    df_pogoda.to_csv(output_file, index=False)
    print(f"\n🎯 ZAKOŃCZONO! Ekstremalnie śnieżne dane zapisane w: {output_file}")
    
    # Odpalamy wykres sprawdzający
    pokaz_wykres_kontrolny_snieg(df_pogoda)
else:
    print("❌ Nie udało się pobrać danych.")