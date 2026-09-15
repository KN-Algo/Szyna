# mpc_prognoza_pogody_zabezpieczony

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_prognoza_zabezpieczony.py` / `KontrolerMPCPrognozaZabezpieczony` /
  `mpc_prognoza_zabezpieczony`
- **Typ:** MPC (QP, model SOPDT blokowy, zabezpieczony) · **Cel:** Funkcja ryzyka (Kalman) + prognoza
  opadu - optymalizacja trajektorii Z prognozą pogody, z kontrolą wiarygodności · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Jak [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md) (prognoza Kalmana CRT na horyzoncie, cel z wariantu
funkcji ryzyka Z prognozą opadu), plus TE SAME dwie warstwy zabezpieczeń co
[mpc_liniowy_zabezpieczony.md](mpc_liniowy_zabezpieczony.md) - patrz tam pełna diagnoza (przyczyna
+155.8% energii pod `HRT_bias` w niezabezpieczonym `mpc_prognoza_pogody` w tym samym teście
awaryjności) i opis obu warstw (`Algorytmy/mpc_wspolne._MPCMachineryMixinZabezpieczony`).

## FLOPs

Jak `mpc_prognoza_pogody` + stały narzut warstwy 2 (~6 FLOPs/krok) - patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Niezabezpieczony punkt odniesienia: [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md). Pełna diagnoza
przyczyny/opis zabezpieczeń: [mpc_liniowy_zabezpieczony.md](mpc_liniowy_zabezpieczony.md).
