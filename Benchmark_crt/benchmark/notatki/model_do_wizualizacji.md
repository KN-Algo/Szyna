# Model symulacyjny ogrzewania rozjazdu (wariant CRT, ze słońcem) - opis obiektów do wizualizacji

Ten dokument opisuje **wszystkie obiekty modelu, ich parametry i połączenia**, tak żeby na jego podstawie można było narysować
schemat/wizualizację bez zaglądania w kod. Przy każdej liczbie zaznaczone jest, czy jest **ZMIERZONA** (zidentyfikowana z realnych
danych), **ZAŁOŻONA** (przyjęta bez pomiaru) czy **WYLICZANA** w trakcie symulacji. Stan na 2026-09-28 (po dodaniu nasłonecznienia).

## 0. Zadanie dla tego, kto rysuje

Zrób czytelną wizualizację (najlepiej kilka widoków; propozycje w sekcji 8):
1. **Schemat przepływu sygnałów obiektu fizycznego** (sekcje 2-3) - najważniejszy rysunek.
2. **Kanał nasłonecznienia** (sekcja 2, P11) - jak z sekund słońca powstaje nagrzewanie szyn.
3. **Architektura kontrolera** (sekcja 4) i **drzewo rodzin algorytmów** (sekcja 5).
4. Wykres odpowiedzi skokowej HRT vs CRT na moc grzania (sekcja 3).

Konwencje graficzne, które proszę zachować:
- **Ciągła ramka** = element zmierzony/zdefiniowany; **przerywana ramka** = element ZAŁOŻONY (nie pomiar).
- **Niebieski = HRT** (szyna ogrzewana), **pomarańczowy = CRT** (szyna zimna/nieogrzewana), **żółty = nasłonecznienie**. Trzymać spójnie.
- Strzałka **moc grzania → CRT** cienka/przerywana (słaby, wolny wpływ).

## 1. Po co jest model

Benchmark porównuje algorytmy sterowania elektrycznym ogrzewaniem rozjazdów kolejowych (PKP PLK, instrukcja LET-1): mają nie dopuścić do
zalegania śniegu/lodu, zużywając jak najmniej energii. Wariant **CRT** bada sytuację, gdy głównym wyznacznikiem decyzji jest **szyna zimna
(CRT)**, a nie ogrzewana (HRT). Zależy na **wytopieniu śniegu w całości** - dlatego CRT mówi też kontrolerowi, ile śniegu zostało.
**CRT** = temperatura szyny nieogrzewanej (duży obiekt, duża bezwładność). **HRT** = szyna ogrzewana. **AT** = temperatura powietrza.

## 2. Obiekt fizyczny - lista obiektów

Krok symulacji: **dt = 10 s**, pełny sezon zimowy na lokalizację, **44 lokalizacje** (pliki pogodowe, godzinowe, ERA5-Land; Wrocław 15-min).

