# nauka_kary_ryzyko

- **Plik / klasa / metoda:** `Algorytmy/funkcja_nauka_kary_pid_ryzyko.py` / `KontrolerNaukaKaryPIDRyzyko` /
  `nauka_kary`
- **Typ:** PID (PI, SIMC, uczący się z kar) · **Cel:** Progi normy LET-1 + nauczony czynnik + złożone
  ryzyko (temp+opad+bliźniak) · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

**Najbardziej zaawansowany wariant całego projektu** — łączy WSZYSTKIE TRZY źródła prognozy z
pozostałych wariantów rodziny (`_temp`, `_opad`, `_blizniak`) w JEDNĄ złożoną ocenę ryzyka
(`_wylicz_ryzyko`), zamiast trzech osobnych, niezależnych kar:

- Prognoza AT (Kalman): `+1.0` ryzyka, gdy min prognozy ≤ -12°C (głęboki mróz nadchodzi);
  `+0.5` bonusu chwilowego, gdy najbliższe 2 kroki pokazują AT ≤ -5°C.
- Prognoza opadu (`przewidywanie_opadow.py`): `+1.0` ryzyka i `+0.5` bonusu, gdy front NADCHODZI
  (obecnie sucho, prognoza widzi intensywność); `-1.0` ryzyka, gdy front KOŃCZY SIĘ a pokrywa cienka
  (≤10mm).
- Prognoza HRT z cyfrowego bliźniaka: `-1.0` ryzyka, gdy przewidywane przegrzanie (max > 35°C);
  `+1.0` ryzyka, gdy zbliżanie się do floora (min < -8°C).

Suma `ryzyko` wchodzi jako `dodatkowa_kara` do mechanizmu uczenia dobowego (`_aktualizuj_uczenie`),
`bonus_chwilowy` jako przejściowy dodatek do celu NA TEN krok (nie akumulowany). Adaptacyjny jak
`nauka_kary_blizniak` (autotest + SIMC + bliźniak), plus prognozy AT i opadu na dokładkę.

## FLOPs

Szacunek: **640/krok** — najwyższy w CAŁYM projekcie (progi normy 10 + PI(D) 15 + amortyzowane skoki
Kalman/bliźniak + przejrzenie prognozy AT 8 kroków + rzadkie wywołania prognozy opadu ~160 + przejrzenie
prognozy HRT z bliźniaka 8 kroków — suma wszystkich trzech źródeł prognozy). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_nauka_kary_wspolna.KontrolerNaukaKaryBazowy` + autotest/bliźniak z
`rdzen_kontrolera.KontrolerBazowy` + `przewidywanie_opadow.przewidywanie_opadow`. Warianty z
pojedynczym źródłem prognozy: [nauka_kary_temp.md](nauka_kary_temp.md),
[nauka_kary_opad.md](nauka_kary_opad.md), [nauka_kary_blizniak.md](nauka_kary_blizniak.md).
