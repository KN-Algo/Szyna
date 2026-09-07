# Podsumowanie_szumu.xlsx

Generator: funkcja `zbuduj_excel()` wewnątrz `test_szum_wielu_czujnikow.py`. Sprawdza
odporność WSZYSTKICH algorytmów na biały szum Gaussa na 7 czujnikach (HRT/CRT/AT/punkt
rosy/wiatr/opad/śnieg) x 4 poziomy każdy (kalibrowane OSOBNO per typ sygnału, nie jeden
wspólny odchylenie standardowe - patrz nagłówek `test_szum_wielu_czujnikow.py` po
dokładne wartości std per poziom/czujnik) + scenariusz referencyjny `brak_awarii` = 29
scenariuszy, na 10 LOSOWO wybranych lokalizacjach (seed=20260902, powtarzalny wybór - nie
wszystkie 43, świadomy kompromis czas/pokrycie).

## Zakładka "Srednie_per_scenariusz" (domyślna, pierwsza)

Jeden wiersz = (algorytm, scenariusz szumu). Kolumny:
- **"Śr. |odchylenie energii| (%)"** - `groupby(['algorytm','scenariusz_szumu'])
  ['odchylenie_energii_pct'].apply(lambda s: s.abs().mean())`, gdzie
  `odchylenie_energii_pct` per wiersz źródłowy = `(energia_tego_przebiegu -
  energia_baseline) / energia_baseline × 100`, a **baseline = energia TEGO SAMEGO
  algorytmu W TEJ SAMEJ lokalizacji w scenariuszu `brak_awarii`** (czyli uśredniamy
  WARTOŚĆ BEZWZGLĘDNĄ odchylenia po wszystkich 10 lokalizacjach dla danego algorytmu i
  poziomu szumu - duże dodatnie i duże ujemne odchylenia się NIE znoszą, tylko sumują siłę
  wpływu).
- **"Śr. IAE (°C·s)"** - zwykła średnia arytmetyczna `iae` po tych samych grupach (bez
  odnoszenia do baseline - surowa wartość, nie odchylenie).

Skala kolorów na kolumnie odchylenia energii: zielony (mało wrażliwy) → czerwony (bardzo
wrażliwy).

## Zakładka "Wyniki_surowe"

Pełna tabela źródłowa, jeden wiersz na (lokalizacja, algorytm, scenariusz szumu):
`lokalizacja`, `algorytm`, `scenariusz_szumu`, `energia_kwh`, `odchylenie_energii_pct`
(policzone jak wyżej, ale TU jako wartość ZE ZNAKIEM, nie `.abs()`), `przelaczenia`,
`max_snieg_mm`, `max_hrt`, `min_hrt`, `iae`, `ise`, `itae`.

## Jak czytać wyniki - dwie pułapki

1. **`algorytm_z_normy` (i każdy inny czysto otwartej-pętli algorytm) będzie miał
   0.00% odchylenia w KAŻDYM scenariuszu** - to NIE oznacza "odporności", tylko że
   algorytm w ogóle nie korzysta z odczytów czujników w logice decyzyjnej (steruje wg
   kalendarza/normy, nie sprzężenia zwrotnego) - patrz uwaga w
   `../../wyniki/_analiza_klastra.md` (sekcja 12).
2. **Nazwa czujnika w `scenariusz_szumu` to SUROWA nazwa kolumny z `row_data`**
   (`HRT_temp_grzana`, `CRT_temp_niegrzana`, `AT_temp_powietrza`, `PUNKT_ROSY_C`,
   `WIATR_M_S`, `PRECIP_opad`, `SNOW_snieg`), połączona z etykietą poziomu (`lekki`/
   `umiarkowany`/`silny`/`ekstremalny`) - np. `HRT_temp_grzana_silny`. Zerowe odchylenie
   na WIATR/PUNKT_ROSY dla WSZYSTKICH algorytmów (realny wynik klastra) oznacza, że żaden
   z 32 algorytmów w ogóle nie czyta tych dwóch sygnałów.
