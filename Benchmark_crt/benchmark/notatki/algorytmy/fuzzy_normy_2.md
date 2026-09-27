# fuzzy_normy_2

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_normy_2.py` / `KontrolerFuzzyNormy2` / `fuzzy_normy`
- **Typ:** Fuzzy logic (FL2, binarny) · **Cel:** Progi normy LET-1 · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_normy_1.md](fuzzy_normy_1.md) (cel z progów normy LET-1), ale wykonawczo silnik + `binaryzuj`
(twarde 0/100% przy progu 50%) zamiast miękkiego obcięcia krańców — patrz
[fuzzy_logic_2.md](fuzzy_logic_2.md) po opis różnicy silnika.

## FLOPs

Szacunek: **40/krok** (progi normy 10 + silnik 40). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy` + silnik współdzielony z
`fuzzy_logic_2.py`. Ten sam silnik, cel z funkcji ryzyka: [fuzzy_ryzyko_2.md](fuzzy_ryzyko_2.md).
