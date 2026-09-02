# fuzzy_logic_1

- **Plik / klasa / metoda:** `Algorytmy/fuzzy_logic_1.py` / `KontrolerFuzzy1` / `compute_control`
- **Typ:** Fuzzy logic (FL1, ciągły) · **Cel:** Stały cel (3°C) · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Regulator rozmyty Sugeno wokół **STAŁEGO** celu `T_ZADANA = 3.0°C` (brak zewnętrznej strategii
setpointu — cel wpisany na sztywno, w odróżnieniu od `fuzzy_ryzyko_*`/`fuzzy_normy_*`, gdzie cel
przychodzi z funkcji ryzyka/normy). Silnik `silniki_fuzzy.wnioskowanie_fl_podstawowe` — 6 reguł Sugeno
na 4 funkcjach przynależności błędu temperatury (`blad_T = T_ZADANA - HRT`: OK/chłodno/mroźno) i HRT
(próg "lodowato" poniżej -15..-12°C), rozgałęzione po obecności opadu/śniegu. Moce wyjściowe
(singletony): OFF=0%, LOW=25%, MED=60%, HIGH=100%.

Wyjście **ciągłe** (0-100%), z miękkim obcięciem krańców (`klamra_fl1`: wynik <10% → 0%, >90% → 100%)
— różni się tym od `fuzzy_logic_2` (twarde 0/100%) i `fuzzy_logic_3` (PWM). Nie dziedziczy
`KontrolerBazowy` (brak pamięci/prognozy — cel jest stały, więc nie potrzebuje historii).

## Diagnostyka (IAE/ISE/ITAE)

Zwraca `(moc, diagnostics)` — `target_temperature = T_ZADANA` (stały), `need_heat=True` zawsze (silnik
dąży do celu bez przerwy, brak stanu zał./wył.).

## FLOPs

Szacunek: **40/krok** (4 funkcje przynależności + 6 reguł Sugeno) — stały koszt, brak amortyzowanych
skoków (brak pamięci/Kalmana). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Samodzielny plik, silnik współdzielony z `fuzzy_logic_2.py` (`silniki_fuzzy.wnioskowanie_fl_podstawowe`).
Ten sam silnik, ale cel z funkcji ryzyka: [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md). Ten sam silnik, cel
z normy: [fuzzy_normy_1.md](fuzzy_normy_1.md).
