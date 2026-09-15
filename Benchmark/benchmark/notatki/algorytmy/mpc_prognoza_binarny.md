# mpc_prognoza_binarny

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_prognoza_binarny.py` / `KontrolerMPCPrognozaBinarny` /
  `mpc_prognoza_binarny`
- **Typ:** MPC (przeszukanie wyczerpujące, model SOPDT blokowy, wyjście binarne) · **Cel:** Funkcja
  ryzyka (Kalman) + prognoza opadu - optymalizacja trajektorii Z prognozą pogody, moc binarna ·
  **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Dokładnie [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md) (prognoza Kalmana CRT na horyzoncie, cel z
wariantu funkcji ryzyka Z prognozą opadu), ale moc na blok OGRANICZONA do {0%, 100%} - rozwiązywane
wyczerpującym przeszukaniem 2^8=256 kombinacji zamiast QP z wyjściem ciągłym, dokładnie jak
[mpc_binarny.md](mpc_binarny.md) (patrz tam pełny opis mechanizmu `_MPCMachineryMixinBinarny`). Dodane
2026-09-15 razem z [mpc_miekkie_binarny.md](mpc_miekkie_binarny.md), żeby porównanie ciągłe-vs-binarne
było KOMPLETNE na wszystkich 3 wariantach MPC (do tej pory tylko `mpc_liniowy` miał binarny
odpowiednik).

Zmierzone (smoke test, abisko, 6 dni): `mpc_prognoza_pogody` energia=827.7 kWh vs
`mpc_prognoza_binarny` energia=2013.2 kWh - ten sam kierunek "koszt dyskretyzacji" co
`mpc_liniowy`/`mpc_binarny`.

## FLOPs

Szacunek po analogii do `mpc_binarny` - patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Ciągły punkt odniesienia: [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md). Analogiczny binarny wariant
bez prognozy: [mpc_binarny.md](mpc_binarny.md). Z barierą wykładniczą:
[mpc_miekkie_binarny.md](mpc_miekkie_binarny.md).
