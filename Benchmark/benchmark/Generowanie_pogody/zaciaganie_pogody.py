#!/usr/bin/env python3
"""
Pobieranie historycznych danych pogodowych (godzinowych) z Open-Meteo Archive API
dla wybranych stacji (miasto vs. dzikie tereny) i sezonów zimowych (XI-III).

Wymagania: pip install requests

Źródło danych: Open-Meteo Historical Weather API (reanaliza ERA5-Land)
https://open-meteo.com/en/docs/historical-weather-api
- darmowe, bez klucza API
- spójna metodologia globalnie (ważne dla porównań miasto vs głusza między kontynentami)
- rozdzielczość: GODZINOWA (to realny sufit dla obszarów odległych, np. Syberii/Jukonu -
  tam natywne stacje synoptyczne bywają rzadsze niż godzinowe, więc i tak reanaliza
  ERA5 jest najgęstszym spójnym źródłem)

UWAGA METODOLOGICZNA:
ERA5-Land to dane z modelu reanalizy (assymilacja obserwacji + model atmosferyczny),
NIE surowe odczyty z termometru na słupku. Dla obszarów o gęstej sieci stacji (miasta)
błąd jest zwykle mały, dla dzikich terenów z rzadkimi obserwacjami - większy.
Jeśli w pracy badawczej to istotne, warto to zaznaczyć w metodologii.
"""

import requests
import csv
import time
import os

# ---------------------------------------------------------------------------
# 1. DEFINICJA STACJI (miasto vs głusza, 4 regiony)
# ---------------------------------------------------------------------------
STACJE = [
    {"nazwa": "Krakow",            "region": "Polska",       "typ": "miasto", "lat": 50.0647,  "lon": 19.9450},
    {"nazwa": "Puszcza_Bialowieska","region": "Polska",       "typ": "glusza", "lat": 52.7000,  "lon": 23.8500},
    {"nazwa": "Oslo",              "region": "Skandynawia",  "typ": "miasto", "lat": 59.9139,  "lon": 10.7522},
    {"nazwa": "Abisko",            "region": "Skandynawia",  "typ": "glusza", "lat": 68.3556,  "lon": 18.7877},
    {"nazwa": "Fairbanks",         "region": "Ameryka_Pln",  "typ": "miasto", "lat": 64.8378,  "lon": -147.7164},
    {"nazwa": "Old_Crow",          "region": "Ameryka_Pln",  "typ": "glusza", "lat": 67.5667,  "lon": -139.8333},
    {"nazwa": "Jakuck",            "region": "Syberia",      "typ": "miasto", "lat": 62.0355,  "lon": 129.6755},
    {"nazwa": "Ojmiakon",          "region": "Syberia",      "typ": "glusza", "lat": 63.4608,  "lon": 142.7858},
]

# ---------------------------------------------------------------------------
# 2. SEZONY ZIMOWE (listopad roku Y - marzec roku Y+1)
# ---------------------------------------------------------------------------
SEZONY = [
    (2021, 2022),
    (2022, 2023),
    (2023, 2024),
    (2024, 2025),
    (2025, 2026),
]

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
KATALOG_WYJSCIOWY = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Pogoda_pomiary_15_minut')
)
os.makedirs(KATALOG_WYJSCIOWY, exist_ok=True)

HOURLY_VARS = "temperature_2m,dew_point_2m,precipitation,wind_speed_10m,sunshine_duration"

# Nazewnictwo plików ujednolicone z resztą folderu Pogoda_pomiary_15_minut:
# {lokalizacja}_{rozdzielczosc_w_minutach}min_{rok_startu_okresu}.csv
# - JEDEN plik na (stację, sezon), a nie jeden zbiorczy plik ze wszystkimi sezonami -
#   dzięki temu każdy plik to pojedynczy, ciągły okres bez przerw w danych (co jest
#   wymagane przez symulacja_fizyczna.wczytaj_pogode_1s() - patrz jej docstring).
ROZDZIELCZOSC_MIN = 60   # natywny krok danych z /v1/archive to 1h


def pobierz_dane(stacja, rok_start, rok_koniec):
    """Pobiera dane godzinowe dla jednej stacji i jednego sezonu zimowego."""
    start_date = f"{rok_start}-11-01"
    end_date = f"{rok_koniec}-03-31"

    params = {
        "latitude": stacja["lat"],
        "longitude": stacja["lon"],
        "start_date": start_date,
        "end_date": end_date,
        "hourly": HOURLY_VARS,
        "wind_speed_unit": "ms",       # m/s zamiast domyślnych km/h
        "timezone": "UTC",
    }

    r = requests.get(BASE_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    for stacja in STACJE:
        for rok_start, rok_koniec in SEZONY:
            print(f"Pobieram: {stacja['nazwa']} ({stacja['typ']}, {stacja['region']}) "
                  f"sezon {rok_start}/{rok_koniec}...")
            try:
                dane = pobierz_dane(stacja, rok_start, rok_koniec)
            except requests.exceptions.RequestException as e:
                print(f"  BŁĄD: {e} — pomijam ten sezon")
                continue

            hourly = dane.get("hourly", {})
            czas = hourly.get("time", [])
            temp = hourly.get("temperature_2m", [])
            rosa = hourly.get("dew_point_2m", [])
            opad = hourly.get("precipitation", [])
            wiatr = hourly.get("wind_speed_10m", [])
            slonce = hourly.get("sunshine_duration", [])

            wiersze = []
            for i in range(len(czas)):
                wiersze.append({
                    "data_czas": czas[i],
                    "temperatura_powietrza_C": temp[i] if i < len(temp) else "",
                    "punkt_rosy_C": rosa[i] if i < len(rosa) else "",
                    "opad_mm": opad[i] if i < len(opad) else "",
                    "wiatr_m_s": wiatr[i] if i < len(wiatr) else "",
                    "naslonecznienie_sekundy": slonce[i] if i < len(slonce) else "",
                })

            # JEDEN plik na (stację, sezon) - ciągły, bez przerw w danych.
            # Format nazwy: {lokalizacja}_{rozdzielczosc}min_{rok_startu}.csv
            nazwa_pliku = f"{stacja['nazwa'].lower()}_{ROZDZIELCZOSC_MIN}min_{rok_start}.csv"
            sciezka = os.path.join(KATALOG_WYJSCIOWY, nazwa_pliku)
            with open(sciezka, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "data_czas", "temperatura_powietrza_C", "punkt_rosy_C",
                    "opad_mm", "wiatr_m_s", "naslonecznienie_sekundy",
                ])
                writer.writeheader()
                writer.writerows(wiersze)
            print(f"  Zapisano {len(wiersze)} wierszy -> {sciezka}")

            time.sleep(1)  # uprzejmość wobec darmowego API (limit ok. 10 000 wywołań/dzień)

        print()

    print("Gotowe. Pliki CSV znajdziesz w katalogu:", KATALOG_WYJSCIOWY)


if __name__ == "__main__":
    main()