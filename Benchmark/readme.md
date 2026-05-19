# 🛤️ Rail Heating System Simulator

Symulator i sterownik układu **grzania szyn kolejowych / rozjazdów kolejowych** oparty na modelach transmitancyjnych (układ ciągły → dyskretny). Projekt pozwala symulować wpływ warunków atmosferycznych na temperaturę szyny oraz oceniać skuteczność dowolnego algorytmu sterowania grzałką.

---

## 📂 Struktura projektu

```
├── generator_pogody.py        # Pobieranie danych pogodowych z API Open-Meteo
├── main_test.py               # Główny symulator – pętla sekundowa, zapis wyników
├── controller.py              # Algorytm sterowania (tutaj wdrażasz swój pomysł!)
├── analizator_wynikow.py      # Interaktywna wizualizacja wyników (dark mode)
└── wroclaw_pogoda_15min_model.csv  # Dane pogodowe (generowane przez generator_pogody.py)
```

---

## ⚙️ Wymagania

```bash
pip install pandas numpy scipy matplotlib requests
```

> Wymagany backend `TkAgg` dla `matplotlib` (okno interaktywne). Na Windows działa out-of-the-box. Na Linux może być potrzebny pakiet `python3-tk`.

---

## 🚀 Jak uruchomić (krok po kroku)

### Krok 1 – Pobierz dane pogodowe

```bash
python generator_pogody.py
```

Skrypt łączy się z **Open-Meteo Historical Forecast API** i pobiera dane 15-minutowe dla Wrocławia w zakresie `2024-11-01` → `2025-03-31`. Wynik to plik CSV:

```
wroclaw_pogoda_15min_model.csv
```

Przy okazji wyświetla wykres kontrolny temperatury i opadów dla tygodnia w grudniu 2024.

> Chcesz inne miasto lub inny okres? Zmień w `generator_pogody.py`:
> ```python
> "latitude": 51.1079,   # Twoja szerokość
> "longitude": 17.0385,  # Twoja długość
> "start_date": "2024-11-01",
> "end_date": "2025-03-31"
> ```

---

### Krok 2 – Uruchom symulator

Ustaw w `main_test.py` ścieżkę do pliku CSV:

```python
NAZWA_PLIKU_CSV = "wroclaw_pogoda_15min_model.csv"  # lub pełna ścieżka
```

Następnie uruchom:

```bash
python main_test.py
```

Symulator:
1. Wczytuje dane 15-minutowe i interpoluje je do rozdzielczości **1 sekundy**
2. Uruchamia pętlę sekundową dla całego okresu zimowego
3. Wywołuje Twój algorytm (`controller.py`) co sekundę
4. Oblicza temperatury szyn przez modele transmitancyjne
5. Aktualizuje model fizyczny akumulacji śniegu i lodu
6. Zapisuje wyniki do pliku `wyniki_symulacji_1s.csv`

---

### Krok 3 – Analizuj wyniki

Ustaw ścieżkę w `analizator_wynikow.py`:

```python
NAZWA_PLIKU_WEJSCIOWEGO = "wyniki_symulacji_1s.csv"
```

Uruchom:

```bash
python analizator_wynikow.py
```

W konsoli pojawi się **raport statystyczny**:
- Całkowity czas symulacji
- Czas aktywnego grzania i % czasu pracy grzałki
- Szacunkowe zużycie energii [kWh]

Otworzy się interaktywne okno wykresu z suwakiem czasowym i scrollem myszy.

---

## 🧠 Model obiektu – jak działa fizyka szyny

System używa dwóch modeli transmitancyjnych opisujących termodynamikę szyny.

### Model wpływu pogody na szynę (G_W)

Opisuje jak temperatura otoczenia przenosi się na temperaturę szyny bez grzania:

```
          K_W * (TZ_W * s + 1)
G_W(s) = ─────────────────────
              T1_W * s + 1
```

| Parametr | Wartość | Znaczenie |
|---|---|---|
| `K_W` | 1.09 | Wzmocnienie statyczne |
| `T1_W` | 5772 s | Stała czasowa cieplna szyny (~96 min) |
| `TZ_W` | 780 s | Stała czasowa zerowania (~13 min) |

