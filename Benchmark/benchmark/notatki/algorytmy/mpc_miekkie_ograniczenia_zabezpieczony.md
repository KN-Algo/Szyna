# mpc_miekkie_ograniczenia_zabezpieczony

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_miekkie_zabezpieczony.py` / `KontrolerMPCMiekkieZabezpieczony` /
  `mpc_miekkie_zabezpieczony`
- **Typ:** MPC (QP, model SOPDT blokowy, bariera wykładnicza, zabezpieczony) · **Cel:** Funkcja ryzyka
  (Kalman) + prognoza opadu - optymalizacja trajektorii z barierą bezpieczeństwa, z kontrolą
  wiarygodności · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Jak [mpc_miekkie_ograniczenia.md](mpc_miekkie_ograniczenia.md) (bariera wykładnicza w karze
bezpieczeństwa zamiast czysto progowej), plus TE SAME dwie warstwy zabezpieczeń co
[mpc_liniowy_zabezpieczony.md](mpc_liniowy_zabezpieczony.md) - patrz tam pełna diagnoza (przyczyna
+140.3% energii pod `HRT_bias` w niezabezpieczonym `mpc_miekkie_ograniczenia` w tym samym teście
awaryjności) i opis obu warstw (`Algorytmy/mpc_wspolne._MPCMachineryMixinZabezpieczony`).

## FLOPs

Jak `mpc_miekkie_ograniczenia` + stały narzut warstwy 2 (~6 FLOPs/krok) - patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Niezabezpieczony punkt odniesienia: [mpc_miekkie_ograniczenia.md](mpc_miekkie_ograniczenia.md). Pełna
diagnoza przyczyny/opis zabezpieczeń: [mpc_liniowy_zabezpieczony.md](mpc_liniowy_zabezpieczony.md).
