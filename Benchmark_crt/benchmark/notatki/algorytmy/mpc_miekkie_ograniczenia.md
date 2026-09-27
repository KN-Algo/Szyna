# mpc_miekkie_ograniczenia

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_miekkie.py` / `KontrolerMPCMiekkie` / `mpc_miekkie`
- **Typ:** MPC (QP, model SOPDT blokowy, bariera wykładnicza) · **Cel:** Funkcja ryzyka (Kalman) +
  prognoza opadu - optymalizacja trajektorii z barierą bezpieczeństwa · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Identyczny jak [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md) (ta sama prognoza CRT z Kalmana, ten
sam cel Z prognozą opadu, ta sama maszyneria QP/model blokowy/move-blocking - patrz
`Algorytmy/mpc_wspolne.py`) - **jedyna różnica to KSZTAŁT kary za zbliżanie się do progu
bezpieczeństwa** w funkcji kosztu QP:

- `mpc_liniowy`/`mpc_prognoza_pogody` (domyślna implementacja w `_MPCMachineryMixin.
  _kara_bezpieczenstwa_mpc`): kara **kwadratowa PROGOWA** - dokładnie ZERO, dopóki przewidywana HRT
  jest nad progiem, `MPC_WAGA_BEZPIECZENSTWO × deficyt²` dopiero po przekroczeniu.
- `mpc_miekkie_ograniczenia` (nadpisuje `_kara_bezpieczenstwa_mpc`): **bariera wykładnicza** -
  `kara = MPC_BARIERA_W × exp(-MPC_BARIERA_K_NA_C × margin)`, gdzie `margin = hrt_pred - target`.
  Kara jest NIGDY dokładnie zerowa (nawet daleko nad progiem zostaje mała, malejąca wykładniczo
  zachęta do trzymania zapasu), a POD progiem rośnie szybciej niż kwadratowo. Wykładnik jest obcięty
  do ±50 (`MPC_BARIERA_WYKLADNIK_LIMIT`) - zabezpieczenie numeryczne przed przepełnieniem float64 przy
  skrajnych, przejściowych próbkach solvera, bez wpływu na optymalne rozwiązanie.

**Cel testu** (patrz specyfikacja MPC w `AGENTS.md`): sprawdzić, czy sam kształt kary progowej wpływa
na kompromis energia/bezpieczeństwo, niezależnie od tego, że zewnętrzny bezpiecznik normy
(`snow_reference_mm` w `symulacja_fizyczna.py`) i tak obcina wyjście z zewnątrz. Oczekiwanie: MPC z
barierą powinien "wyprzedzająco" zostawiać większy zapas cieplny nad progiem niż wariant z karą czysto
progową (potwierdzone na smoke teście, patrz `AGENTS.md`).

Reszta mechaniki (move blocking co 900s, bezpieczeństwo - natychmiastowe zerowanie mocy przy
`need_heat=False`, fallback P przy braku modelu, fallback "ostatnia moc" przy niepowodzeniu solvera)
identyczna jak `mpc_liniowy`/`mpc_prognoza_pogody` - patrz [mpc_liniowy.md](mpc_liniowy.md) i
`Algorytmy/mpc_wspolne.py`.

## FLOPs

SZACUNEK po analogii do `mpc_prognoza_pogody` (~805/krok) - identyczna struktura kosztu solvera,
jedyna różnica to inny wzór skalarny w `_kara_bezpieczenstwa_mpc`. Do zmierzenia realnie przy
najbliższym pełnym przebiegu testowym, patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `_MPCMachineryMixin` (`Algorytmy/mpc_wspolne.py`, nadpisuje hook
`_kara_bezpieczenstwa_mpc`) + `funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy` (setpoint + prognoza
opadu). Wariant z karą czysto progową (kontrolny): [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md).
Wariant bez prognozy pogody w ogóle: [mpc_liniowy.md](mpc_liniowy.md).
