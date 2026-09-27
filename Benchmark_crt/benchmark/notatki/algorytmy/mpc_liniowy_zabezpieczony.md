# mpc_liniowy_zabezpieczony

- **Plik / klasa / metoda:** `Algorytmy/funkcja_mpc_liniowy_zabezpieczony.py` / `KontrolerMPCLiniowyZabezpieczony` /
  `mpc_liniowy_zabezpieczony`
- **Typ:** MPC (QP, model SOPDT blokowy, zabezpieczony) · **Cel:** Funkcja ryzyka (Kalman) - optymalizacja
  trajektorii BEZ prognozy pogody, z kontrolą wiarygodności · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Kontekst - diagnoza awarii MPC pod HRT_bias (2026-09-15)

W teście awaryjności czujników (`testy/test_awarie_czujnikow.py`, scenariusz `HRT_bias`: czujnik HRT
czyta +5°C cieplej niż rzeczywistość, PRZEZ CAŁĄ symulację) wszystkie trzy warianty MPC bez
zabezpieczeń (`mpc_liniowy`, `mpc_prognoza_pogody`, `mpc_miekkie_ograniczenia`) wykazały +140% do +157%
wzrostu zużycia energii - znacznie więcej niż jakikolwiek regulator PID/histereza na tym samym
scenariuszu (te max. kilkanaście % w dowolną stronę).

**Pierwsza hipoteza (BŁĘDNA, ale pouczająca)**: MPC liczy błąd regulacji względem WŁASNEJ predykcji
modelu blokowego (nie względem zmierzonego HRT), więc w przeciwieństwie do PID nie dostaje
"kompensującej ulgi" tego samego znaku co bias sensora przy wyborze progu w kaskadzie priorytetów
(`funkcja_ryzyka_wspolne._evaluate_risk_setpoint`). To osobny, prawdziwy efekt (patrz warstwa 2 niżej),
ale zmierzone empirycznie: **NIE tłumaczył obserwowanego wzrostu** - poprawka adresująca WYŁĄCZNIE ten
mechanizm (krzyżowa kontrola bieżącego pomiaru) nie zmieniła wyniku (+157.3% przed i po).

**Prawdziwa przyczyna (znaleziona debugowaniem instrumentowanym, nie analizą kodu)**: `autotest()`
(`Algorytmy/rdzen_kontrolera.py`) przerywa skok grzania 0%→100% na PIERWSZYM z trzech zdarzeń, w tym
`hrt >= AUTOTEST_SAFETY_CUTOFF_HRT_C` (~38°C) - sprawdzane na ZMIERZONYM (nie prawdziwym) HRT. Pod
HRT_bias ten próg jest osiągany SZTUCZNIE wcześniej niż w rzeczywistości, ucinając skok w połowie
transjentu. Dopasowanie SOPDT (`_identify_sopdt`) na tak krótkiej, niepełnej krzywej trafia w DOLNE
OGRANICZENIA solvera (`bounds_lower=[0.1, 5.0, 5.0, 0.0]`) - zmierzone bezpośrednio (lokalizacja
abisko, mpc_liniowy, HRT_bias+5°C):

| | K | T1 | T2 | L |
|---|---|---|---|---|
| Baseline (bez awarii) | 51.11 | 1129.2 | 2442.8 | 1185.3 |
| Pod HRT_bias | **5.06** | **5.00** | **5.00** | **~0** |

Model blokowy zbudowany z tych zdegenerowanych parametrów "widzi" grzałkę jako słabą i prawie
natychmiastową - QP wtedy utyka przy 100% mocy próbując dogonić cel, który z takim (fałszywym) modelem
wygląda nieosiągalny, mimo że w rzeczywistości fizyczna HRT dawno przekroczyła cel. Stąd +157% energii -
to defekt IDENTYFIKACJI, nie samej logiki QP/kosztu.

To wyjaśnia też anomalie ADRC/LADRC/NADRC w tym samym teście (`risk_function_ladrc`: -99.8%,
`risk_function_nadrc`: +28.9% pod HRT_bias) - obie korzystają z TEGO SAMEGO `self.autotest_result`
(patrz [adrc.md](adrc.md)) do wyliczenia `b0`/`omega_c`/`omega_o`. PID/histereza są ODPORNE na ten
konkretny defekt, bo ich sterowanie NIE zależy od `autotest_result` (SIMC ma nastawy FIKSOWANE, autotest
zasila tylko OPCJONALNĄ prognozę zanikania ciepła w `_evaluate_risk_setpoint`, nie sam regulator).

## Dwie warstwy zabezpieczeń (`Algorytmy/mpc_wspolne._MPCMachineryMixinZabezpieczony`)