| ID | Obiekt | Wejście → wyjście | Parametry | Status |
|---|---|---|---|---|
| E1 | **Dane pogodowe** (CSV, 1 plik = 1 lokalizacja, ze współrzędnymi) | → AT, punkt rosy, wiatr, opad, **nasłonecznienie [s słońca w godzinie]** | interpolowane do dt | dane |
| P1 | **G_W: pogoda → szyna** (wspólna dla obu szyn) | AT → składowa pogodowa `W` | K=0,987; T1=5146 s (86 min); Tz=1321 s (22 min); bez opóźnienia | ZMIERZONA (Wrocław), przeliczona RAZEM ze słońcem |
| P2 | **Linia opóźnienia mocy** | moc → `u` | L = 0 | zmierzona |
| P3 | **G_H: moc → HRT** | u → `H` | K=47,17 °C na 100% mocy; T1=2462 s (41 min); Tz=204 s (3,4 min) | ZMIERZONA |
| P4 | **G_HC: moc → CRT** | u → `HC` | K=4,72 °C na 100% mocy (=10% K_H); T1=14400 s (4 h); bez członu różniczkującego | **ZAŁOŻONA** |
| P5 | **Sumatory** | | `HRT = W + S_h + H`,  `CRT = W + S_c + HC` | - |
| P6 | **Model śniegu i lodu** (pochodna SnowClim) | pogoda, **HRT** → grubość śniegu [mm], lód [mm] | - | model fizyczny |
| P7 | **Blok czujników** | → wiersz danych dla kontrolera | patrz 4.1 | - |
| P8 | **Zabezpieczenie termiczne 45°C** | HRT → wymusza moc 0 | zatrzask od HRT≥45°C, zwolnienie poniżej 40°C (histereza 5°C ZAŁOŻONA); tylko algorytmy NIE-fuzzy | wymóg sprzętu + założenie |
| P9 | **Bezpiecznik z normy** | trajektoria normy → korekta mocy | jeśli zalega śnieg i moc normy > moc algorytmu, przejmuje moc normy (`max`) | mechanizm testowy |
| P10 | **Metryki** | | energia, przełączenia, IAE/ISE/ITAE, kara bezpieczeństwa (HRT i CRT), czas >45°C | - |
| **P11** | **G_S: słońce → szyna** (kanał nasłonecznienia, NOWY) | wejście słońca → `S_h` (do HRT), `S_c` (do CRT) | HRT: K=9,63 °C, T=35 062 s (9,7 h); CRT: K=12,77 °C, T=5651 s (94 min); pierwszy rząd K/(Ts+1) | ZMIERZONA na 1 wiośnie (Wrocław); HRT słabo zidentyfikowane |

### Wejście słońca (P11)
`wejście = ułamek_słońca × sin(wysokość_słońca)`, wartość 0..1:
- **ułamek_słońca** = sekundy słońca / długość przedziału (3600 s dla plików godzinowych): **0 = brak słońca (noc lub pełne zachmurzenie), 1 =
  pełne słońce przez cały przedział** (dla przedziału 15 min max = 900 s). Wartość godzinowa = średnia w godzinie, ustawiona w środku godziny,
  **interpolowana liniowo** do kroku symulacji (dane gęstsze niż godzinowe nie są dostępne dla wszystkich lokalizacji; test na Wrocławiu:
  wejście godzinowe jest równie dobre jak 15-minutowe - RMSE 1,19 vs 1,20 °C).
- **sin(wysokość słońca)** liczony ze współrzędnych lokalizacji i czasu UTC (NOAA) - nadaje dobowy kształt natężenia (rano/wieczorem słabsze).
  Bez tego czynnika RMSE CRT jest 1,9 °C zamiast 1,2 °C.
- Wejście 1,0 = słońce w zenicie na czystym niebie. Kontroler **nie widzi słońca** (urządzenie go nie mierzy) - odczuwa je tylko przez CRT/HRT.
- **Zimowe tłumienie:** parametry P11 pochodzą z wiosny bez śniegu, a zimą śnieg odbija promieniowanie, więc w symulacji wkład słońca (`S_h`, `S_c`)
  jest mnożony przez **0,5** (ZAŁOŻENIE po ostrożnej stronie: szyny chłodniejsze niż przy pełnym słońcu; stała `WSPOLCZYNNIK_SLONCA_ZIMA`,
  1,0 = bez tłumienia). Wykresy zgodności z danymi (sekcja 6) pokazują model BEZ tłumienia (dane są z wiosny).

### Kolejność w jednym kroku symulacji
1. Odczyt pogody → składowa pogodowa `W` (P1) i składowe słoneczne `S_h`, `S_c` (P11).
2. Wiersz czujników (P7) → kontroler → moc żądana.
3. Bezpiecznik z normy (P9) może podnieść moc. 4. Zabezpieczenie 45°C (P8) działa ostatnie, może zerować moc.
5. Moc → opóźnienie (P2) → G_H (P3) i G_HC (P4) → nowe HRT i CRT (P5).
6. Model śniegu (P6) z aktualnego HRT. 7. Naliczenie metryk (P10).

## 3. Schemat przepływu sygnałów

