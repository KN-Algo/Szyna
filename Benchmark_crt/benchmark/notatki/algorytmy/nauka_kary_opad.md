# nauka_kary_opad

- **Plik / klasa / metoda:** `Algorytmy/funkcja_nauka_kary_pid_opad.py` / `KontrolerNaukaKaryPIDOpad` /
  `nauka_kary`
- **Typ:** PID (PI, uczący się z kar) · **Cel:** Progi normy LET-1 + nauczony czynnik + prognoza opadu ·
  **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

Jak [nauka_kary.md](nauka_kary.md), plus prognoza OPADU (`przewidywanie_opadow.py`, ten sam
mechanizm co `KontrolerRyzykaOpadBazowy`) dokłada DWIE rzeczy:

1. **Wyprzedzający, PRZEJŚCIOWY bonus** (`+1.0°C`) + **dodatkowa kara** (+1.0), gdy prognoza pokazuje
   INTENSYFIKACJĘ opadu w najbliższych ~30 min (front dopiero nadchodzi — obecnie brak opadu, ale
   prognoza widzi intensywność >0 w 2 najbliższych krokach).
2. **Dodatkowa UJEMNA kara** (-1.0) do mechanizmu uczenia, gdy front WŁAŚNIE KOŃCZY SIĘ (obecnie jest
   opad, prognoza nie widzi już nic w 2 krokach) a pokrywa jest cienka (≤10mm) — pozwala nauczonemu
   czynnikowi szybciej OPAŚĆ, bo nie ma sensu utrzymywać wysokiego czynnika, skoro opad i tak ustaje.

## FLOPs

Szacunek: **175/krok** (progi normy 10 + PI(D) 15 + rzadkie wywołania prognozy opadu ~160/wywołanie).
Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_nauka_kary_wspolna.KontrolerNaukaKaryBazowy`. Wariant bazowy:
[nauka_kary.md](nauka_kary.md). Wariant łączący wszystkie prognozy: [nauka_kary_ryzyko.md](nauka_kary_ryzyko.md).
