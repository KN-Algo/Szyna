# risk_function_pid

- **Plik / klasa / metoda:** `Algorytmy/funkcja_ryzyka_pid.py` / `KontrolerRyzykaPID` / `risk_function_pid`
- **Typ:** PID (PI, SIMC) · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** tak · **Bezpiecznik:** tak

## Jak działa

Setpoint liczony przez `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy._evaluate_risk_setpoint` — kaskada
**4 twardych priorytetów** sprawdzanych po kolei, pierwszy spełniony wygrywa:

1. **Marznący deszcz** → grzej bezwarunkowo, target 7.0°C.
2. **Śnieg / zalegająca pokrywa (>5mm)** → target 4.0°C + kara za grubość pokrywy (do +6.0°C), CHYBA
   że prognoza CRT (Kalman, `rail_temperature_prediction`) pokazuje ocieplenie w ~30 min i pokrywa
   jest cienka — wtedy nie grzejemy na zapas.
3. **Ochrona floora** → jeśli HRT ≤ -8°C lub prognoza pokazuje ≤ -12°C w horyzoncie 2h, grzej z
   wyprzedzeniem do -5.0°C (zapas przed bezwzględnym minimum -10°C).
4. **Suchy mróz** → progi LET-1, target 1.0°C.

Jeśli nic się nie spełni — nie grzej. Pełny diagram: artefakt "Funkcja ryzyka" (opublikowany w tej
rozmowie) albo bezpośrednio kod w `funkcja_ryzyka_wspolne.py`.

**PRZY STARCIE** wykonuje jednorazowy autotest (`_autotest_startowy` — skok grzania 0%→100%,
identyfikacja SOPDT: K, T1, T2, L). Dopóki trwa, grzeje pełną mocą i pomija normalną logikę. Po
udanej identyfikacji PRZELICZA własne nastawy PI metodą SIMC (Skogestad, λ=θ) ze ŚWIEŻO
zidentyfikowanych parametrów — dostraja się do REALNEGO obiektu, nie do wartości poznanych wcześniej w
innym teście. Nastawy fabryczne (używane do czasu autotestu i jako fallback, gdyby identyfikacja się
nie powiodła): `Kc=2.9262 %/°C`, `Ti=3571.88 s` (z K=51.12, T1=1120.9, T2=2451.0, L=1194.2).

Regulator ciągły (0-100%) z anti-windup (całka zamrożona, gdy wyjście w nasyceniu 0%/100%). Jeśli
model został zidentyfikowany, dokłada do prognozy CRT fizyczną prognozę zanikania ciepła z ostatnio
wydanych komend mocy ("cyfrowy bliźniak") — realnie poprawia `warmup_soon`/`forecast_min_c` tam, gdzie
w rurze zostało jeszcze ciepło z niedawnego grzania.

## FLOPs

Szacunek: **450/krok** (kaskada 20 + PI(D) 15, plus amortyzowane skoki: Kalman co 300 kroków,
cyfrowy bliźniak 7200 kroków). Autotest startowy (do 14400 kroków, jednorazowo) NIE wliczony do tej
liczby. Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` ← `rdzen_kontrolera.KontrolerBazowy`.
Siostrzany wariant binarny: [risk_function.md](risk_function.md). Wariant z prognozą opadu:
[risk_function_pid_opad.md](risk_function_pid_opad.md). Ten sam setpoint, wykonawczo silnikiem fuzzy:
[fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md) i pochodne.