```
 E1 Pogoda (CSV) ──AT──► G_W(s) ────────────────────┬───────────────────────┐
   │  K=0,987 T1=86 min Tz=22 min                   │ W                     │ W
   │                                                ▼                       ▼
   └─ sekundy słońca ─► ułamek × sin(wys. słońca) ─► P11 G_S(s)          ┌─────┐
                                                     │ S_h ─────────────► │  +  │─► HRT
   moc żądana ─► bezpiecznik ─► zabezp. 45°C ─► u ──►│ S_c ─────┐         └─────┘
   (kontroler)   normy (max)    (zeruje moc)         │          ▼            ▲ H
                                                     │       ┌─────┐   G_H(s) K=47,2 T1=41 min
                                                     │       │  +  │─► CRT     ▲
                                                     │       └─────┘           │
                                                     │          ▲ HC    G_HC(s) K=4,72 T1=4 h (ZAŁOŻONA)
   HRT + pogoda ─► MODEL ŚNIEGU I LODU ─► śnieg [mm], lód [mm]
```

**Odpowiedź na pełną moc od zera (bez pogody i słońca):**

| po czasie | wkład grzania w HRT | wkład grzania w CRT |
|---|---|---|
| 32 min | 27,3 °C | 0,6 °C |
| 41 min (T1 HRT) | 31,3 °C | 0,7 °C |
| 1 h | 37,1 °C | 1,0 °C |
| 4 h (T1 CRT) | 47,0 °C | 3,0 °C |
| 12 h | 47,2 °C | 4,5 °C |
| ustalony | 47,2 °C | 4,7 °C |

Przy włączeniu mocy HRT skacze natychmiast o K·Tz/T1 = 3,9 °C (człon różniczkujący). Sedno: **HRT szybko i mocno reaguje na moc, CRT prawie
wcale i wolno**; na wykresie użyj jednej osi °C i osobnego panelu z przybliżeniem CRT.
Stan ustalony pogody: szyna ≈ 0,99 · AT (plus słońce w dzień); przy pełnym słońcu w zenicie CRT jest o ok. 12,8 °C cieplejsze, HRT o ok. 9,6 °C.

## 4. Kontroler - lista obiektów

Każdy algorytm dziedziczy wspólny **rdzeń kontrolera** i widzi wyłącznie to, co daje blok czujników.

### 4.1 Blok czujników (co widzi kontroler)
`CRT` (prawdziwe: pogoda + słońce + słaby wkład grzania z poprzedniego kroku), `HRT` (z poprzedniego kroku), `AT`, wilgotność, opad, intensywność
śniegu, punkt rosy, wiatr. **NIE widzi** nasłonecznienia ani prawdziwej grubości śniegu (liczy własny estymator K7).

### 4.2 Obiekty rdzenia (wspólne)
| ID | Obiekt | Co robi |
|---|---|---|
| K1 | **Pamięć czujników** | średnie w binach 15 min (bufor 36 = 9 h) |
| K2 | **Prognoza AT** | Kalman (poziom+trend), 2 h = 8 kroków po 15 min |
| K3 | **Prognoza CRT (Kalman fizyczny)** | model pogoda→CRT (te same K/T1/Tz co P1, bez słońca) korygowany zmierzonym CRT (Q=R=0,01) |
| K4 | **Autotest** | przy starcie: skok mocy 0→100%, dopasowanie SOPDT (K, T1, T2, L); koniec przy HRT=38°C / ustabilizowaniu / po 4 h |
| K5 | **Cyfrowy bliźniak HRT** | SOPDT z autotestu; prognoza zanikania ciepła po wyłączeniu |
| K6 | **Cyfrowy bliźniak CRT** | G_HC (K=4,72, T1=4 h, **założony**) |
| K7 | **Estymator śniegu** | przyrost = intensywność opadu śniegu; ubytek = 0,001 mm/s na °C · max(**CRT**,0) |
| K8 | **Prognoza opadu** | intensywność 0-3, horyzont 2 h |

