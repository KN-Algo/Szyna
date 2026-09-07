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
# 1. DEFINICJA STACJI - pełna lista 44 lokalizacji użytkownika (2026-09-03),
#    MINUS Wrocław (świadomie WYŁĄCZONY z tego skryptu - jego istniejący plik
#    `wroclaw_15min_2024.csv` pochodzi z INNEGO źródła, natywnej rozdzielczości
#    15-min z historical-forecast-api - patrz Generowanie_pogody/generator_pogody.py
#    - i użytkownik wyraźnie poprosił, żeby ten konkretny plik ZOSTAŁ nietknięty,
#    nie nadpisywany przez ten skrypt). Pozostałe 43 lokalizacje pobierane TĄ
#    SAMĄ metodą (Open-Meteo /v1/archive, ERA5-Land, godzinowe) dla spójności
#    metodologicznej między wszystkimi lokalizacjami (patrz nagłówek pliku).
#
#    Współrzędne = centrum miasta/miejscowości z listy użytkownika. ERA5-Land to
#    reanaliza na siatce ~9-11km pokrywającej CAŁY ląd globu, więc każda z tych
#    współrzędnych automatycznie dostaje dane z najbliższej komórki siatki - nie
#    ma tu "białych plam" wymagających ręcznego szukania zastępczej stacji w
#    okolicy (w odróżnieniu od sieci stacji naziemnych, gdzie takie dziury
#    faktycznie by wystąpiły).
STACJE = [
    # --- Pierwotne 9 (bez Wrocławia) ---
    {"nazwa": "Abisko",                     "region": "Szwecja",             "lat": 68.3556,  "lon": 18.7877},
    {"nazwa": "Fairbanks",                  "region": "USA (Alaska)",        "lat": 64.8378,  "lon": -147.7164},
    {"nazwa": "Jakuck",                     "region": "Rosja",               "lat": 62.0355,  "lon": 129.6755},
    {"nazwa": "Krakow",                     "region": "Polska",              "lat": 50.0647,  "lon": 19.9450},
    {"nazwa": "Ojmiakon",                   "region": "Rosja",               "lat": 63.4608,  "lon": 142.7858},
    {"nazwa": "Old_Crow",                   "region": "Kanada",              "lat": 67.5667,  "lon": -139.8333},
    {"nazwa": "Oslo",                       "region": "Norwegia",            "lat": 59.9139,  "lon": 10.7522},
    {"nazwa": "Puszcza_Bialowieska",        "region": "Polska",              "lat": 52.7000,  "lon": 23.8500},
    {"nazwa": "Suwalki",                    "region": "Polska",              "lat": 54.1004,  "lon": 22.9296},
    # --- 34 nowe lokalizacje (2026-09-03) ---
    {"nazwa": "Ushuaia",                    "region": "Argentyna",           "lat": -54.8019, "lon": -68.3030},
    {"nazwa": "San_Carlos_de_Bariloche",    "region": "Argentyna",           "lat": -41.1335, "lon": -71.3103},
    {"nazwa": "Punta_Arenas",               "region": "Chile",               "lat": -53.1638, "lon": -70.9171},
    {"nazwa": "Coyhaique",                  "region": "Chile",               "lat": -45.5752, "lon": -72.0662},
    {"nazwa": "Harbin",                     "region": "Chiny",               "lat": 45.8038,  "lon": 126.5349},
    {"nazwa": "Mohe",                       "region": "Chiny",               "lat": 53.4715,  "lon": 122.3378},
    {"nazwa": "Urumczi",                    "region": "Chiny",               "lat": 43.8256,  "lon": 87.6168},
    {"nazwa": "Lhasa",                      "region": "Chiny (Tybet)",       "lat": 29.6500,  "lon": 91.1000},
    {"nazwa": "Norylsk",                    "region": "Rosja",               "lat": 69.3535,  "lon": 88.2027},
    {"nazwa": "Wladywostok",                "region": "Rosja",               "lat": 43.1332,  "lon": 131.9113},
    {"nazwa": "Murmansk",                   "region": "Rosja",               "lat": 68.9585,  "lon": 33.0827},
    {"nazwa": "Rovaniemi",                  "region": "Finlandia",           "lat": 66.5039,  "lon": 25.7294},
    {"nazwa": "Sodankyla",                  "region": "Finlandia",           "lat": 67.4166,  "lon": 26.5901},
    {"nazwa": "Kiruna",                     "region": "Szwecja",             "lat": 67.8558,  "lon": 20.2253},
    {"nazwa": "Ostersund",                  "region": "Szwecja",             "lat": 63.1792,  "lon": 14.6357},
    {"nazwa": "Tromso",                     "region": "Norwegia",            "lat": 69.6492,  "lon": 18.9553},
    {"nazwa": "Roros",                      "region": "Norwegia",            "lat": 62.5750,  "lon": 11.3844},
    {"nazwa": "Reykjavik",                  "region": "Islandia",            "lat": 64.1466,  "lon": -21.9426},
    {"nazwa": "Akureyri",                   "region": "Islandia",            "lat": 65.6885,  "lon": -18.1262},
    {"nazwa": "Banff",                      "region": "Kanada",              "lat": 51.1784,  "lon": -115.5708},
    {"nazwa": "Yellowknife",                "region": "Kanada",              "lat": 62.4540,  "lon": -114.3718},
    {"nazwa": "Quebec_City",                "region": "Kanada",              "lat": 46.8139,  "lon": -71.2080},
    {"nazwa": "Anchorage",                  "region": "USA (Alaska)",        "lat": 61.2181,  "lon": -149.9003},
    {"nazwa": "Duluth",                     "region": "USA (Minnesota)",     "lat": 46.7867,  "lon": -92.1005},
    {"nazwa": "Garmisch_Partenkirchen",     "region": "Niemcy",              "lat": 47.4917,  "lon": 11.0956},
    {"nazwa": "Oberstdorf",                 "region": "Niemcy",              "lat": 47.4021,  "lon": 10.2793},
    {"nazwa": "Aviemore",                   "region": "Wielka Brytania",     "lat": 57.1930,  "lon": -3.8270},
    {"nazwa": "Braemar",                    "region": "Wielka Brytania",     "lat": 57.0064,  "lon": -3.3970},
    {"nazwa": "Sapporo",                    "region": "Japonia",             "lat": 43.0618,  "lon": 141.3545},
    {"nazwa": "Nagano",                     "region": "Japonia",             "lat": 36.6513,  "lon": 138.1810},
    {"nazwa": "Manali",                     "region": "Indie",               "lat": 32.2432,  "lon": 77.1892},
    {"nazwa": "Gulmarg",                    "region": "Indie",               "lat": 34.0484,  "lon": 74.3805},
    {"nazwa": "Sutherland",                 "region": "RPA",                 "lat": -32.3833, "lon": 20.6667},
    {"nazwa": "Mount_Hotham",               "region": "Australia",           "lat": -36.9833, "lon": 147.1333},
]

