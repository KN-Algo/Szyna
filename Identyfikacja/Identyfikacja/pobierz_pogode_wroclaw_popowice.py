# Identyfikacja/Identyfikacja/pobierz_pogode_wroclaw_popowice.py
#
# DODATKOWY skrypt (nie dotyczy referencyjnych plików identyfikacyjnych) -
# pobiera z Open-Meteo (historical-forecast-api, TEN SAM wzorzec co
# Benchmark/benchmark/Generowanie_pogody/generator_pogody.py) dane wiatru i
# nasłonecznienia dla DOKŁADNEJ lokalizacji szyny: Wrocław Popowice,
# 51.121933, 17.005006 - na cały okres pokryty logiem urządzenia
# (algo (4).log, 2026-04-15 -> 2026-05-06), siatka 15-minutowa (najgęstsza
# dostępna w API).
#
# Zapisuje do OSOBNEGO pliku (na życzenie użytkownika) - pogoda_wroclaw_popowice_15min.csv
# - identyfikacja_miso.py wczytuje go OSOBNO i dołącza WIATR/NASŁONECZNIENIE
# jako dwa dodatkowe kanały do tej samej analizy wpływu (patrz tam).
#
# Uruchomienie: python pobierz_pogode_wroclaw_popowice.py

import os
import requests
import pandas as pd

LATITUDE = 51.121933
LONGITUDE = 17.005006
START_DATE = "2026-04-15"
END_DATE = "2026-05-07"  # dzień zapasu na koniec (log kończy się 2026-05-06 11:58)

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pogoda_wroclaw_popowice_15min.csv")


def pobierz():
    print(f"Łączenie z API Open-Meteo (Wrocław Popowice, {LATITUDE}, {LONGITUDE})...")
    url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "minutely_15": [
            "temperature_2m",
            "wind_speed_10m",
            "sunshine_duration",
        ],
        "timezone": "Europe/Warsaw",
    }
    response = requests.get(url, params=params, timeout=60)
    if response.status_code != 200:
        print(f"BŁĄD serwera API: kod {response.status_code}")
        print(response.text)
        return None

    data = response.json()
    raw = data["minutely_15"]
    df = pd.DataFrame({
        'Timestamp': pd.to_datetime(raw["time"]),
        'AT_openmeteo_C': raw["temperature_2m"],       # do walidacji krzyżowej z AT z logu urządzenia
        'wiatr_m_s': [round(w / 3.6, 2) if w is not None else None for w in raw["wind_speed_10m"]],
        'naslonecznienie_sekundy': raw["sunshine_duration"],
    })
    print(f"Pobrano {len(df)} próbek (siatka 15-min), {df['Timestamp'].min()} -> {df['Timestamp'].max()}")
    print(f"  Wiatr: {df['wiatr_m_s'].min():.2f} - {df['wiatr_m_s'].max():.2f} m/s "
          f"(średnio {df['wiatr_m_s'].mean():.2f})")
    print(f"  Nasłonecznienie: {df['naslonecznienie_sekundy'].min():.0f} - "
          f"{df['naslonecznienie_sekundy'].max():.0f} s/15min "
          f"(średnio {df['naslonecznienie_sekundy'].mean():.0f})")
    return df


if __name__ == "__main__":
    df = pobierz()
    if df is not None:
        df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
        print(f"\nZapisano: {OUTPUT_FILE}")
    else:
        print("Nie udało się pobrać danych.")
