# Podsumowanie_wrazliwosc.xlsx

Generator: `generuj_excel_wrazliwosc.py`, wołany po `test_wrazliwosc_dwie_lokalizacje.py`
(pogłębiona wrażliwość transmitancji + szumu, TYLKO na 2 skrajnych lokalizacjach -
Abisko=najwięcej opadu/śniegu, Ojmiakon=najzimniejsza). Źródło:
`WRAZLIWOSC_ZBIORCZY.csv`, jeden wiersz = (lokalizacja, algorytm, scenariusz
transmitancji, szum wł./wył.). 14 scenariuszy transmitancji (`nominal`, `K_plus10`,
`K_plus20`, `T1_plus10`, `T1_plus20`, `L_plus10`, `L_plus20`, i kombinacje typu
`K10_L10`/`K20_T1_20`/`K20_L20_T1_20` itd.) x szum on/off (2.0°C std dodany na HRT i CRT).

## Zakładka "Wyniki" - surowa tabela

Jeden wiersz na przebieg, kolumny (wszystkie to LITERALNE wartości z `stats`, nie
formuły): `lokalizacja`, `name` (algorytm), `scenariusz`, `szum` (bool),
`perturb_k_pct`/`perturb_t1_pct`/`perturb_l_pct` (o ile % zaburzono K/T1/L względem
prawdziwych `symulacja_fizyczna.K_H/T1_H/L_H`), `energia_kwh`, `przelaczenia`,
`max_snieg_mm`, `max_lod_mm`, `max_hrt`, `min_hrt`, oraz - TYLKO dla algorytmów
adaptacyjnych (mają autotest) - `autotest_fit_ok`, `autotest_K`/`T1`/`T2`/`L`
(zidentyfikowane przez `controller.autotest_result` z odpowiedzi skokowej 0%→100% na
starcie przebiegu) i `blad_identyfikacji_K_pct`/`T1_pct`/`L_pct` = `(zidentyfikowane -
prawdziwe_zaburzone) / prawdziwe_zaburzone × 100`.

## Zakładka "Odchylenie_energii"

Dodaje kolumnę `odchylenie_energii_pct` = `(energia_tego_wiersza - energia_baseline) /
energia_baseline × 100`, gdzie **baseline = energia TEGO SAMEGO algorytmu w TEJ SAMEJ
lokalizacji w scenariuszu `nominal` BEZ szumu** (czyli "jak bardzo ten konkretny
przebieg różni się od punktu odniesienia bez żadnych zaburzeń"). Skala kolorów: zielony
(0% odchylenia) → żółty (0, oś środkowa formalnie ustawiona na `mid_value=0`) → czerwony
(duże odchylenie w dowolną stronę - `ColorScaleRule` z `mid_type='num', mid_value=0`).

## Zakładka "Jakosc_autotestu"

Filtr `df[df['autotest_fit_ok'].notna()]` - tylko wiersze algorytmów adaptacyjnych.
Kolumny `autotest_fit_ok`/`autotest_r_squared`/3x `blad_identyfikacji_*_pct` wprost z CSV
(bez przeliczeń). Skala kolorów na kolumnach błędu identyfikacji: zielony w środku (0%
błędu), czerwony na obu końcach zakresu ±50% (`start_value=-50`/`end_value=50` - błąd
POWYŻEJ 50% w dowolną stronę jest już maksymalnie "czerwony", więc wizualnie płaskuje
się przy skrajnych wartościach typu 98%/99% widzianych w pełnej skali na klastrze).

**WAŻNE przy czytaniu**: `autotest_fit_ok=True` NIE oznacza dobrej identyfikacji - to
tylko flaga "solver się zbiegł", nie miara jakości dopasowania. Realny full-scale wynik
klastra (patrz `../../wyniki/_analiza_klastra.md`) pokazał, że ta flaga zostaje `True` w
100% przypadków, nawet gdy błąd identyfikacji K/T1 sięga ~98-99% pod wpływem szumu -
zawsze patrz na `blad_identyfikacji_*_pct`/`autotest_r_squared`, nie tylko na `fit_ok`.

## Zakładka "Podsumowanie"

Gotowy tekst (nie formuły), budowany per lokalizacja:
- **"Najbardziej wrażliwy... (bez szumu)"** - wiersz z MAKSYMALNĄ wartością bezwzględną
  `odchylenie_energii_pct` spośród wierszy TEJ lokalizacji BEZ szumu (`idxmax()` na
  `.abs()`) - pokazuje który (algorytm, scenariusz) najbardziej reaguje na samo
  zaburzenie modelu obiektu, bez udziału szumu pomiarowego.
- **"Średnie bezwzględne odchylenie energii"** - `.abs().mean()` po WSZYSTKICH
  scenariuszach i algorytmach tej lokalizacji, osobno dla szum=True/False - porównanie
  ogólnego poziomu wrażliwości z i bez szumu (uwaga: to NIE to samo co "różnica
  spowodowana przez sam szum" - oba warianty już zawierają wpływ zaburzenia
  transmitancji, różni je tylko dodatkowa obecność szumu).
- **"Jakość autotestu"** - `blad_identyfikacji_K_pct`/`T1_pct` uśrednione (`.abs().mean()`)
  osobno bez i z szumem, po WSZYSTKICH lokalizacjach/scenariuszach razem (nie per
  lokalizacja, w odróżnieniu od sekcji energii wyżej).
