# fuzzy_logic_2

- **Plik / klasa / metoda:** `Algorytmy/fuzzy_logic_2.py` / `KontrolerFuzzy2` / `compute_control`
- **Typ:** Fuzzy logic (FL2, binarny) · **Cel:** Stały cel (3°C) · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Dokładnie jak [fuzzy_logic_1.md](fuzzy_logic_1.md) (ten sam silnik `wnioskowanie_fl_podstawowe`, ten
sam stały cel 3.0°C, te same 6 reguł Sugeno) — jedyna różnica: wyjście jest **twardo zbinaryzowane**
(`silniki_fuzzy.binaryzuj`: próg 50% → wynik ≥50% daje 100%, inaczej 0%) zamiast ciągłe z miękkim
obcięciem krańców. To sprawia, że FL2 zachowuje się jak przełącznik sterowany rozmytą oceną sytuacji,
nie jak regulator proporcjonalny.

## Diagnostyka (IAE/ISE/ITAE)

Jak `fuzzy_logic_1` — `target_temperature = T_ZADANA`, `need_heat=True` zawsze.

## FLOPs

Szacunek: **40/krok** (identyczny silnik co FL1 — binaryzacja to jeden dodatkowy, pomijalny koszt
porównania). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Samodzielny plik, silnik współdzielony z `fuzzy_logic_1.py`. Ten sam silnik binarny, cel z funkcji
ryzyka: [fuzzy_ryzyko_2.md](fuzzy_ryzyko_2.md). Cel z normy: [fuzzy_normy_2.md](fuzzy_normy_2.md).
