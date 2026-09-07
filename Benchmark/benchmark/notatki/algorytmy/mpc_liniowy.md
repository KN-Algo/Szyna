# mpc_liniowy

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_liniowy.py` / `KontrolerMPCLiniowy` / `mpc_liniowy`
- **Typ:** MPC (QP, model SOPDT blokowy) · **Cel:** Funkcja ryzyka (Kalman) - optymalizacja trajektorii
  BEZ prognozy pogody · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Prawdziwy regulator predykcyjny (Model Predictive Control) - w ODRÓŻNIENIU od `nauka_kary_blizniak`/
`nauka_kary_ryzyko` (cyfrowy bliźniak używany TYLKO jako feedforward do korekty pojedynczego kroku),
tu cyfrowy bliźniak jest PODSTAWĄ OPTYMALIZACJI CAŁEJ TRAJEKTORII na horyzoncie 2h.

Po autoteście startowym (jak `risk_function_pid`) buduje DRUGI, niezależny model stanowy - w
rozdzielczości BLOKU 15-minutowego (`dt=STEP_SECONDS=900s`, nie `dt_sterowania` jak "cyfrowy
bliźniak" reszty algorytmów), z tych samych parametrów SOPDT (K/T1/T2/L). Na KAŻDYM przejściu do
nowego bloku 15-minutowego rozwiązuje QP (`scipy.optimize.minimize`, L-BFGS-B, box constraints
0-100%) na 8 przyszłych wartościach mocy, minimalizując:

```
J = w1*Σ(moc_i)² + w2*Σmax(0, próg - HRT_pred_i)² + w3*Σ(moc_i - moc_{i-1})²
```

(energia + kara za deficyt wobec progu bezpieczeństwa z funkcji ryzyka + kara za skoki mocy) i
APLIKUJE STAŁĄ moc z pierwszego bloku planu przez CAŁY ten blok (900s), zanim przeplanuje od nowa -
"move blocking" zamiast klasycznego receding horizon co krok (nierealne obliczeniowo przy
`dt_sterowania`=1s × rok × 43 lokalizacje - patrz uzasadnienie w `Algorytmy/mpc_wspolne.py`).

**Wariant kontrolny**: zaburzenie (CRT) użyte przez MPC do przewidywania WŁASNEJ trajektorii jest
ZAKŁADANE STAŁE (ostatni odczyt) na całym horyzoncie - NIE prognoza Kalmana. Cel/próg bezpieczeństwa
mimo to liczony normalną funkcją ryzyka (`_evaluate_risk_setpoint`, jak `risk_function_pid`), która
WEWNĘTRZNIE korzysta z prognozy Kalmana - "bez prognozy pogody" dotyczy WYŁĄCZNIE mechanizmu
przewidywania trajektorii wewnątrz MPC, nie współdzielonej logiki wyznaczania progu. Punkt
odniesienia do [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md) - różnica energetyczna między nimi to
czysta wartość dodana prognozy pogody przy pełnej optymalizacji trajektorii.

Bezpieczeństwo: niezależnie od zaplanowanej mocy bloku, gdy funkcja ryzyka w BIEŻĄCEJ chwili mówi
`need_heat=False`, moc jest NATYCHMIAST zerowana (nie czeka na granicę bloku) - wyłączenie reaguje od
razu, załączenie czeka na najbliższe przeplanowanie (do 15 min) - asymetria celowa (fail-safe szybkie
wyłączenie, rozważne załączenie).

Fallback: jeśli autotest się nie powiódł (model blokowy nigdy nie powstaje), używa prostego
regulatora P (`MPC_FALLBACK_KC_PERCENT_NA_C`). Jeśli solver QP zawiedzie (wyjątek/NaN), trzyma
OSTATNIĄ zastosowaną moc (nie 0%, nie normę) - status trafia do `diagnostics['mpc_status']`.

## FLOPs

**ZMIERZONE** (nie szacunek analityczny - solver czyni analizę kodu bezcelową): ~800/krok, patrz
[../FLOPs.md](../FLOPs.md) sekcja o `mpc_liniowy`/`mpc_prognoza_pogody`.

## Powiązania

Dziedziczy `_MPCMachineryMixin` (`Algorytmy/mpc_wspolne.py`) + `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy`
(setpoint) + mechanizm autotestu z `rdzen_kontrolera.KontrolerBazowy`. Wariant z pełną prognozą:
[mpc_prognoza_pogody.md](mpc_prognoza_pogody.md). Analogiczny (ale feedforward-only, nie optymalizacja
trajektorii) wykorzystanie cyfrowego bliźniaka: [nauka_kary_blizniak.md](nauka_kary_blizniak.md).
