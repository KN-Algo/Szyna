# compute_control_gorski

- **Plik / klasa / metoda:** `Algorytmy/histereza_let1_gorski.py` / `KontrolerHisterezaLET1Gorski` /
  `compute_control`
- **Typ:** Histereza · **Cel:** Progi normy LET-1 (rejon górski, pkt 2.4.18.7) · **Adaptacyjny:** nie ·
  **Bezpiecznik:** nie (wariant algorytmu bazowego, tak jak `compute_control`)

## Jak działa

Wariant [compute_control.md](compute_control.md) (dziedziczy `KontrolerHisterezaLET1` bez zmiany
logiki) dla **rejonów górskich**, zgodnie z instrukcją LET-1 PKP PLK S.A., pkt 2.4.18.7:

> "W rejonach górskich gdzie występują bardzo intensywne opady śniegu oraz w szczególnych przypadkach
> można ustawić temperaturę wyłączenia na +10°C."

Zmienia **WYŁĄCZNIE** próg wyłączenia HRT przy opadach (Tabela nr 5, wariant dwuczujnikowy): z
`hrt_off_precip = 7.0°C` (standard) na `10.0°C`. Wszystkie pozostałe progi — załączenie przy opadach
(CRT≤2°C, HRT≤4°C), oraz oba progi suchego mrozu z Tabeli nr 6 — SĄ IDENTYCZNE jak w wariancie
standardowym; norma nie wspomina o ich zmianie dla rejonów górskich, więc pozostają bez zmian.

Efekt praktyczny: grzanie przy opadach trwa **dłużej** (wyłącza się dopiero przy wyższej HRT), co
lepiej wytapia bardzo intensywny/obfity śnieg typowy dla terenów górskich — kosztem większego zużycia
energii niż wariant standardowy w tych samych warunkach pogodowych.

Pełny tekst normy (fragment cytowany przez użytkownika, 2026-09-02):

```
2.4.18.7. W rejonach górskich gdzie występują bardzo intensywne opady śniegu
oraz w szczególnych przypadkach można ustawić temperaturę wyłączenia na + 10°C.
```

## Diagnostyka (IAE/ISE/ITAE)

Dziedziczona bez zmian z `compute_control` - `target_temperature` = próg wyłączenia aktywnej gałęzi
(dla opadów już podniesiony do 10.0°C w tym wariancie), `need_heat=heating_on`.

## FLOPs

Szacunek: **45/krok** — identyczny jak `compute_control` (ta sama logika, tylko inna stała progowa,
zero dodatkowego kosztu obliczeniowego). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `histereza_let1.KontrolerHisterezaLET1` bez nadpisywania żadnej metody (tylko stała w
`__init__`). Wariant standardowy (nie-górski): [compute_control.md](compute_control.md).
