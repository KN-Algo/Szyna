# nauka_kary_temp

- **Plik / klasa / metoda:** `Algorytmy/funkcja_nauka_kary_pid_temp.py` / `KontrolerNaukaKaryPIDTemp` /
  `nauka_kary`
- **Typ:** PID (PI, uczący się z kar) · **Cel:** Progi normy LET-1 + nauczony czynnik + prognoza
  temperatury · **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Jak [nauka_kary.md](nauka_kary.md) (mechanizm uczenia z kar, PI identyczne nastawy), plus prognoza
temperatury POWIETRZA (Kalman, `temperature_prediction()`, 8 kroków × 15 min) dokłada DWIE rzeczy:

1. **Wyprzedzający, PRZEJŚCIOWY bonus do celu** (`+1.0°C`, NIE akumulowany na stałe): gdy prognoza w
   najbliższych 2 krokach (~30 min) pokazuje wejście w suchy mróz (AT ≤ -5°C) — grzejemy z lekkim
   wyprzedzeniem, zanim faktycznie zrobi się zimno (obiekt ma bezwładność).
2. **Dodatkowa, WYPRZEDZAJĄCA kara** (+1.0) do mechanizmu uczenia dobowego, gdy prognoza pokazuje
   bardzo głęboki mróz (≤ -12°C w całym horyzoncie) — "uczymy się" trochę szybciej w takich warunkach,
   zamiast czekać, aż realnie dojdzie do niedogrzania.

WAŻNE: mimo korzystania z prognozy Kalmana, `adaptacyjny: False` w rejestrze — bo nie wykonuje
autotestu ani nie przestraja nastaw PI na żywo (to inne pojęcie "adaptacyjności" niż uczenie się
czynnika kary, które dzieje się we WSZYSTKICH wariantach `nauka_kary_*`).

## FLOPs

Szacunek: **165/krok** (progi normy 10 + PI(D) 15 + amortyzowany skok prognozy Kalmana co 300 kroków
+ przejrzenie prognozy 8 kroków ~16/wywołanie). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_nauka_kary_wspolna.KontrolerNaukaKaryBazowy`. Wariant bazowy bez prognozy:
[nauka_kary.md](nauka_kary.md). Wariant łączący wszystkie prognozy: [nauka_kary_ryzyko.md](nauka_kary_ryzyko.md).
