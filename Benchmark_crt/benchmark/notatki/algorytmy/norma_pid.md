# norma_pid

- **Plik / klasa / metoda:** `Algorytmy/funkcja_pid_normy.py` / `KontrolerNormaPID` / `norma_pid`
- **Typ:** PID (PI, SIMC offline) · **Cel:** Progi normy LET-1 · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Regulator PI(D) ciągły (0-100%) dążący do **progu ZAŁĄCZENIA z normy LET-1** (nie funkcji ryzyka) —
setpoint z `funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy._evaluate_norm_setpoint`, bez pamięci ani
prognozy: `target = 4.0°C` przy opadach (AT ≤ 4°C i wykryty opad/śnieg), `target = 1.0°C` przy suchym
mrozie (AT ≤ -5°C), inaczej brak potrzeby grzania.

Dlaczego próg załączenia, a nie np. średnia zał/wył? Bo reprezentuje "jak ciepła ma być szyna, żeby
norma uznała warunki za bezpieczne" — `compute_control` grzeje AŻ szyna go osiągnie (histereza), tu
regulator ciągły po prostu utrzymuje się w jego okolicy zamiast przelatywać przez całe pasmo histerezy.

Nastawy PI **identyczne jak w `risk_function_pid`** (Kc=2.9262 %/°C, Ti=3571.88 s) — bo to własność
OBIEKTU/grzałki (wyliczona offline metodą SIMC z parametrów zidentyfikowanych we wcześniejszym teście
autotestu), nie strategii wyznaczania celu. Różnica z `risk_function_pid`: BRAK autotestu na żywo —
nastawy są ustalone raz, offline, nigdy się nie przeliczają w trakcie przebiegu (stąd `adaptacyjny:
False`).

## FLOPs

Szacunek: **18/krok** (progi normy 10 + PI(D) 15 — najniższy koszt spośród wszystkich regulatorów
ciągłych, bo brak pamięci/prognozy Kalmana). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy` ← `rdzen_kontrolera.KontrolerBazowy`
(pamięć dziedziczona, ale niewykorzystywana w logice). Setpoint współdzielony z całą rodziną
`fuzzy_normy_*`. Ten sam regulator PI, ale cel z funkcji ryzyka zamiast normy:
[risk_function_pid.md](risk_function_pid.md).