### 4.3 Funkcja ryzyka - cel (współdzielona przez `risk_function*`, MPC, `fuzzy_ryzyko*`)
Kaskada priorytetów (pierwszy spełniony wygrywa):
1. **Marznący deszcz** → grzej bezwarunkowo (cel 3 °C).
2. **Opad śniegu lub zalegający śnieg > 5 mm** → grzej (cel 2 °C + kara 0,0073 °C/mm, max +0,88 °C), chyba że prognoza CRT pokazuje ocieplenie za ~30 min
   przy cienkiej pokrywie. **2b.** Front opadowy za ~30 min i AT lub CRT ≤ 2 °C → grzanie wyprzedzające.
3. **Ochrona przed spadkiem CRT poniżej −10 °C**: CRT ≤ −8 °C lub prognoza 2 h ≤ −12 °C → cel −5 °C.
4. **Suchy mróz** (AT ≤ −5 °C) → cel −5 °C. 5. W innym razie: brak zagrożenia, nie grzej.
Progi celu z kolumny „szyna nieogrzewana” tabel 5/6 normy LET-1. Twardy dolny limit bezpieczeństwa szyny: −10 °C.

### 4.4 Regulatory
| Typ | Zasada |
|---|---|
| **Histereza binarna** | włącz gdy CRT < cel, wyłącz gdy CRT ≥ cel + 2 °C; min. odstęp 60 s, limit przełączeń na dobę (100) |
| **PI ciągły** | błąd względem CRT, nastawy SIMC z autotestu, anty-windup |
| **Kaskada 2×PI** | zewnętrzna (wolna): błąd CRT → zadana HRT; wewnętrzna (szybka): błąd HRT → moc |
| **PI binarny z histerezą 2 °C** | błąd CRT + całka (Ti z SIMC, ±2 °C) → przekaźnik Schmitta: załącz przy +1 °C, wyłącz przy −1 °C |
| **ADRC / LADRC / NADRC** | obserwator stanu rozszerzonego zamiast całki |
| **MPC** | 8 bloków po 15 min; koszt = energia + deficyt względem celu + zmiany mocy + 1000·(HRT_prog−45)²; warianty ciągłe/binarne/zabezpieczone |
| **Fuzzy Sugeno** | FL1 (ciągły), FL2/FL2v2 (binarny), FL3 (PWM 60 s) |
| **Uczenie z kar** | PID do progów normy + współczynnik korygowany raz na dobę |
| **Automat/histereza z normy** | progi LET-1 (załącz/wyłącz), także wariant górski |

## 5. Drzewo rodzin algorytmów (52 algorytmy w rejestrze)

```
Algorytmy
├─ Wg normy LET-1: compute_control, compute_control_gorski, algorytm_z_normy (punkt odniesienia), norma_pid, fuzzy_normy_*
├─ Funkcja ryzyka (pamięć + Kalman + bliźniaki + opad)   ← CRT jako wyznacznik
│    ├─ binarna: risk_function, _opad        ├─ PI ciągły: risk_function_pid, _pid_opad, _pid_auto
│    ├─ PI binarny z histerezą 2°C: risk_function_pi_binarny
│    ├─ Kaskada 2×PI: risk_function_cascade_pi, _opad
│    └─ ADRC: risk_function_ladrc, risk_function_nadrc
├─ MPC (9): ciągłe / binarne × {liniowy, z prognozą pogody, miękkie ograniczenia} + „zabezpieczone”
├─ Fuzzy logic (22): fuzzy_logic_*, fuzzy_ryzyko_* (+ _opad, adaptacyjny, agresywny), fuzzy_ryzyko_2v2_[opad_]crt_[progi|pelny]
├─ Uczenie z kar: nauka_kary, _temp, _opad, _blizniak, _ryzyko
└─ Z literatury: histereza_pamiec_rosy, predykcja_wygladzanie_prosta
```
(Fuzzy: zabezpieczenie 45 °C tylko monitoruje, nie wymusza mocy.)

## 6. Zgodność modelu z realnymi danymi (Wrocław Popowice, 21 dni kwiecień-maj 2026)

RMSE pomiar vs model, ze słońcem (i bez, dla porównania):

