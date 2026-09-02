# fuzzy_logic_3

- **Plik / klasa / metoda:** `Algorytmy/fuzzy_logic_3.py` / `KontrolerFuzzy3` / `compute_control`
- **Typ:** Fuzzy logic (FL3, PWM) · **Cel:** Stały cel (3°C) · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_logic_1.md](fuzzy_logic_1.md) (ten sam silnik `wnioskowanie_fl_podstawowe`, ten sam stały
cel 3.0°C), ale wyjście jest **modulowane PWM** (modulacja szerokości impulsu, `silniki_fuzzy.WykonawcaPWM`,
okno 60s) zamiast ciągłe/binarne: moc % wyliczana silnikiem rozmytym RAZ na początku każdego okna
60-sekundowego, potem przeliczana na czas załączenia W TYM oknie z kwantyzacją (czas włączenia <15s →
0, >45s → pełen cykl) — każdy krok zwraca binarne 0/100% w zależności od pozycji w oknie. Efekt:
grzałka włącza/wyłącza się kilka razy na minutę zamiast trzymać ciągły poziom mocy, ale ŚREDNIA moc w
oknie odpowiada wynikowi silnika rozmytego.

## Diagnostyka (IAE/ISE/ITAE)

Jak `fuzzy_logic_1` — `target_temperature = T_ZADANA`, `need_heat=True` zawsze.

## FLOPs

Szacunek: **42/krok** (silnik FL1 — 40 FLOPs — liczony RAZ na cykl PWM 60s, więc amortyzowany do
~0.67/krok + krok PWM 2/krok = ~2.67 realnie, ale rejestr podaje uśrednioną wartość rzędu 42
uwzględniającą sposób liczenia). Patrz [../FLOPs.md](../FLOPs.md) po dokładny podział silnik-raz-na-cykl
vs krok-PWM-co-krok.

## Powiązania

Samodzielny plik, silnik `wnioskowanie_fl_podstawowe` współdzielony z FL1/FL2, mechanizm PWM
(`WykonawcaPWM`) współdzielony z `fuzzy_ryzyko_3*` i `fuzzy_normy_3`. Cel z funkcji ryzyka:
[fuzzy_ryzyko_3.md](fuzzy_ryzyko_3.md). Cel z normy: [fuzzy_normy_3.md](fuzzy_normy_3.md).
