# mpc_prognoza_pogody

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_prognoza.py` / `KontrolerMPCPrognoza` / `mpc_prognoza`
- **Typ:** MPC (QP, model SOPDT blokowy) · **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu -
  optymalizacja trajektorii Z prognozą pogody · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Jak [mpc_liniowy.md](mpc_liniowy.md) (ta sama maszyneria QP/model blokowy/move-blocking - patrz
`Algorytmy/mpc_wspolne.py`), ale "PEŁNA" wersja wykorzystująca WSZYSTKIE dostępne prognozy:

- Zaburzenie (CRT) użyte przez MPC do przewidywania WŁASNEJ trajektorii na horyzoncie bierze z
  **prognozy Kalmana** (`rail_temperature_prediction()`, 2h/8×15min) zamiast zakładać wartość stałą.
- Cel/próg bezpieczeństwa liczony wariantem funkcji ryzyka **Z prognozą opadu**
  (`KontrolerRyzykaOpadBazowy._evaluate_risk_setpoint_z_opadem`, `przewidywanie_opadow.py`) - nie
  grzeje na zapas, gdy front opadowy kończy się a pokrywa jest cienka (jak `risk_function_pid_opad`).

**Kluczowe porównanie z [mpc_liniowy.md](mpc_liniowy.md)**: różnica energetyczna między tymi dwoma
pokazuje CZYSTĄ wartość dodaną prognozy pogody przy PEŁNEJ optymalizacji trajektorii - w odróżnieniu
od par `*_opad` reszty algorytmów (gdzie różnica dotyczy tylko furtki ucieczki z grzania), tu dotyczy
CAŁEGO mechanizmu przewidywania trajektorii wewnątrz MPC, więc różnica powinna być bardziej widoczna
(MPC z natury wykorzystuje wiedzę o przyszłości do optymalizacji, nie tylko do jednorazowej decyzji).

Reszta mechaniki (move blocking co 900s, bezpieczeństwo - natychmiastowe zerowanie mocy przy
`need_heat=False`, fallback P przy braku modelu, fallback "ostatnia moc" przy niepowodzeniu solvera)
identyczna jak `mpc_liniowy` - patrz [mpc_liniowy.md](mpc_liniowy.md) i `Algorytmy/mpc_wspolne.py`.

## FLOPs

**ZMIERZONE** (nie szacunek analityczny): ~805/krok, patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `_MPCMachineryMixin` (`Algorytmy/mpc_wspolne.py`) + `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy`
(setpoint + prognoza opadu). Wariant kontrolny bez prognozy pogody: [mpc_liniowy.md](mpc_liniowy.md).
Analogiczne wykorzystanie prognozy opadu w innej rodzinie: [risk_function_pid_opad.md](risk_function_pid_opad.md).
