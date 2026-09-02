# fuzzy_normy_1

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_normy_1.py` / `KontrolerFuzzyNormy1` / `fuzzy_normy`
- **Typ:** Fuzzy logic (FL1, ciągły) · **Cel:** Progi normy LET-1 · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md) (silnik FL1, `wnioskowanie_fl_podstawowe` + `klamra_fl1`),
ale cel z **progów normy LET-1** (`funkcja_normy_wspolne._evaluate_norm_setpoint` — patrz
[norma_pid.md](norma_pid.md)) zamiast funkcji ryzyka: `target = 4.0°C` przy opadach, `1.0°C` przy
suchym mrozie, bez pamięci/prognozy/kary za śnieg. Brak autotestu (`adaptacyjny: False`) — norma nie
korzysta z cyfrowego bliźniaka.

## FLOPs

Szacunek: **40/krok** (progi normy 10 + silnik FL1 40 — ale dziedziczona pamięć czujników z
`KontrolerBazowy` jest zapisywana, choć nieużywana w logice, stąd stała pamięciowa jak
`risk_function`, nie jak samodzielny `fuzzy_logic_1`). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy` + silnik `silniki_fuzzy` (współdzielony
z `fuzzy_logic_1.py`). Ten sam cel, wykonawczo PID: [norma_pid.md](norma_pid.md). Ten sam silnik, cel
z funkcji ryzyka: [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md).