1. **Kontrola jakości dopasowania SOPDT** (`_dopasowanie_wiarygodne`) - odrzuca dopasowanie, jeśli
   `T1`/`T2` trafiły w (lub blisko) dolną granicę solvera (`MPC_MIN_STALA_CZASOWA_S=5.5s` - prawdziwe
   stałe czasowe grzałki są rzędu 10³s, więc trafienie tu nie jest przypadkiem) lub `r_squared` jest
   słabe (`MPC_MIN_R_KWADRAT=0.8`).

   **WAŻNA LEKCJA (pierwsza wersja tej warstwy była NIEBEZPIECZNA, nie tylko nieoptymalna)**: pierwsza
   implementacja przy odrzuceniu dopasowania zostawiała kontroler NA ZAWSZE na prostym regulatorze P
   (`MPC_FALLBACK_KC_PERCENT_NA_C`). Zmierzone empirycznie pod `HRT_bias`: `min_hrt=-17.0°C` (GŁĘBOKO
   pod bezwzględnym floorem -10°C!) i kara bezpieczeństwa ~4.2 mln - GORZEJ niż niezabezpieczony
   wariant referencyjny (`min_hrt=-5.4°C`, kara=0), mimo mniejszej energii (551.7 vs 3356.1 kWh).
   Przyczyna: regulator P liczy błąd względem TEGO SAMEGO zmierzonego (obciążonego +5°C) HRT, który
   jest PRZYCZYNĄ odrzucenia dopasowania - nie ma żadnej ochrony przed samym sensorem, więc pod ciepłym
   biasem systematycznie NIEDOGRZEWA, aż prawdziwa temperatura spada niebezpiecznie. "Bezpieczne"
   okazało się mniej bezpieczne niż "marnotrawne".

   **Poprawka**: gdy dopasowanie jest niewiarygodne, model blokowy jest budowany z BEZPIECZNYCH,
   wcześniej zidentyfikowanych wartości domyślnych (`ADRC_FALLBACK_K/T1/T2/L` z
   `funkcja_ryzyka_adrc_wspolne.py` - ten sam obiekt fizyczny/grzałka, sprawdzone jako
   reprezentatywne: K≈51.1, T1≈1121, T2≈2451, L≈1194 - bardzo bliskie prawidłowo zidentyfikowanym
   wartościom bez awarii) ZAMIAST porzucać model na zawsze. Dzięki temu QP dalej planuje na SENSOWNYCH
   parametrach (nie na zdegenerowanym K=5.06/T1=T2=5.0), a KLUCZOWE - warstwa 2 niżej (wymaga
   zbudowanego modelu) staje się AKTYWNA i może korygować bieżący, zafałszowany pomiar w czasie
   rzeczywistym. `_mpc_model_odrzucony` zostaje jako flaga DIAGNOSTYCZNA (dopasowanie było odrzucone -
   `diagnostics['model_blokowy_odrzucony']`), nie jako "porzuć model na zawsze".

   **Zweryfikowane PO poprawce** (10 dni, abisko, `mpc_liniowy_zabezpieczony` pod `HRT_bias`):
   energia=1210.4 kWh (-64% względem zepsutego 3356.1 kWh referencyjnego), min_hrt=-6.49°C (bezpiecznie,
   porównywalnie do baseline -5.69°C), max_hrt=25.93°C (BEZ przegrzania - niżej niż nawet baseline
   33.5°C, w odróżnieniu od referencyjnego 42.2°C), kara_bezpieczenstwa=0. Jednocześnie bezpieczne I
   energetycznie lepsze - nie kompromis, tylko czysta poprawa względem obu wcześniejszych wersji.

2. **Krzyżowa kontrola bieżącego pomiaru HRT** (`_wiarygodny_pomiar_hrt`, dziedziczone z
   `_MPCMachineryMixin`) - NIEZALEŻNA druga warstwa: nawet gdy model JEST wiarygodny (lub podstawiony
   bezpiecznymi domyślnymi - patrz warstwa 1), porównuje zmierzony HRT z własną predykcją modelu
   blokowego (`C @ x`, D=0 - transmitancja ściśle właściwa) i przy rozbieżności >
   `MPC_SANITY_HRT_DELTA_C=3.0°C` podstawia predykcję modelu w miejsce pomiaru przy wyznaczaniu
   progu/celu (`_evaluate_risk_setpoint`). To WŁAŚNIE ta warstwa faktycznie chroni przed niedogrzaniem
   pod `HRT_bias` (regulator P z warstwy 1, sam, nie ma z czym porównać zmierzonego HRT - potrzebuje
   modelu, który dostaje TERAZ, po poprawce).

Celowo NIE zmieniono istniejących `mpc_liniowy`/`mpc_prognoza_pogody`/`mpc_miekkie_ograniczenia` - na
życzenie użytkownika (2026-09-15) zostają jako niezabezpieczony punkt odniesienia w teście awaryjności,
żeby porównanie pokazało wartość tych dwóch warstw wprost.

## FLOPs

Jak bazowy wariant + stały narzut warstwy 2 (~6 FLOPs/krok, `C @ x` 2-wymiarowe + porównanie) - patrz
[../FLOPs.md](../FLOPs.md).

## Powiązania

Niezabezpieczony punkt odniesienia: [mpc_liniowy.md](mpc_liniowy.md). Analogiczne zabezpieczone warianty:
[mpc_prognoza_pogody_zabezpieczony.md](mpc_prognoza_pogody_zabezpieczony.md),
[mpc_miekkie_ograniczenia_zabezpieczony.md](mpc_miekkie_ograniczenia_zabezpieczony.md). Ten sam
`autotest_result` konsumują też [adrc.md](adrc.md) (LADRC/NADRC) - niezabezpieczone przed tym samym
defektem identyfikacji.
