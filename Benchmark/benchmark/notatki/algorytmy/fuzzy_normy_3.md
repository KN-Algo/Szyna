# fuzzy_normy_3

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_normy_3.py` / `KontrolerFuzzyNormy3` / `fuzzy_normy`
- **Typ:** Fuzzy logic (FL3, PWM) · **Cel:** Progi normy LET-1 · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_normy_1.md](fuzzy_normy_1.md) (cel z progów normy LET-1), ale wykonawczo PWM
(`silniki_fuzzy.WykonawcaPWM`, okno 60s) — patrz [fuzzy_logic_3.md](fuzzy_logic_3.md) po mechanikę
PWM: silnik FL1 liczony raz na okno 60s, moc % przeliczana na czas załączenia w oknie.

## FLOPs

Szacunek: **42/krok** (silnik FL1 amortyzowany do cyklu PWM + krok PWM + progi normy). Patrz
[../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy` + mechanizm PWM współdzielony z
`fuzzy_logic_3.py`. Ten sam mechanizm, cel z funkcji ryzyka: [fuzzy_ryzyko_3.md](fuzzy_ryzyko_3.md).
