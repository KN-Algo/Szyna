# Podsumowanie_awarii.xlsx

Generator: `generuj_excel_awarie.py`, wołany po `test_awarie_czujnikow.py`. W
odróżnieniu od "szumu wielu czujników" (patrz `podsumowanie_szumu.md`) - to KRÓTKI test,
1 lokalizacja (domyślnie `abisko_60min_2021`), TYLKO 2 czujniki (HRT/AT), ale 3 KONKRETNE
TYPY awarii zamiast poziomów szumu:
- **`_bias`** - stałe przesunięcie odczytu o `BIAS_C = 5.0°C` przez CAŁY przebieg.
- **`_szum`** - biały szum Gaussa, `SZUM_STD_C = 2.0°C` (jeden ustalony poziom, w
  odróżnieniu od 4 poziomów w `test_szum_wielu_czujnikow.py`).
- **`_rozlaczenie`** - od POŁOWY okna symulacji kontroler widzi ZAMROŻONĄ ostatnią wartość
  sprzed awarii (typowa "martwa" awaria czujnika) - `_zrob_rozlaczenie` w kodzie.

7 scenariuszy razem: `brak_awarii` (referencja) + `HRT_bias`/`HRT_szum`/`HRT_rozlaczenie`
+ `AT_bias`/`AT_szum`/`AT_rozlaczenie`.

## Jedyna zakładka: "Odpornosc_na_awarie"

Jeden wiersz = jeden algorytm (WSZYSTKIE z `Algorytmy/rejestr_algorytmow.ALGORYTMY`, w
naturalnej kolejności rejestru). Kolumny = 7 scenariuszy w stałej kolejności
(`SCENARIUSZE_KOLEJNOSC` w kodzie). Wartość w komórce:
- Kolumna `brak_awarii`: energia w kWh WPROST (`round(energia, 1)`, bez przeliczeń).
- KAŻDA inna kolumna: **`Δ energia (%) = (energia_tego_scenariusza -
  energia_brak_awarii) / energia_brak_awarii × 100`**, gdzie `energia_brak_awarii` jest
  liczona OSOBNO DLA TEGO SAMEGO ALGORYTMU (nie globalny baseline) - stąd interpretacja
  "o ile ten konkretny algorytm pogorszył/poprawił swój WŁASNY wynik pod wpływem tej
  konkretnej awarii", nie porównanie między algorytmami.

Skala kolorów (zielony→czerwony wg wartości) na każdej kolumnie oprócz `brak_awarii` -
ale UWAGA: skala jest liczona OSOBNO per kolumna (per typ awarii), nie globalnie po całej
tabeli, więc kolor w kolumnie `HRT_szum` NIE jest bezpośrednio porównywalny z kolorem w
`AT_bias` - porównuj liczby (%), nie same kolory, między kolumnami.

## Jak czytać - ważna uwaga o znaku

Odchylenie może być DODATNIE (algorytm zużywa WIĘCEJ energii niż normalnie - zwykle bo
"myśli", że jest zimniej/gorzej niż jest, i nadmiernie grzeje) albo UJEMNE (zużywa MNIEJ -
zwykle bo "myśli", że jest cieplej niż jest, i NIEDOgrzewa - to jest scenariusz
POTENCJALNIE NIEBEZPIECZNY mimo niższego zużycia energii, bo oznacza rzeczywistą szynę
zimniejszą niż zakładał kontroler). Duże OBA kierunki są złe, ale z RÓŻNYCH powodów - nie
sortuj/filtruj tylko po wartości bezwzględnej bez sprawdzenia znaku, jeśli interesuje Cię
bezpieczeństwo, a nie tylko koszt.

Realny wynik pełnej skali (`../../wyniki/_analiza_klastra.md`, sekcja 13):
`risk_function`/`risk_function_opad` przy `HRT_szum` niemal PODWAJAJĄ energię (+109-111%,
nadreaktywność), podczas gdy ich warianty PID (`risk_function_pid*`) w tym samym
scenariuszu są niemal całkowicie stabilne (-0.6%) - mocny argument liczbowy za wariantem
PID.
