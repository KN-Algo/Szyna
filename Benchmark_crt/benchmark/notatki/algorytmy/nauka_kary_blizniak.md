# nauka_kary_blizniak

- **Plik / klasa / metoda:** `Algorytmy/funkcja_nauka_kary_pid_blizniak.py` / `KontrolerNaukaKaryPIDBlizniak` /
  `nauka_kary`
- **Typ:** PID (PI, SIMC, uczący się z kar) · **Cel:** Progi normy LET-1 + nauczony czynnik + prognoza
  cyfrowego bliźniaka · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Jak [nauka_kary.md](nauka_kary.md), ale **ADAPTACYJNY** — wykonuje jednorazowy autotest startowy
(identyfikacja SOPDT) i buduje cyfrowy bliźniak (jak `risk_function_pid`), a nastawy PI przelicza
metodą SIMC ze zidentyfikowanych parametrów. Kluczowa różnica wobec `nauka_kary_temp`: źródło
wyprzedzającej kary to **FIZYCZNY model reakcji obiektu** na już wydane komendy mocy (prognoza HRT z
bliźniaka: `rail_temperature_prediction() + zanikanie_ciepla`), nie prognoza POGODY.

Dodatkowa kara (bez przejściowego bonusu — ten wariant NIE ma wyprzedzającego bonusu do celu, tylko
karę do uczenia):
- **-1.0** (ucz się grzać SŁABIEJ), gdy prognoza HRT z bliźniaka pokazuje przewidywane przegrzanie
  (max prognozy > 35°C).
- **+1.0** (ucz się grzać MOCNIEJ), gdy prognoza pokazuje zbliżanie się do floora (min < -8°C, jak
  `RISK_HRT_FLOOR_TRIGGER_C`).

## FLOPs

Szacunek: **470/krok** (progi normy 10 + PI(D) 15 + amortyzowane skoki Kalman/bliźniak 7200 kroków +
przejrzenie prognozy HRT 8 kroków). Autotest startowy nie wliczony (jednorazowy koszt). Patrz
[../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_nauka_kary_wspolna.KontrolerNaukaKaryBazowy` + mechanizm autotestu/bliźniaka z
`rdzen_kontrolera.KontrolerBazowy` (ten sam co `risk_function_pid`). Wariant łączący ze wszystkimi
prognozami: [nauka_kary_ryzyko.md](nauka_kary_ryzyko.md).
