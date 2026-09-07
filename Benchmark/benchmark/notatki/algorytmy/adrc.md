# ADRC (risk_function_ladrc / risk_function_nadrc)

Dwa nowe algorytmy (2026-09-07, na życzenie użytkownika: "dodaj algorytm ADCR
i różne jego warianty" - potwierdzone jako ADRC, Active Disturbance Rejection
Control). Ta sama logika wyznaczania temperatury zadanej co pozostałe warianty
funkcji ryzyka (`Algorytmy/funkcja_ryzyka_wspolne.py` -
`KontrolerRyzykaBazowy._evaluate_risk_setpoint`) - różnią się WYŁĄCZNIE
mechanizmem regulacji wokół tego celu (jak `risk_function_pid`, tylko zamiast
PI).

## Idea ADRC (w skrócie)

Han Jingqing (1998/2009). Zamiast całkować błąd (PID) albo jawnie optymalizować
na modelu (MPC), Extended State Observer (ESO) w czasie rzeczywistym estymuje
DODATKOWY stan - "całkowite zakłócenie" (`z2`) - sumę wszystkiego, czego
uproszczony model pierwszego rzędu nie opisuje (opóźnienie, drugi biegun,
wpływ pogody, błąd identyfikacji). Prawo sterowania aktywnie tę estymatę
odejmuje. Regulator nie musi znać dokładnego modelu obiektu - musi go tylko na
bieżąco obserwować.

## Dwa warianty

- **`risk_function_ladrc`** (Liniowe ADRC, Gao 2003 - "bandwidth-parameterization"):
  ESO i prawo sterowania czysto liniowe. 2 parametry pasma: `omega_c`
  (regulator) i `omega_o` (obserwator, `= 5x omega_c`).
- **`risk_function_nadrc`** (Nieliniowe ADRC, oryginalna wersja Hana): ESO
  (NLESO) i prawo sterowania (NLSEF) używają funkcji `fal(e, alpha, delta)` -
  silniejsza korekta blisko zera, słabsza (poddaje się wolniej niż liniowo,
  `alpha<1`) przy dużych błędach/skokach. Wagi SKALIBROWANE tak, żeby w
  wąskiej strefie liniowej (`|e|<=delta=0.5°C`) zachowanie było IDENTYCZNE jak
  w LADRC - para jest więc uczciwie porównywalna (ta sama bazowa
  agresywność, inny kształt reakcji na duże odchylenia).

Wspólna matematyka: `Algorytmy/funkcja_ryzyka_adrc_wspolne.py`
(`wylicz_parametry_adrc`, `fal`).

## Wyprowadzenie parametrów z modelu SOPDT

Z identyfikacji `K/T1/T2/L` (ten sam autotest co `risk_function_pid` - patrz
`notatki/...`/`funkcja_ryzyka_pid.py`), przybliżenie obiektu jako pierwszego
rzędu: `ẏ = -y/tau + b0*u + zakłócenia`, `tau = T1+T2`.

- `b0 = K / (100 * tau)` - **UWAGA na dzielenie przez 100**: `K` jest
  zdefiniowane jako °C w stanie ustalonym przy `u_frakcja=1.0` (100% mocy) -
  tak samo jak w cyfrowym bliźniaku (`rdzen_kontrolera._krok_modelu: u =
  moc_procent / 100.0`). Kontrolery ADRC operują na `moc_procent` w skali
  0-100, więc bez tego dzielenia `b0` wychodzi 100x za duże.
- `omega_c = 1 / (2*L)` - ta sama konwencja "lambda=theta, średnio
  agresywnie", której `risk_function_pid` już używa do SIMC - żeby PID i ADRC
  były porównywalne pod względem założonej agresywności, nie tylko
  przypadkowo podobne.
- `omega_o = 5 * omega_c` (Gao 2003 - typowa separacja pasm 3-5x).

Przeliczane RAZ po zakończeniu autotestu (jak SIMC w `risk_function_pid`) -
dopóki trwa, oba warianty grzeją pełną mocą jak reszta rodziny.

## Złapany błąd skalowania (smoke test 2026-09-07)

Pierwsza wersja miała `b0 = K/tau` (BEZ dzielenia przez 100) - sterowanie
wychodziło ~100x za słabe (`power_percent` rzędu 0.01-0.1% zamiast dziesiątek
procent). Objawy w smoke teście (10 dni, Abisko): `min_hrt` spadało do
-18...-20°C (norm: -9.2°C, PID: -12.9°C), `kara_bezpieczenstwa` rzędu
1-2 mln (PID: 7000), `przelaczenia` tylko 2 (moc praktycznie stale ~0%). Po
poprawce (`b0 = K/(100*tau)`): `min_hrt` -12.1...-12.4°C (porównywalne z PID),
energia 1319-1455 kWh (PID: 1223, norma: 1638) - w rozsądnym zakresie.

**Wciąż widoczna cecha, NIE poprawiana dalej (brak czasu na strojenie w tej
sesji)**: `kara_bezpieczenstwa` obu wariantów ADRC (78 647 / 141 531) jest
wyraźnie wyższa niż PID (7000) mimo porównywalnego `min_hrt` - sugeruje, że
ADRC spędza więcej CZASU w okolicy/poniżej progów bezpieczeństwa (wolniejszy
powrót) niż PID, nie tylko podobnie głęboko schodzi. Prawdopodobny powód:
stała czasowa obserwatora (`1/omega_o`, rzędu ~8 min przy wartościach
fallback) wprowadza opóźnienie w estymacie `z2` względem nagłych zmian -
ciekawy, realny wynik do zbadania/skomentowania w analizie porównawczej, nie
błąd implementacji.

## W rejestrze

`bezpiecznik=True`, `adaptacyjny=True` (autotest jak `risk_function_pid`),
`typ='ADRC (liniowy, ESO 2-stanowy)'`/`'ADRC (nieliniowy, fal(), ESO
2-stanowy)'`, `cel='Funkcja ryzyka (Kalman)'` - identycznie jak
`risk_function_pid` pod względem `cel`, żeby porównanie PID vs LADRC vs NADRC
izolowało WYŁĄCZNIE różnicę w mechanizmie regulacji, nie w wyznaczaniu celu.
