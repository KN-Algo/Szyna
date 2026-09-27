# fuzzy_ryzyko_3

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_3.py` / `KontrolerFuzzyRyzyko3` / `fuzzy_ryzyko`
- **Typ:** Fuzzy logic (FL3, PWM) · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md) (cel z kaskady funkcji ryzyka, autotest + bliźniak), ale
wykonawczo **PWM** (`silniki_fuzzy.WykonawcaPWM`, okno 60s — patrz [fuzzy_logic_3.md](fuzzy_logic_3.md)
po mechanikę PWM) zamiast ciągłego/binarnego wyjścia: silnik FL1 liczony raz na okno, moc %
przeliczana na czas załączenia w tym oknie.

**Uwaga praktyczna zaobserwowana w testach**: ta kombinacja (cel z funkcji ryzyka + wykonanie PWM)
wypadła SŁABO pod wpływem awarii czujnika HRT (bias) w teście odporności — patrz
`test_awarie_czujnikow.py` / `Podsumowanie_awarii.xlsx`, wariant `fuzzy_ryzyko_3_opad` znacząco
niedogrzewał przy zaburzonym odczycie HRT. Warto to mieć na uwadze przy interpretacji wyników tego
wariantu w warunkach zaszumionych czujników.

## FLOPs

Szacunek: **492/krok** (kaskada 20 + silnik FL1 amortyzowany do cyklu PWM + krok PWM). Patrz
[../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` + mechanizm PWM (współdzielony z
`fuzzy_logic_3.py`). Wariant z prognozą opadu: [fuzzy_ryzyko_3_opad.md](fuzzy_ryzyko_3_opad.md).
