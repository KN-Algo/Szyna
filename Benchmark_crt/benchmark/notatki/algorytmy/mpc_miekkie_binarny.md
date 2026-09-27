# mpc_miekkie_binarny

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_miekkie_binarny.py` / `KontrolerMPCMiekkieBinarny` /
  `mpc_miekkie_binarny`
- **Typ:** MPC (przeszukanie wyczerpujące, model SOPDT blokowy, bariera wykładnicza, wyjście binarne) ·
  **Cel:** Funkcja ryzyka (Kalman) + prognoza opadu - optymalizacja trajektorii z barierą
  bezpieczeństwa, moc binarna · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Dokładnie [mpc_miekkie_ograniczenia.md](mpc_miekkie_ograniczenia.md) (bariera wykładnicza w karze
bezpieczeństwa), ale moc na blok OGRANICZONA do {0%, 100%} - rozwiązywane wyczerpującym przeszukaniem
2^8=256 kombinacji zamiast QP z wyjściem ciągłym, dokładnie jak [mpc_binarny.md](mpc_binarny.md) (patrz
tam pełny opis mechanizmu `_MPCMachineryMixinBinarny`). Dodane 2026-09-15 razem z
[mpc_prognoza_binarny.md](mpc_prognoza_binarny.md), żeby porównanie ciągłe-vs-binarne było KOMPLETNE na
wszystkich 3 wariantach MPC.

Zmierzone (smoke test, abisko, 6 dni): `mpc_miekkie_ograniczenia` energia=875.4 kWh vs
`mpc_miekkie_binarny` energia=2013.2 kWh (IDENTYCZNE z `mpc_prognoza_binarny` w tym konkretnym oknie -
zweryfikowane bezpośrednio, że to zbieg okoliczności, NIE błąd dziedziczenia: dla przykładowych danych
testowych kara progowa i bariera wykładnicza dają różne wartości, 1820.0 vs 40630.1 - po prostu w tak
mroźnym oknie obie funkcje kosztu i tak wskazują 100% mocy w niemal każdym bloku, więc wyczerpujące
przeszukanie binarne trafia na to samo optimum niezależnie od kształtu bariery).

## FLOPs

Szacunek po analogii do `mpc_prognoza_binarny` - patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Ciągły punkt odniesienia: [mpc_miekkie_ograniczenia.md](mpc_miekkie_ograniczenia.md). Analogiczny binarny
wariant z karą progową: [mpc_prognoza_binarny.md](mpc_prognoza_binarny.md). Bez prognozy:
[mpc_binarny.md](mpc_binarny.md).
