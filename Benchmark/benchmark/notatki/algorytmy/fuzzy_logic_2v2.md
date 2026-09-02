# fuzzy_logic_2v2

- **Plik / klasa / metoda:** `Algorytmy/fuzzy_logic_2v2.py` / `KontrolerFuzzy2v2` / `compute_control`
- **Typ:** Fuzzy logic (FL2v2, binarny, 7 reguł) · **Cel:** Stały cel (3°C) · **Adaptacyjny:** nie ·
  **Bezpiecznik:** tak

## Jak działa

Wariant `fuzzy_logic_2` z **własnym silnikiem** `silniki_fuzzy.wnioskowanie_fl2v2` — dwie różnice wobec
podstawowego wnioskowania (`wnioskowanie_fl_podstawowe`):

1. **Dodatkowa (7.) reguła**: `śnieg AKTYWNY ∧ chłodno → HIGH` — osobno wyłapuje kombinację "pada śnieg
   i jest chłodno", niezależnie od reguł 3/5 (opad ogólnie).
2. **Próg "lodowato" ZALEŻNY od intensywności opadu** (`R = precip`), zamiast stałego -15..-12°C:
   `prog_lodowato = -15.0 + R*10.0 + (5.0 jeśli R>8)` — przy silniejszym opadzie próg przesuwa się
   wyżej (łatwiej "złapać" stan lodowaty), co ma sens fizycznie (więcej wilgoci = szybsze zamarzanie).

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
