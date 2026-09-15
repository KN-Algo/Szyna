# mpc_binarny

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_binarny.py` / `KontrolerMPCBinarny` / `mpc_binarny`
- **Typ:** MPC (przeszukanie wyczerpujące, model SOPDT blokowy, wyjście binarne) · **Cel:** Funkcja
  ryzyka (Kalman) - optymalizacja trajektorii BEZ prognozy pogody, moc binarna · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Dokładnie [mpc_liniowy.md](mpc_liniowy.md) (ten sam model blokowy, ten sam cel/funkcja ryzyka, ta sama
częstotliwość przeplanowania co 900s), ale moc na blok OGRANICZONA do {0%, 100%} - przekaźnik
załącz/wyłącz, jak większość pozostałych algorytmów projektu (histereza, PID z ograniczeniem przełączeń
w normie itd.), zamiast wyjścia ciągłego typowego dla SSR/PWM.

Zamiast QP z wyjściem ciągłym (`scipy.optimize.minimize`, L-BFGS-B) rozwiązywane WYCZERPUJĄCYM
przeszukaniem: przy horyzoncie 8 bloków to `2^8=256` kombinacji `{0,100}^8` - tanie obliczeniowo (jedno
przeplanowanie na 900s), więc daje DOKŁADNE optimum globalne wg TEJ SAMEJ funkcji kosztu co wariant
ciągły (`_koszt_mpc` - energia + kara bezpieczeństwa + kara za skoki mocy, patrz
`Algorytmy/mpc_wspolne._MPCMachineryMixinBinarny`). Różni się WYŁĄCZNIE dopuszczalny zbiór mocy - model,
kara i częstotliwość przeplanowania są IDENTYCZNE z `mpc_liniowy`, celowo, żeby porównanie izolowało
wyłącznie koszt dyskretyzacji na przekaźnik binarny.

Fallback regulatora P (używany w krótkim oknie między autotestem a pierwszym blokiem, zanim model
blokowy powstanie) jest RÓWNIEŻ binaryzowany (próg 50%, jak `silniki_fuzzy.binaryzuj`) - inaczej ten
krótki fragment symulacji miałby moc ciągłą, co złamałoby "czystość" binarności całego algorytmu.

**Zmierzone (smoke test, abisko, okno 6 dni)**: `mpc_binarny` energia=2016.0 kWh vs `mpc_liniowy`
energia=827.8 kWh na tym samym oknie - bang-bang musi "przegrzewać" ponad cel, żeby skompensować brak
mocy pośrednich, więc wyższe zużycie energii jest OCZEKIWANYM, nie błędnym wynikiem - to właśnie jest
"koszt dyskretyzacji", który ten algorytm ma zmierzyć.

**Bez zabezpieczeń** (patrz [mpc_liniowy_zabezpieczony.md](mpc_liniowy_zabezpieczony.md)) - celowo, jako
naturalny binarny odpowiednik `mpc_liniowy`, nie `mpc_liniowy_zabezpieczony`.

## FLOPs

Szacunek po analogii do `mpc_liniowy` (256 ewaluacji `_koszt_mpc` na przeplanowanie co 900s, ten sam
rząd wielkości co kilkadziesiąt iteracji L-BFGS-B) - patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Ciągły punkt odniesienia: [mpc_liniowy.md](mpc_liniowy.md). Zabezpieczone warianty (inny wymiar
porównania - jakość identyfikacji, nie dyskretyzacja mocy): [mpc_liniowy_zabezpieczony.md](mpc_liniowy_zabezpieczony.md).
