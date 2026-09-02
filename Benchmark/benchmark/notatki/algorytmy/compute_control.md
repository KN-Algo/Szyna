# compute_control

- **Plik / klasa / metoda:** `Algorytmy/histereza_let1.py` / `KontrolerHisterezaLET1` / `compute_control`
- **Typ:** Histereza · **Cel:** Progi normy LET-1 · **Adaptacyjny:** nie · **Bezpiecznik:** nie (to
  obecny/domyślny algorytm sterownika — punkt odniesienia dla porównań, nie podlega sam sobie)

## Jak działa

To jest **obecny algorytm sterownika** — implementacja normy LET-1 PKP PLK (rozdział 2.4, automaty
pogodowe) z dwoma czujnikami (CRT niegrzana + HRT grzana), plus dodatkowy 11-stopniowy licznik ryzyka
(`calculate_risk_level`, skala 0-10) używany wyłącznie diagnostycznie (nie steruje decyzją, tylko
raportuje poziom zagrożenia).

Dwa tryby, rozłączne wg obecności opadu (próg `AT ≤ 4.0°C` i wykryty opad/śnieg):
- **Opady** (Tabela nr 5): załącz gdy `CRT ≤ 2.0°C ORAZ HRT ≤ 4.0°C`, wyłącz gdy `CRT > 3.0°C LUB
  HRT > 7.0°C`.
- **Suchy mróz** (Tabela nr 6): załącz gdy `AT ≤ -5.0°C ORAZ HRT ≤ 1.0°C ORAZ CRT ≤ -2.0°C`, wyłącz
  gdy `HRT > 3.0°C`.

Wyjście binarne (0/100%), z limitem przełączeń/dobę (domyślnie 12) — histereza działa TYLKO na
progach zał/wył z tabel, bez pamięci historii ani prognozy (dziedziczy `KontrolerBazowy` wyłącznie po
to, żeby mieć wspólny interfejs pamięci czujników, nie po to, żeby jej używać w logice decyzyjnej).

## Diagnostyka (IAE/ISE/ITAE)

Zwraca `(moc, diagnostics)` — `target_temperature` to próg WYŁĄCZENIA aktywnej gałęzi (opady/suchy
mróz) gdy `heating_on=True` (implicytny cel: to ten próg kończy epizod grzania), `need_heat=heating_on`.

## FLOPs

Szacunek: **45/krok** (`calculate_risk_level` 10 progów + histereza + limit przełączeń). Rzeczywisty
koszt praktycznie stały (brak prognozy/skoków amortyzowanych) — patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Samodzielny plik, dziedziczy `rdzen_kontrolera.KontrolerBazowy` (pamięć czujników, niewykorzystywana
w logice decyzyjnej). Odpowiednik binarny `algorytm_z_normy` (ten sam zestaw progów, bez licznika
ryzyka/limitu przełączeń — czysta implementacja normy).
