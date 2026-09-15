# fuzzy_ryzyko_agresywny

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_agresywny.py` / `KontrolerFuzzyRyzykoAgresywny` /
  `fuzzy_ryzyko_agresywny`
- **Typ:** Fuzzy logic (FL1, agresywny) · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md) (cel z kaskady funkcji ryzyka, wykonawczo silnik rozmyty FL1),
ale z WYRAŹNIE OSTRZEJSZĄ reakcją na pogarszające się warunki - dodane 2026-09-15 na wyraźne życzenie
użytkownika ("bardziej karaj fuzzy logic... żeby znacznie mocniej reagował na warunki złe") jako OSOBNY
algorytm (`fuzzy_ryzyko_1` zostaje bez zmian jako punkt odniesienia "normalnej" reakcji).

**Jak dokładnie "karze" mocniej** (`silniki_fuzzy.wnioskowanie_fl_agresywne`) - CELOWO nie przez dodanie
nowych reguł ani mnożnik na wyniku po fakcie, tylko przez zmianę samych funkcji przynależności (dalej
prawidłowe wnioskowanie Sugeno, ta sama matematyka co FL1, inny kształt zbiorów rozmytych):

| Parametr | FL1 (domyślny) | Agresywny | Efekt |
|---|---|---|---|
| `prog_chlodno` | 3.0°C | 1.5°C | z "OK" do "chłodno" przy mniejszym błędzie |
| `prog_mrozno` | 6.0°C | 3.5°C | pełne "mroźno" (MOC_HIGH przy opadzie) dużo wcześniej |
| `prog_lodowato_dolny` | -15.0°C | -12.0°C | próg "lodowato" zaczyna się przy łagodniejszym mrozie |
| `prog_lodowato_gorny` | -12.0°C | -8.0°C | pełna MOC_HIGH z powodu HRT osiągana dużo wcześniej |
| `MOC_LOW` | 25% | 50% | "chłodno bez opadu" grzeje 2x mocniej |
| `MOC_MED` | 60% | 85% | "mroźno bez opadu" grzeje wyraźnie mocniej |

Implementacja: `silniki_fuzzy.wnioskowanie_fl_parametryzowane` rozszerzona o parametry `moc_low`/`moc_med`
(domyślnie = `MOC_LOW`/`MOC_MED`, zero zmiany zachowania dla FL1/FL2/FL3/`fuzzy_ryzyko_adaptacyjny`), a
`wnioskowanie_fl_agresywne` to cienka otoczka podstawiająca stałe z tabeli wyżej.

**Oczekiwany kompromis** (CEL tego wariantu, nie błąd): WYŻSZA energia, mniej epizodów poniżej progów
bezpieczeństwa niż `fuzzy_ryzyko_1` - "agresywny" = konserwatywny/bezpieczny kosztem energii. Zmierzone
(smoke test, abisko, 6 dni): `fuzzy_ryzyko_1` energia=587.5 kWh vs `fuzzy_ryzyko_agresywny`
energia=724.8 kWh (+23%).

## FLOPs

**40/krok** - identyczne jak `fuzzy_ryzyko_1` (te same 6 reguł Sugeno, tylko inne stałe). Patrz
[../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` (setpoint) + silnik `silniki_fuzzy`
(`wnioskowanie_fl_agresywne`). Łagodny punkt odniesienia: [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md).
Inny rodzaj adaptacji (progi strojone online, nie na stałe zaostrzone):
[fuzzy_ryzyko_adaptacyjny.md](fuzzy_ryzyko_adaptacyjny.md).