### Model grzałki elektrycznej (G_H)

Opisuje jak moc grzałki [0–100%] przekłada się na przyrost temperatury szyny:

```
              K_H
G_H(s) = ───────────────────── * e^(-L_H * s)
          (T1_H*s+1)(T2_H*s+1)
```

| Parametr | Wartość | Znaczenie |
|---|---|---|
| `K_H` | 51.12 | Wzmocnienie (°C na pełne wysterowanie) |
| `T1_H` | 1121 s | Pierwsza stała czasowa (~18.7 min) |
| `T2_H` | 2451 s | Druga stała czasowa (~40.8 min) |
| `L_H` | 1194 s | Opóźnienie transportowe (~20 min) |

Temperatura szyny ogrzewanej (HRT) w każdej chwili to suma:

```
HRT = G_W(temperatura_otoczenia) + G_H(sterowanie_grzałką)
```

Temperatura szyny niegrzewanej (CRT) to samo:

```
CRT = G_W(temperatura_otoczenia)
```

Modele są dyskretyzowane metodą Tustina (Bilinear) do kroku `dt = 1 s` i realizowane przez **równania różnicowe** – bez ponownej dyskretyzacji w każdej iteracji, co zapewnia wysoką wydajność.

---

## 🌨️ Model akumulacji śniegu i lodu

Klasa `SnowIcePhysicalModel` w `main_test.py` śledzi grubość warstwy śniegu i lodu na szynie w milimetrach.

### Akumulacja

| Warunek | Efekt |
|---|---|
| `AT ≤ 0°C` i opad | Opad trafia do warstwy śniegu |
| `AT > 0°C` i opad i `HRT ≤ 0°C` | Opad trafia do warstwy lodu (deszcz zamarzający) |

### Topnienie przez grzałkę

Co sekundę, jeśli temperatura szyny ogrzewanej `HRT > 0°C`:

```
melt_potential = HRT * melt_rate * dt    # melt_rate = 0.0001 [mm/(°C·s)]
```

Topnienie odbywa się w kolejności: najpierw śnieg, potem lód. Warstwa nigdy nie spada poniżej zera.

---

## 🎛️ Jak pisać własny algorytm sterowania

Plik `controller.py` to jedyne miejsce, które musisz modyfikować, żeby testować swoje pomysły.

### Wejście – co dostaje algorytm

Metoda `compute_control(row_data)` otrzymuje słownik z następującymi polami:

| Klucz | Typ | Jednostka | Opis |
|---|---|---|---|
| `Timestamp` | `datetime` | — | Aktualny czas symulacji |
| `CRT_temp_niegrzana` | `float` | °C | Temperatura szyny **niegrzewanej** (wpływ pogody) |
| `HRT_temp_grzana` | `float` | °C | Temperatura szyny **ogrzewanej** (pogoda + grzałka) |
| `AT_temp_powietrza` | `float` | °C | Temperatura powietrza |
| `RH_wilgotnosc` | `float` | % | Wilgotność względna (obliczona z punktu rosy) |
| `PRESS_cisnienie` | `float` | hPa | Ciśnienie atmosferyczne |
| `PRECIP_opad` | `float` | mm/s | Intensywność opadu deszczu |
| `SNOW_snieg` | `float` | mm/s | Intensywność opadu śniegu |
| `PWRL1_moc` | `float` | kW | Moc na linii zasilającej 1 (zarezerwowane) |
| `PWRL2_moc` | `float` | kW | Moc na linii zasilającej 2 (zarezerwowane) |

### Wyjście – co zwraca algorytm

Metoda musi zwrócić **jedną liczbę zmiennoprzecinkową**:

```
sterowanie [float]  →  zakres: 0.0 (wyłączone) do 100.0 (pełna moc)
```

W aktualnej implementacji sterowanie jest dwustanowe (0 lub 100), ale interfejs jest gotowy na sterowanie proporcjonalne.

### Przykład – aktualny algorytm z histerezą i limitem przełączeń

