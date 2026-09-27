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

## Model AT → CRT (szyna NIEogrzewana) — `identyfikacja_crt.py`

Wszystkie modele wyżej mają cel **HRT** (szyna ogrzewana), która poza oknem testu skokowego ma
NIEZNANY stan grzania (ograniczenie 1-2 powyżej) — model "długoterminowy" opisuje więc CAŁY układ
zamknięty (pogoda + ew. automatyczne grzanie), nie czystą fizykę szyny. **CRT** ("temperatura szyny
NIEogrzewanej") nie ma tego problemu — z definicji nie zależy od grzania — więc jest czystszym celem
do wyznaczenia transmitancji AT → CRT, odpowiednika `TF_WEATHER` z `Benchmark/benchmark/
symulacja_fizyczna.py` (tam dotąd wzięty z innego, wcześniejszego pomiaru, nie z danych z Wrocławia).

**Weryfikacja założenia** (w oknach testu skokowego, gdzie moc jest znana): przy mocy zmieniającej
się od 0 do pełnej, HRT zmienił się o 43,5–43,6°C, a CRT tylko o 6,0–6,7°C — CRT jest więc w dużej
mierze, ale NIE całkowicie, niezależny od grzania (niewielka resztkowa zmienność to najpewniej zwykłe
ocieplenie otoczenia w trakcie testu/bliskość czujnika, nie efekt cieplny grzałki).

**Dane**: ten sam log co reszta (`algo (4).log`), 21,0 dni po wykluczeniu dni testu skokowego (jak w
`identyfikacja_miso.py`, dla spójności metodologii), 164 391 próbek po 10 s.

**Ranking modeli** (AT → CRT, malejąco wg adj R²):

| Model | Typ | R² | adj R² | RMSE [°C] | MAE [°C] | AIC |
|---|---|---|---|---|---|---|
| **FO_Z** | brak L | **0,9583** | **0,9583** | **2,2612** | 1,7795 | 268 259,5 |
| SO_Z | brak L | 0,9583 | 0,9583 | 2,2613 | 1,7796 | 268 269,4 |
| FO | brak L | 0,9572 | 0,9572 | 2,2896 | 1,7832 | 272 361,6 |
| FOD | L iter. (L*=0) | 0,9572 | 0,9572 | 2,2896 | 1,7832 | 272 363,6 |
| SO | brak L | 0,9572 | 0,9572 | 2,2897 | 1,7832 | 272 377,7 |
| SOD | L iter. (L*=0) | 0,9572 | 0,9572 | 2,2897 | 1,7832 | 272 379,7 |
| TO | brak L | 0,9572 | 0,9572 | 2,2898 | 1,7833 | 272 393,8 |
| I (integrator) | brak L | −0,2993 | −0,2993 | 12,619 | 10,341 | 833 531,1 |

**Najlepszy: FO_Z** (pierwszy rząd z zerem) — `K=1,217`, `T1=2482,3 s` (≈41,4 min), `Tz=690,8 s`
(≈11,5 min). Modele z opóźnieniem (FOD/SOD) zbiegają do `L*=0` — zero w liczniku FO_Z już oddaje
szybką reakcję lepiej niż czyste opóźnienie transportowe, dokładania L nic nie daje.

**Weryfikacja drugiego rzędu z opóźnieniem (SOPDT)** — sprawdzone dodatkowo, na życzenie, czy
model analogiczny do kanału grzania (K/T1/T2/L) nie pasuje tu lepiej:
- Krzywa adj R²(L) dla SOD, przeszukana gęsto 0–2h — **maleje monotonicznie** od L=0 (0,9572) do
  L=2h (0,800), bez żadnego lokalnego maksimum przy L>0.
- Sam drugi rząd (bez L), z 8 różnych punktów startowych — zawsze zwyrodnienie: albo jedna stała
  czasowa ucieka do dolnej granicy (model faktycznie robi się pierwszego rzędu, adj R²=0,9572,
  identyczne jak czysty FO), albo obie stałe się zlewają (T1=T2≈909 s, adj R²=0,9555 — gorzej).
- SOPDT z L jako swobodnym parametrem (dopasowanie gradientowe, nie siatka) — te same wnioski z 4
  różnych startów.
- Kontrola niezależną metodą (korelacja krzyżowa AT↔CRT, bez dopasowania transmitancji): powierzchnia
  bardzo płaska (r=0,968 przy L=0 do r=0,974 przy L≈25–30 min), bez ostrego piku — typowy obraz
  inercji pierwszego rzędu ze stałą czasu rzędu 30-40 min, NIE sygnał realnego opóźnienia
  transportowego (w przeciwieństwie do kanału grzania, gdzie L_H≈1194s jest wyraźne i uzasadnione
  fizycznie bezwładnością grzałki).
- **Wniosek**: SOPDT nie pasuje fizycznie do AT→CRT — ciepło z powietrza dochodzi do nieogrzewanej
  szyny bez wyraźnego opóźnienia transportowego. FO_Z pozostaje najlepszym modelem.

**Porównanie z modelem AT → HRT** (ten sam log, ta sama metoda, `identyfikacja_miso.py`):

| Cel | Model | adj R² | RMSE |
|---|---|---|---|
| HRT (grzanie w tym okresie NIEZNANE) | FO_Z | 0,9691 | 1,567°C |
| **CRT (bez wpływu grzania z definicji)** | FO_Z | **0,9583** | **2,261°C** |

Model CRT ma nieco niższe R² i wyższy RMSE niż model HRT — ale to spodziewane i tłumaczone inaczej,
niż mogłoby się wydawać: to NIE słabszy model, tylko cel z natury trudniejszy do przewidzenia z samej
temperatury powietrza (CRT reaguje na bezpośrednie promieniowanie słoneczne/przewodzenie z gruntu w
większym stopniu niż na samo AT, a te czynniki nie są tu wejściem), podczas gdy model HRT — mimo że
nominalnie ma wyższe R² — de facto myli efekt pogody z nieznanym, niekontrolowanym automatycznym
grzaniem (patrz ograniczenie 2 wyżej). CRT jest więc mniej dokładnym, ale ZA TO uczciwym, czystym
modelem fizycznym.

**Wyniki**: `wyniki_identyfikacja/wyniki_identyfikacji_crt.csv` / `.xlsx`,
`wyniki_identyfikacja/przesiewanie_AT_CRT.png`. Uruchomienie: `python identyfikacja_crt.py`
(z folderu `Identyfikacja/Identyfikacja`).

## Predykcja CRT: Kalman z fizyką jako modelem procesu (`predykcja_kalman_crt.py`)

Na życzenie użytkownika (2026-09-26): do prognozowania CRT (2h, 8 kroków co 15 min, używane w
`Benchmark_crt/benchmark/Algorytmy/rdzen_kontrolera.py`) porównano 3 metody na realnym logu
(19 dni, dni testu skokowego wykluczone):

| Metoda | Co robi | RMSE 2h średnio |
|---|---|---|
| A) Kalman generyczny (poziom+trend) | statystyka, nie zna fizyki obiektu | 2,52°C |
| B) Fizyka, otwarta pętla | zna transmitancję AT→CRT, ale IGNORUJE pomiar CRT | 2,24°C |
| **C) Kalman z modelem procesu = fizyka** | zna transmitancję I koryguje pomiarem CRT co krok | **1,77°C** |