| | CRT | HRT (poza oknami testu grzania) |
|---|---|---|
| całe 21 dni | 1,22 °C (R² 0,988), było 2,23 | 1,15 °C (R² 0,984), było 2,72 |
| tydzień 20-27.04 | 1,39 °C, było 2,22 | 1,07 °C, było 2,01 |
| doba 22.04 | 1,54 °C, było 2,54 | 0,78 °C, było 2,37 |
| okno testu grzania (ON) | 1,36 °C (było 1,32) | 1,47 °C, było 4,12 |

Stary G_W (K=1,217) wchłonął średnie nagrzewanie słoneczne; sam kanał słoneczny dołożony do niego nic nie dawał - trzeba było przeliczyć G_W
razem ze słońcem (K spadło do 0,99).

## 7. Metryki i uruchamianie

Energia [kWh], przełączenia (budżet 100/dobę, 500 000 na życie), IAE/ISE/ITAE, **kara bezpieczeństwa** (zalegający śnieg > 5 mm + marznący deszcz przy szynie
< 2 °C + spadek poniżej −10 °C; osobno HRT i CRT), max/min HRT i CRT, czas powyżej 45 °C. Wynik: Excel (pierwsza zakładka: średnia moc, suma kar, kara HRT,
kara CRT; wartości w % względem normy). 44 lokalizacje × 52 algorytmy ≈ 2300 zadań, równolegle; na klastrze WCSS dzielone na węzły po 128 rdzeni.

## 8. Propozycje widoków

1. **Schemat obiektu** (sekcje 2-3): bloki E1, P1-P11, dwa tory (niebieski HRT, pomarańczowy CRT), żółty kanał słońca, przerywana ramka wokół P4.
2. **Kanał słońca**: wejście (ułamek, sinus, iloczyn) przez 3 bezchmurne doby i nagrzewanie CRT (szybkie, ~9 °C w południe) vs HRT (wolne, ~4 °C).
3. **Oś czasu jednego kroku** (kolejność 1-7 z sekcji 2). 4. **Architektura kontrolera** (K1..K8 → drabinka priorytetów → regulator → moc).
5. **Drzewo rodzin** (sekcja 5). 6. **Odpowiedź skokowa HRT vs CRT** (tabela w sekcji 3).
7. **Zgodność z danymi**: tydzień i doba - HRT/CRT pomiar vs model, residua, AT, słońce, załączenie grzania.

### Gotowe rysunki (wersja referencyjna)
`notatki/rysunki/`: `01_schemat_obiektu.png`, `02_architektura_kontrolera.png`, `03_odpowiedz_skokowa_hrt_crt.png`, `04_kanal_sloneczny.png`
(generator `generuj_wizualizacje_modelu.py`). Zgodność z danymi: `Identyfikacja/wyniki_identyfikacja/model_z_sloncem_tydzien.png` i
`model_z_sloncem_dzien.png` (skrypt `Identyfikacja/Identyfikacja/dopasowanie_nasloneczenia.py`).

## 9. Ograniczenia i zastrzeżenia (proszę ująć na rysunku/legendzie)

- Tor **moc → CRT (P4, K6)** jest **założeniem**, nie pomiarem. Histereza zabezpieczenia 45 °C (5 °C) jest założona; sam limit 45 °C to wymóg sprzętu.
- Kanał słońca dopasowany na **jednej wiośnie** w jednym miejscu; słońce to dane z reanalizy Open-Meteo, nie pomiar na miejscu. Stała czasowa słońca dla HRT
  (~10 h) jest słabo zidentyfikowana. Zimą przy śniegu wkład słońca byłby przeszacowany (model nie ma albedo), dlatego w symulacji jest tłumiony x0,5 (założenie, po ostrożnej stronie).
- Moc grzania jest zapisana tylko w dwóch oknach po ok. 80 min; poza nimi stan grzania nieznany.
- W zimnych scenariuszach wiele algorytmów pracuje na ~100% mocy, więc różnice widać głównie w karze HRT i w łagodniejszych scenariuszach.
- Algorytmy binarne z dobowym limitem przełączeń (100) mogą go wyczerpać na migotaniu histerezy i zostać „zamrożone” - dotyczy też normy jako punktu odniesienia.
