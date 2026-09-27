# fuzzy_logic_2v2

- **Plik / klasa / metoda:** `Algorytmy/fuzzy_logic_2v2.py` / `KontrolerFuzzy2v2` / `compute_control`
- **Typ:** Fuzzy logic (FL2v2, binarny, 7 reguł) · **Cel:** Stały cel (3°C) · **Adaptacyjny:** nie ·
  **Bezpiecznik:** tak

## Jak działa

Wariant `fuzzy_logic_2` z **własnym silnikiem** `silniki_fuzzy.wnioskowanie_fl2v2` — dwie różnice wobec
podstawowego wnioskowania (`wnioskowanie_fl_podstawowe`):

1. **Dodatkowa (7.) reguła**: `śnieg AKTYWNY ∧ chłodno → HIGH` — osobno wyłapuje kombinację "pada śnieg
   i jest chłodno", niezależnie od reguł 3/5 (opad ogólnie).
2. **Próg "lodowato" — TYLKO w wariantach z rodziny funkcji ryzyka (`fuzzy_ryzyko_2v2`/`_opad`) — ZALEŻY
   od poziomu RYZYKA** wyznaczonego przez TĘ SAMĄ funkcję ryzyka, która ustaliła cel grzania
   (`funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy._poziom_ryzyka_funkcji`, skala 0-4 wg priorytetów 1-4
   z `_evaluate_risk_setpoint` — 1=suchy mróz, 2=ochrona floor/prognoza mrozu, 3=śnieg/zalegająca
   pokrywa, 4=marznący deszcz). `silniki_fuzzy.wnioskowanie_fl2v2` przyjmuje ten poziom jako opcjonalny
   parametr `poziom_ryzyka`: `prog_lodowato_gorny = -15.0 + poziom_ryzyka + (3.0 jeśli poziom_ryzyka≥4)`
   — przy poziomie 3 (śnieg) wraca DOKŁADNIE do domyślnego -12.0, przy poziomie 4 (marznący deszcz,
   najwyższe zagrożenie) skacze dalej do -8.0.

   **W tym pliku (`fuzzy_logic_2v2` samodzielny, cel STAŁY 3°C) i w `fuzzy_normy_2v2` (cel z normy
   LET-1)** — obie klasy NIE dziedziczą po funkcji ryzyka i nie mają skąd wziąć tego poziomu, więc
   wołają silnik BEZ parametru `poziom_ryzyka` → próg wraca do STAŁYCH -15.0/-12.0°C, identycznie jak w
   wariancie podstawowym FL1.

   **POPRAWKA 2026-09-15 (dwa etapy)**: pierwsza wersja tego wariantu błędnie podstawiała pod próg
   surowy odczyt opadu (`precip`, mm) pod nazwą `R`, sugerującą "ryzyko" — wykryte po przeglądzie
   komentarza w kodzie. Pierwsza poprawka użyła 0-10 licznika ryzyka z `histereza_let1.py`
   (`calculate_risk_level`), ale to inny, niezwiązany algorytm (LET-1, nie funkcja ryzyka) — na
   wyraźne życzenie użytkownika ostatecznie R pochodzi z priorytetu WŁASNEJ funkcji ryzyka tego
   kontrolera (patrz wyżej), dostępnego tylko dla `fuzzy_ryzyko_2v2`/`_opad`.

Wyjście binarne (`silniki_fuzzy.binaryzuj`, próg 50%), tak jak FL2.

## Diagnostyka (IAE/ISE/ITAE)

Jak `fuzzy_logic_1` — `target_temperature = T_ZADANA`, `need_heat=True` zawsze.

## FLOPs

Szacunek: **48/krok** (4 funkcje przynależności + 7 reguł — o jedną regułę i jedno mnożenie progu
więcej niż FL1/FL2). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Samodzielny plik, własny silnik `wnioskowanie_fl2v2` (współdzielony TYLKO z `fuzzy_ryzyko_2v2*` i
`fuzzy_normy_2v2`, nie z podstawowym FL1/FL2/FL3). Cel z funkcji ryzyka:
[fuzzy_ryzyko_2v2.md](fuzzy_ryzyko_2v2.md). Cel z normy: [fuzzy_normy_2v2.md](fuzzy_normy_2v2.md).
