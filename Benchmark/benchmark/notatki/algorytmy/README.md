# Notatki per algorytm

Jeden plik `.md` na każdy z 32 algorytmów zarejestrowanych w `Algorytmy/rejestr_algorytmow.py`
(`ALGORYTMY` dict) — opisuje jak dany algorytm liczy setpoint/moc, czym różni się od najbliższego
"rodzeństwa", jakie ma własne stałe, i szacunek FLOPs/krok (pełny mechanizm liczenia FLOPs:
[../FLOPs.md](../FLOPs.md)).

**WAŻNE — utrzymanie aktualności**: gdy zmienia się logika decyzyjna, stałe, albo zależności
(dziedziczenie) któregoś algorytmu, notatka `<nazwa_algorytmu>.md` MUSI zostać zaktualizowana W TYM
SAMYM kroku co zmiana kodu — nie osobno, nie "później". To dotyczy też dodania NOWEGO algorytmu do
`rejestr_algorytmow.py`: dostaje od razu własny plik `.md` tutaj, wg tego samego szablonu (nagłówek z
plik/klasa/metoda/typ/cel/adaptacyjny/bezpiecznik, sekcja "Jak działa", sekcja "FLOPs", sekcja
"Powiązania" z linkami do rodzeństwa).

## Bez prognozy/pamięci (progi statyczne)

- [compute_control](compute_control.md) — obecny algorytm sterownika, histereza LET-1 + licznik ryzyka 0-10
- [compute_control_gorski](compute_control_gorski.md) — wariant dla rejonów górskich (LET-1 pkt 2.4.18.7, próg wyłączenia HRT +10°C zamiast +7°C)
- [algorytm_z_normy](algorytm_z_normy.md) — czysta norma LET-1, referencja bezpieczeństwa dla reszty
- [fuzzy_logic_1](fuzzy_logic_1.md) / [_2](fuzzy_logic_2.md) / [_2v2](fuzzy_logic_2v2.md) / [_3](fuzzy_logic_3.md) — fuzzy wokół stałego celu 3°C

## Cel z progów normy LET-1, wykonanie ciągłe/rozmyte

- [norma_pid](norma_pid.md) — PID (SIMC offline) do progu normy
- [fuzzy_normy_1](fuzzy_normy_1.md) / [_2](fuzzy_normy_2.md) / [_2v2](fuzzy_normy_2v2.md) / [_3](fuzzy_normy_3.md)

## Cel z funkcji ryzyka (pamięć + prognoza Kalmana)

- [risk_function](risk_function.md) — histereza binarna
- [risk_function_pid](risk_function_pid.md) — PID adaptacyjny (autotest + SIMC + cyfrowy bliźniak)
- [risk_function_pid_auto](risk_function_pid_auto.md) — jak wyżej + automatyczne strojenie progów setpointu ("perturb-and-observe", realna implementacja propozycji)
- [fuzzy_ryzyko_1](fuzzy_ryzyko_1.md) / [_2](fuzzy_ryzyko_2.md) / [_2v2](fuzzy_ryzyko_2v2.md) / [_3](fuzzy_ryzyko_3.md)

## Cel z funkcji ryzyka + prognoza opadu (przewidywanie_opadow.py)

- [risk_function_opad](risk_function_opad.md) / [risk_function_pid_opad](risk_function_pid_opad.md)
- [fuzzy_ryzyko_1_opad](fuzzy_ryzyko_1_opad.md) / [_2_opad](fuzzy_ryzyko_2_opad.md) / [_2v2_opad](fuzzy_ryzyko_2v2_opad.md) / [_3_opad](fuzzy_ryzyko_3_opad.md)

## Uczenie adaptacyjne z kar (czynnik nauczony, aktualizacja raz/dobę)

- [nauka_kary](nauka_kary.md) — bazowy, czysto reaktywny
- [nauka_kary_temp](nauka_kary_temp.md) — + prognoza temperatury powietrza
- [nauka_kary_opad](nauka_kary_opad.md) — + prognoza opadu
- [nauka_kary_blizniak](nauka_kary_blizniak.md) — + cyfrowy bliźniak (adaptacyjny, autotest)
- [nauka_kary_ryzyko](nauka_kary_ryzyko.md) — łączy wszystkie trzy prognozy (najbardziej złożony, adaptacyjny)

## MPC (optymalizacja CAŁEJ trajektorii na horyzoncie, nie tylko pojedynczego kroku)

- [mpc_liniowy](mpc_liniowy.md) — QP na 8-blokowym horyzoncie 2h, zaburzenie (CRT) STAŁE (wariant kontrolny bez prognozy pogody)
- [mpc_prognoza_pogody](mpc_prognoza_pogody.md) — jak wyżej, zaburzenie z prognozy Kalmana + cel z prognozą opadu (pełna wersja)
- [mpc_miekkie_ograniczenia](mpc_miekkie_ograniczenia.md) — jak mpc_prognoza_pogody, ale bariera wykładnicza zamiast kary progowej za zbliżanie się do progu bezpieczeństwa
- [histereza_pamiec_rosy](histereza_pamiec_rosy.md) — histereza + punkt rosy (polityka P_mem, Chiaradonna i in. 2021) - jedyny algorytm czytający PUNKT_ROSY_C, z pamięcią na wypadek zawieszonego odczytu
- [predykcja_wygladzanie_prosta](predykcja_wygladzanie_prosta.md) — regulator na prognozie HRT wygładzaniem Holta (polityka P_pre, Chiaradonna i in. 2021), margines bezpieczeństwa samokalibrujący się z własnego błędu prognozy
