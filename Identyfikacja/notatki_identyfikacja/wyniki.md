# Wyniki identyfikacji MISO (2026-09-16, wersja finalna z wiatrem/nasłonecznieniem)

Interpretacja ostatniego przebiegu `identyfikacja_miso.py` na `algo (4).log`
(2026-04-15 → 2026-05-06) + `pogoda_wroclaw_popowice_15min.csv` (Open-Meteo, dokładna lokalizacja
szyny: 51.121933, 17.005006). Metodologia — patrz [README.md](README.md). Surowe wyniki:
`Identyfikacja/wyniki_identyfikacja/` (8 wykresów PNG + `wyniki_identyfikacji_miso.csv/xlsx` +
`wplyw_parametrow.csv`).

## Skąd wiatr i nasłonecznienie

Urządzenie ich nie mierzy (potwierdzone opisem pól). Pobrane osobnym skryptem
(`pobierz_pogode_wroclaw_popowice.py`) z Open-Meteo (historical-forecast-api, ten sam wzorzec co
`Benchmark/benchmark/Generowanie_pogody/generator_pogody.py`) dla DOKŁADNYCH współrzędnych szyny,
siatka 15-min, cały okres logu. **Walidacja**: korelacja temperatury z Open-Meteo z temperaturą z
loga urządzenia = 0,82 (MAE 4,4°C) — sensowna zgodność jak na dane reanalizy siatkowej (~1 km)
kontra dokładny czujnik przy szynie; potwierdza właściwą lokalizację/okres.

## Ile w danych jest momentów grzania (przypomnienie)

Moc znana tylko przez 162 min z 21 dni (0,535% logu), oba testy niemal cały czas załączone
(100%/99,7%) — brak fazy "wyłączone". Reszta logu (99,465%) — stan grzania nieznany.

## Tabela: najlepsza postać transmitancji per kanał

| Kanał | Model | R² | RMSE [°C] | Interpretacja |
|---|---|---|---|---|
| **PWR** (moc→HRT) | FOLP_Z | **0,998** | 0,56 | dominujący, oczekiwany efekt |
| **AT** (powietrze→HRT) | FO_Z | **0,969** | 1,57 | silny, długoterminowy |
| **NASŁONECZNIENIE→HRT** | FO_Z | **0,561** | 5,91 | umiarkowany, ale REALNY (patrz niżej) |
| WIATR→HRT | I | -0,58 | 11,22 | brak sensownego samodzielnego wpływu |
| RH (wilgotność) | SO_Z | -0,22 | 9,85 | brak |
| PRECIP (flaga opadu) | I | -0,74 | 11,76 | brak |
| DPT (punkt rosy) | I | -1,87 | 15,10 | brak |
| PRESS (ciśnienie) | FO_Z | -0,003 | 8,93 | brak |

**Nasłonecznienie MA realny, mierzalny wpływ na HRT** (R²=0,56 samodzielnie na 19 dniach) — fizycznie
sensowne (ciemna stal szyny nagrzewa się od bezpośredniego słońca). **Wiatr NIE ma** mierzalnego
samodzielnego wpływu w tych danych (R² ujemne — gorzej niż stała).

## WAŻNE: znaleziony i naprawiony problem współliniowości w modelu MISO

Pierwsza próba dołączenia nasłonecznienia do wspólnego modelu MISO (okno testu skokowego, 80 min)
dała wynik **fałszywie sugerujący**, że moc grzania ma marginalny wpływ (ΔR² spadło z 0,237 do
0,019!). Przyczyna: test skokowy wypadł w słoneczny poranek — nasłonecznienie było w tym 80-minutowym
oknie **praktycznie stałe** (882→900 na skali 0-900, zmienność zaledwie 0,7% pełnej skali), DOKŁADNIE
jak moc (też stała — czysty skok włącz/na-stałe). Dwa sygnały wyglądające jak "stały skok" w TYM
SAMYM krótkim oknie są statystycznie nierozróżnialne dla dopasowania MNK — model przypisał część
efektu mocy nasłonecznieniu, co jest fizycznie niewiarygodne (3800 W grzania w 80 min nie może
"stracić" 90% swojego wpływu na rzecz słońca).

**Naprawa**: dodano zabezpieczenie — kanał jest wykluczany z modelu MISO, jeśli w oknie dopasowania
ma mniej niż 5% swojej długoterminowej zmienności (za mało "ruchu", żeby wiarygodnie oddzielić jego
wpływ od współwystępującej mocy). Nasłonecznienie zostało poprawnie wykluczone z MISO (jego
SAMODZIELNY wynik z długiego okna, R²=0,56, zostaje w tabeli — to wciąż wiarygodna informacja, tylko
nie nadaje się do WSPÓLNEGO dopasowania na TYM konkretnym, krótkim oknie).

## Model KRÓTKOTERMINOWY (MISO, okno testu skokowego, po naprawie)

`HRT = y0 + G_PWR(moc) + G_AT(AT)` — **R² = 0,9991, RMSE = 0,355°C**. Wpływ: **PWR ΔR²=0,237**
(dominujący), AT ΔR²=0,001 (marginalny w tym krótkim oknie, bo AT też mało się zmienia w 80 min —
ale patrz model długoterminowy, gdzie AT jest drugim najważniejszym czynnikiem po mocy).

## Model DŁUGOTERMINOWY (bez mocy, ~19 dni)

Najlepszy pojedynczy kanał: **AT / FO_Z, R² = 0,9691, RMSE = 1,567°C**. Opisuje zachowanie CAŁEGO
układu zamkniętego (pogoda → ew. automatyczne grzanie → HRT), nie czystej fizyki bez grzania — stan
grzania w tym okresie nieznany (patrz wyżej).

## Ranking wpływu WSZYSTKICH sprawdzonych parametrów (samodzielne R², malejąco)

1. PWR (moc grzania) — 0,998
2. AT (temperatura powietrza) — 0,969
3. NASŁONECZNIENIE — 0,561 (rzeczywisty wpływ, wykluczony tylko ze wspólnego MISO z powodu
   współliniowości z mocą w konkretnym oknie testowym)
4. PRESS (ciśnienie) — ~0 (brak wpływu)
5. WIATR — poniżej 0 (brak wpływu)
6. PRECIP (flaga opadu) — poniżej 0 (brak wpływu)
7. DPT (punkt rosy) — poniżej 0 (brak wpływu, najgorszy)
8. RH (wilgotność) — poniżej 0 (brak wpływu)

## Ograniczenia (podsumowanie)

1. Moc grzania nieznana poza 0,535% logu — model MISO z mocą wiarygodny TYLKO w tym oknie.
2. Model długoterminowy = odpowiedź układu zamkniętego, nie czysta fizyka bez grzania.
3. Wiatr/nasłonecznienie to dane reanalizy Open-Meteo (siatka ~1km), nie pomiar na miejscu -
   korelacja z lokalną temperaturą 0,82 (rozsądna, nie idealna).
4. Współliniowość: kanały prawie stałe w krótkim oknie testowym są automatycznie wykluczane z
   modelu MISO (nawet jeśli mają dobry wynik długoterminowy) - inaczej dają fałszywe wyniki.
5. Kosmetyczny transient na starcie + 2 mikro-artefakty przy zszytych dniach na wykresie długoterminowym.
6. Opóźnienia L ustalone z etapu przesiewania, niereoptymalizowane wspólnie w modelu MISO.
