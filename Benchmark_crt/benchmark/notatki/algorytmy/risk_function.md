# risk_function

- **Plik / klasa / metoda:** `Algorytmy/funkcja_ryzyka_binarna.py` / `KontrolerRyzykaBinarny` / `risk_function`
- **Typ:** Histereza · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Setpoint liczony przez `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy._evaluate_risk_setpoint` — patrz
[risk_function_pid.md](risk_function_pid.md) dla pełnego opisu kaskady 4 priorytetów (marznący deszcz
→ śnieg z karą za zaleganie i ucieczką przy ociepleniu → ochrona floora -10°C → suchy mróz), wspólnej
z wersją PID. Ten wariant (`risk_function`) różni się WYŁĄCZNIE tym, JAK ten setpoint zamienia się na
moc: **histereza binarna** (0%/100%), nie ciągły regulator — załącz gdy `HRT < target`, wyłącz gdy
`HRT > target + 2.0°C` (histereza), z limitem przełączeń/dobę (domyślnie 12) i minimalnym odstępem
60s między przełączeniami.

NIE jest adaptacyjny (`adaptacyjny: False` w rejestrze) mimo dziedziczenia po tej samej klasie bazowej
co `risk_function_pid` — nie wykonuje autotestu ani nie buduje cyfrowego bliźniaka (autotest dotyczy
tylko wariantów z regulatorem ciągłym, gdzie wynik identyfikacji przelicza nastawy PI; histereza nie
ma nastaw do przeliczenia).

## FLOPs

Szacunek: **145/krok** (kaskada 20 + histereza/limit 15, plus amortyzowany skok prognozy Kalmana co
300 kroków). Realnie zmierzony koszt bywa ~3.3x wyższy — patrz sekcja 3 w [../FLOPs.md](../FLOPs.md)
(historia rośnie do ~86400 próbek zanim przycinanie zadziała, nie do 43200 jak szacunek zakładał).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` (setpoint) ← `rdzen_kontrolera.KontrolerBazowy`
(pamięć + Kalman). Wariant z prognozą opadu: [risk_function_opad.md](risk_function_opad.md). Wariant
z regulatorem ciągłym: [risk_function_pid.md](risk_function_pid.md).