```python
class RailHeatingController:
    def __init__(self, target_temp=4.0, hysteresis=1.0):
        self.target_temp = target_temp      # Temperatura docelowa szyny [°C]
        self.hysteresis = hysteresis        # Szerokość histerezy [°C]
        self.heating_on = False
        self.max_switches_per_day = 5       # Limit przełączeń dziennie

    def compute_control(self, row_data):
        hrt = float(row_data['HRT_temp_grzana'])
        at  = float(row_data['AT_temp_powietrza'])
        rh  = float(row_data['RH_wilgotnosc'])
        precip = float(row_data['PRECIP_opad'])
        snow   = float(row_data['SNOW_snieg'])

        ice_risk = (at <= 2.0) and (precip > 0 or snow > 0 or rh > 80.0)

        if self.heating_on:
            if hrt >= (self.target_temp + self.hysteresis):
                self.heating_on = False     # Wyłącz po osiągnięciu górnego progu
        else:
            if hrt <= (self.target_temp - self.hysteresis) or ice_risk:
                self.heating_on = True      # Włącz przy dolnym progu lub ryzyku lodu

        return 100.0 if self.heating_on else 0.0
```

### Jak podpiąć swój kontroler do symulatora

W pliku `main_test.py` zastąp import kontrolera:

```python
# Było:
# class RailHeatingController: ...  (wbudowana klasa testowa)

# Zamień na:
from controller import RailHeatingController
```

I utwórz instancję z własnymi parametrami:

```python
controller = RailHeatingController(target_temp=4.0, hysteresis=1.0)
```

---

## 📊 Format pliku wynikowego

`wyniki_symulacji_1s.csv` zawiera jedną próbkę na sekundę:

| Kolumna | Jednostka | Opis |
|---|---|---|
| `Timestamp` | datetime | Czas symulacji |
| `AT_temp_powietrza` | °C | Temperatura powietrza |
| `HRT_temp_grzana` | °C | Temperatura szyny ogrzewanej |
| `CRT_temp_niegrzana` | °C | Temperatura szyny niegrzewanej |
| `PRECIP_opad_1s` | mm/s | Opad (rozdzielony na sekundy) |
| `SNOW_snieg_1s` | mm/s | Śnieg (rozdzielony na sekundy) |
| `Moc_procent` | % | Wysterowanie grzałki (0 lub 100) |
| `Snieg_na_szynie_mm` | mm | Aktualna grubość warstwy śniegu |
| `Lod_na_szynie_mm` | mm | Aktualna grubość warstwy lodu |

---

## 📈 Analiza wyników – co pokazuje wykres

Interaktywne okno `analizator_wynikow.py` składa się z dwóch paneli:

**Panel górny – temperatury i moc:**
- 🔴 `HRT` – szyna ogrzewana
- ⚪ `CRT` – szyna niegrzewana (referencja)
- 🔵 `AT` – temperatura powietrza
- 🟡 Żółte wypełnienie – okresy aktywnego grzania [%]

**Panel dolny – opady i akumulacja:**
- 🔵 Intensywność opadów (przeliczona z powrotem na mm/15min)
- 🟢 Grubość warstwy śniegu na szynie
- 🟣 Grubość warstwy lodu na szynie

**Nawigacja:**
- Suwak na dole – przewija cały okres symulacji
- Przyciski `◀` `▶` – skok o 30 minut
- Rolka myszy nad wykresem – płynne przewijanie

---

## 🏗️ Architektura przepływu danych

```
generator_pogody.py
        │
        │  wroclaw_pogoda_15min_model.csv
        ▼
main_test.py
 ├── Interpolacja 15min → 1s
 ├── Pętla sekundowa:
 │    ├── G_W(AT) ──────────────────────────────► CRT
 │    ├── controller.compute_control(dane) ─► u%
 │    ├── G_H(u%, opóźnienie L_H) ──────────────┐
 │    │                                          ├──► HRT = CRT + G_H
 │    └── SnowIcePhysicalModel.update() ────────► śnieg/lód [mm]
 │
 └── wyniki_symulacji_1s.csv
        │
        ▼
analizator_wynikow.py
  └── Raport statystyczny + Wykres interaktywny
```

---

## 📝 Licencja

Projekt edukacyjno-badawczy. Dane pogodowe pochodzą z [Open-Meteo](https://open-meteo.com/) (licencja CC BY 4.0).
