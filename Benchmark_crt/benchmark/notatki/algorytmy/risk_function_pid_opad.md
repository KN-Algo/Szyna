# risk_function_pid_opad

- **Plik / klasa / metoda:** `Algorytmy/funkcja_ryzyka_pid_opad.py` / `KontrolerRyzykaPIDOpad` /
  `risk_function_pid_opad`
- **Typ:** PID (PI, SIMC) · **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Jak [risk_function_pid.md](risk_function_pid.md) (autotest startowy → SIMC → regulator PI ciągły
0-100%), ale setpoint z `_evaluate_risk_setpoint_z_opadem` — patrz
[risk_function_opad.md](risk_function_opad.md) po opis furtki opadowej (dodatkowa ucieczka z grzania
w priorytecie 2, gdy prognoza `przewidywanie_opadow.py` pokazuje koniec frontu a pokrywa jest cienka).

Łączy WSZYSTKIE trzy elementy adaptacyjności naraz: (1) autotest identyfikujący obiekt na żywo, (2)
SIMC przeliczające własne nastawy PI z wyniku identyfikacji, (3) cyfrowy bliźniak prognozujący HRT
fizycznie. Prognoza opadu jest DODATKOWA (nie wymaga autotestu) — działa niezależnie od tego, czy
identyfikacja się powiodła.

## FLOPs

Szacunek: **465/krok** (kaskada 20 + PI(D) 15 + amortyzowane skoki Kalman/bliźniak + rzadkie
wywołania prognozy opadu). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy`. Wariant bez opadu:
[risk_function_pid.md](risk_function_pid.md). Wariant binarny:
[risk_function_opad.md](risk_function_opad.md).