# ---------------------------------------------------------------------------
# 2. SEZON ZIMOWY - TYLKO 2025/2026 (listopad 2025 - marzec 2026), na wyraźne
#    życzenie użytkownika ("chcę mieć wszystkie dane z 2025 roku dla każdej z
#    podanej lokalizacji") - w konwencji tego projektu sezon zimowy zaczyna się
#    w listopadzie roku Y, więc "rok 2025" = sezon (2025, 2026). Wcześniejsze
#    sezony (2021-2024) dla pierwotnych 8 stacji świadomie USUNIĘTE z aktywnego
#    zestawu danych (patrz komentarz w AGENTS.md) - wciąż odzyskiwalne z historii
#    gita, gdyby były jeszcze kiedyś potrzebne.
# ---------------------------------------------------------------------------
SEZONY = [
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


def wyznacz_okno_zimowe(stacja, rok_start, rok_koniec):
    """
    Zwraca (start_date, end_date) okna zimowego DLA WŁAŚCIWEJ półkuli.

    Półkula PÓŁNOCNA (lat >= 0): listopad(rok_start) - marzec(rok_koniec) - jak
    dotychczas w tym projekcie.
    Półkula POŁUDNIOWA (lat < 0): maj(rok_start) - wrzesień(rok_start) - zima na
    półkuli południowej wypada w PRZECIWNYM półroczu (czerwiec-sierpień to tam
    LATO na północy = ZIMA na południu), więc okno jest przesunięte o 6 miesięcy
    i NIE przekracza granicy roku kalendarzowego (w odróżnieniu od okna
    północnego, które celowo obejmuje przełom roku - listopad-marzec).

    Bez tego rozróżnienia (błąd wykryty i naprawiony 2026-09-03 przy pierwszym
    pobraniu 6 lokalizacji południowych - Ushuaia/Bariloche/Punta Arenas/
    Coyhaique/Sutherland/Mount Hotham) skrypt pobrałby dla tych lokalizacji
    dane z ICH LATA (listopad-marzec), a nie zimy - bezwartościowe dla analizy
    ogrzewania rozjazdów kolejowych w warunkach zimowych.
    """
    if stacja["lat"] >= 0:
        return f"{rok_start}-11-01", f"{rok_koniec}-03-31"
    return f"{rok_start}-05-01", f"{rok_start}-09-30"


def pobierz_dane(stacja, start_date, end_date):
    """Pobiera dane godzinowe dla jednej stacji i jednego okna dat (patrz wyznacz_okno_zimowe)."""
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
            start_date, end_date = wyznacz_okno_zimowe(stacja, rok_start, rok_koniec)
            polkula = 'płn.' if stacja["lat"] >= 0 else 'płd.'
            print(f"Pobieram: {stacja['nazwa']} ({stacja['region']}, półkula {polkula}) "
                  f"okno {start_date} -> {end_date}...")
            try:
                dane = pobierz_dane(stacja, start_date, end_date)
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