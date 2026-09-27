# risk_function_opad

- **Plik / klasa / metoda:** `Algorytmy/funkcja_ryzyka_binarna_opad.py` / `KontrolerRyzykaBinarnyOpad` /
  `risk_function_opad`
- **Typ:** Histereza · **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu · **Adaptacyjny:** nie ·
  **Bezpiecznik:** tak

## Jak działa

Jak [risk_function.md](risk_function.md) (histereza binarna 0/100%, kaskada 4 priorytetów), ale
setpoint liczony przez `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy._evaluate_risk_setpoint_z_opadem`
— dokłada **DRUGĄ, niezależną furtkę ucieczki z grzania** w priorytecie 2 (śnieg): jeśli pokrywa jest
cienka (≤10mm) i moduł `przewidywanie_opadow.py` (ten sam testowany osobno na 43 plikach pogodowych —
patrz `test_skutecznosc_prognozy_opadow.py` w katalogu głównym, ~80% skuteczności osłony globalnie) nie
widzi już żadnej intensywności opadu w najbliższych 2 krokach prognozy (~30 min), NIE grzejemy na zapas.

To jest przesłanka NIEZALEŻNA od `warmup_soon` (prognoza CRT z Kalmana) — łapie sytuacje, gdy front
opadowy mija, ale sama szyna jeszcze nie zdążyła się ocieplić (dwa różne sygnały: "front kończy się"
vs "szyna sama się nagrzeje", sprawdzane osobno).

## FLOPs

Szacunek: **155/krok** (kaskada 20 + histereza 15 + rzadkie wywołania prognozy opadu ~160/wywołanie,
tylko gdy furtka śniegu jest w ogóle sprawdzana). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy` (← `KontrolerRyzykaBazowy`). Wariant
bez opadu: [risk_function.md](risk_function.md). Wariant z regulatorem ciągłym:
[risk_function_pid_opad.md](risk_function_pid_opad.md).