Metoda C wygrywa na każdym horyzoncie od ~30 min wzwyż (przy 120 min: 2,17°C vs 4,14°C dla A —
generyczny Kalman rozjeżdża się bez ograniczenia, fizyka trzyma w ryzach dzięki inercji obiektu).
Przy 15 min A jest odrobinę lepszy (0,63°C vs 0,80°C) — na bardzo krótkim horyzoncie sama
ekstrapolacja trendu wystarcza, przewaga fizyki ujawnia się dopiero z czasem.

**Sprawdzone osobno dla okresów z opadem/śniegiem w horyzoncie prognozy** (n=23) vs bez (n=422) —
dokładność metody C **nie pogarsza się** akurat wtedy, gdy ryzyko jest największe: 1,43°C z
opadem/śniegiem vs 1,79°C bez. (CRT z definicji nie topi śniegu — grzanie idzie do HRT — więc to
sprawdzenie dotyczy wyłącznie jakości samej prognozy pogodowej, nie procesu topnienia.)

**Ważna poprawka techniczna po drodze**: `scipy.signal.tf2ss` daje realizację stanową w postaci
kanonicznej ze stanem w fatalnej skali dla tej transmitancji (C≈0,00035, x rzędu dziesiątek
tysięcy) — matematycznie tożsamej (różnica <1e-14 w odpowiedzi), ale numerycznie zabójczej dla
Kalmana: wzmocnienie K=P·Cᵀ/S wychodzi mikroskopijne i korekta pomiarem ginie w zaokrągleniach
(zmierzone: różnica stanu przed/po korekcie ~1e-4 wobec stanu ~60000 — metody B i C wychodziły
wtedy bit-identyczne, co był sygnał błędu). Naprawione ręczną realizacją stanu w skali fizycznej
(°C) przez rozkład transmitancji na feedthrough D + składnik pierwszego rzędu z jednostkowym
wzmocnieniem.

**Dostrojone parametry filtru** (grid search minimalizujący RMSE 2h): `Q=1e-2`, `R=1e-2` —
wpisane do `rdzen_kontrolera.py` jako `KALMAN_CRT_Q`/`KALMAN_CRT_R`.

Uruchomienie: `python predykcja_kalman_crt.py` (z folderu `Identyfikacja/Identyfikacja`).
