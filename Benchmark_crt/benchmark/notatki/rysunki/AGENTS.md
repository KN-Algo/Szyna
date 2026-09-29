# AGENTS.md - opis obiektu do wizualizacji (dla innego czatu/agenta)

To jest samodzielny opis - nie wymaga dostępu do repozytorium. Powstał, żeby inny agent AI mógł na jego podstawie
narysować/zwizualizować obiekt bez czytania kodu źródłowego. Stan na **2026-09-28** (po dodaniu kanału nasłonecznienia
i zimowego tłumienia). Jeśli otwierasz to jako kolejną turę - potraktuj ten plik jako aktualny stan prawdy, nadpisujący
wszystko, co wcześniej wiedziałeś o tym modelu.

## 0. Zadanie

Narysuj/zwizualizuj obiekt opisany niżej. Sugerowane widoki (można wybrać część):
1. **Schemat przepływu sygnałów** obiektu fizycznego (sekcja 2) - najważniejszy.
2. **Kanał nasłonecznienia** osobno (sekcja 2, blok P11) - jak z sekund słońca powstaje nagrzewanie szyn, plus zimowe tłumienie.
3. **Architektura kontrolera** (sekcja 3) i **drzewo rodzin algorytmów** (sekcja 4).
4. Wykres odpowiedzi skokowej HRT vs CRT na moc grzania (tabela w sekcji 2).

Konwencje kolorystyczne:
- **Niebieski = HRT** (szyna ogrzewana), **pomarańczowy = CRT** (szyna zimna/nieogrzewana), **żółty = nasłonecznienie/słońce**.
- **Ciągła ramka** = element zmierzony/zdefiniowany; **przerywana ramka** = element ZAŁOŻONY (przyjęty, nie zmierzony).
- Strzałka **moc grzania → CRT** cienka/przerywana (słaby, wolny wpływ, w odróżnieniu od mocnej strzałki moc → HRT).

Przy każdej liczbie w tabelach zaznaczony jest status: **ZMIERZONA** (z realnych danych urządzenia), **ZAŁOŻONA** (przyjęta bez
pomiaru, świadomie po stronie ostrożnej) albo **WYLICZANA** (w trakcie symulacji).

## 1. Kontekst (po co jest ten model)

Symulator porównuje algorytmy sterowania elektrycznym ogrzewaniem rozjazdów kolejowych (norma PKP PLK, instrukcja LET-1):
mają nie dopuścić do zalegania śniegu/lodu na rozjeździe, zużywając przy tym jak najmniej energii. Badany wariant ma
**CRT** (szyna zimna/nieogrzewana) jako **główny wyznacznik** decyzji sterownika - nie HRT (szyna ogrzewana), jak
w klasycznym podejściu. Zależy na **wytopieniu śniegu w całości**, więc CRT ma też pośrednio "mówić" sterownikowi,
ile śniegu jeszcze zostało.

- **HRT** - temperatura szyny ogrzewanej (ma grzałkę, mały obiekt, szybko reaguje).
- **CRT** - temperatura szyny nieogrzewanej (duży obiekt, duża bezwładność cieplna, reaguje bardzo wolno i słabo nawet
  na grzanie sąsiedniej szyny).
- **AT** - temperatura powietrza (wejście pogodowe).

Symulacja: krok **dt = 10 s**, pełny sezon zimowy, **44 lokalizacje** na całym świecie (obie półkule).

## 2. Obiekt fizyczny

### Lista bloków

| ID | Blok | Wejście → wyjście | Parametry | Status |
|---|---|---|---|---|
| E1 | Dane pogodowe (1 plik = 1 lokalizacja, każda ma swoje współrzędne) | → AT, punkt rosy, wiatr, opad, nasłonecznienie [s słońca w przedziale czasu] | interpolowane do dt | dane |
| P1 | G_W: pogoda → szyna (wspólny dla obu szyn) | AT → składowa pogodowa `W` | K=0,987; T1=5146 s (86 min); Tz=1321 s (22 min); bez opóźnienia | ZMIERZONA, przeliczona RAZEM ze słońcem |
| P2 | Linia opóźnienia mocy | moc → `u` | opóźnienie L = 0 | zmierzona |
| P3 | G_H: moc → HRT | u → `H` | K=47,17 °C przy 100% mocy; T1=2462 s (41 min); Tz=204 s (3,4 min) | ZMIERZONA |
| P4 | G_HC: moc → CRT (słaby, wolny kanał) | u → `HC` | K=4,72 °C przy 100% mocy (10% wartości K_H); T1=14 400 s (4 h); bez członu różniczkującego | **ZAŁOŻONA** (nie pomiar) |
| P5 | Sumatory | | `HRT = W + S_h + H`,  `CRT = W + S_c + HC` | wyliczana |
| P6 | Model śniegu i lodu (na bazie SnowClim) | pogoda + HRT → grubość śniegu [mm], lód [mm] | - | model fizyczny |
| P7 | Blok czujników sterownika | → wiersz danych dla kontrolera | patrz sekcja 3.1 | - |
| P8 | Zabezpieczenie termiczne 45°C | HRT → wymusza moc 0% | zatrzask od HRT≥45°C, zwolnienie poniżej 40°C (histereza 5°C ZAŁOŻONA); dotyczy WSZYSTKICH algorytmów oprócz rodziny "fuzzy" (tam tylko monitoring) | wymóg sprzętu + założenie |
| P9 | Bezpiecznik odniesienia do normy | trajektoria referencyjnego algorytmu z normy → korekta mocy | jeśli zalega śnieg i moc normy > moc badanego algorytmu, przejmuje moc normy (`max`) | mechanizm testowy |
| P10 | Metryki wyniku | | energia, przełączenia, IAE/ISE/ITAE, kara bezpieczeństwa (osobno HRT i CRT), czas powyżej 45°C | wyliczana |
| **P11** | **G_S: słońce → szyna** (kanał nasłonecznienia) | wejście słońca (0..1) → `S_h` (do HRT), `S_c` (do CRT) | HRT: K=9,63 °C, T=35 062 s (9,7 h); CRT: K=12,77 °C, T=5651 s (94 min); każdy: pierwszy rząd K/(T·s+1) | ZMIERZONA na jednej wiośnie; stała HRT słabo zidentyfikowana |

### Wejście słońca (blok P11) - jak dokładnie powstaje

```
wejście_słońca(t) = ułamek_słońca(t)  x  sin(wysokość_słońca(t))        zakres 0..1
```

- **ułamek_słońca** = (sekundy słońca zarejestrowane w przedziale) / (długość przedziału w sekundach, zwykle 3600 s dla
  danych godzinowych). **0 = brak słońca** (noc lub pełne zachmurzenie), **1 = pełne słońce przez cały przedział**.
  Wartość jest umieszczana w ŚRODKU przedziału źródłowego i **interpolowana liniowo** do kroku symulacji (10 s).
  Sprawdzone: wejście zbudowane z danych godzinowych daje niemal identyczny wynik jak z danych 15-minutowych
  (różnica RMSE 1,19 vs 1,20 °C) - gęstsze próbkowanie nie jest potrzebne.
- **sin(wysokość słońca)** liczony analitycznie (wzory NOAA) ze współrzędnych geograficznych lokalizacji i czasu UTC -
  nadaje kształt dobowy (słabe słońce o świcie/zmierzchu, mocne w południe). Bez tego czynnika model jest zauważalnie
  gorszy (RMSE CRT 1,9 °C zamiast 1,2 °C przy pełnym modelu).
- Iloczyn = 1,0 tylko przy słońcu dokładnie w zenicie i czystym niebie.
- **Kontroler NIE widzi słońca bezpośrednio** (prawdziwe urządzenie go nie mierzy) - odczuwa je pośrednio, przez
  zmierzone wartości CRT/HRT.

**Zimowe tłumienie (WAŻNE założenie):** parametry P11 zidentyfikowano na wiosennych danych, gdzie nie ma śniegu.
Zimą śnieg na szynie odbija większość promieniowania słonecznego (albedo), a model tego zjawiska nie ma wprost.
Dlatego w symulacji zimowej **cały wkład słońca (`S_h` i `S_c`) jest mnożony przez współczynnik 0,5** - świadome
niedoszacowanie ("błąd na minus", czyli szyny wychodzą chłodniejsze niż w rzeczywistości, nigdy cieplejsze) zamiast
przeszacowania. Współczynnik 1,0 = brak tłumienia (tryb "czysto wiosenny", używany tylko przy dopasowaniu modelu do
danych referencyjnych).

### Kolejność zdarzeń w jednym kroku symulacji (10 s)
1. Odczyt pogody → składowa pogodowa `W` (P1) i składowe słoneczne `S_h`, `S_c` (P11, z uwzględnieniem zimowego tłumienia).
2. Wiersz czujników (P7) trafia do kontrolera → kontroler zwraca moc żądaną (0-100%).
3. Bezpiecznik odniesienia do normy (P9) może podnieść moc, jeśli zalega śnieg.
4. Zabezpieczenie termiczne 45°C (P8) działa jako OSTATNIE - może wyzerować moc.
5. Moc (po korektach) → opóźnienie (P2) → filtry G_H (P3) i G_HC (P4) → nowe wartości HRT i CRT (sumatory P5).
6. Model śniegu i lodu (P6) aktualizuje się na podstawie aktualnego HRT.
7. Naliczenie metryk (P10).

### Schemat (do narysowania, tekstowy szkic)

```
 E1 Pogoda (CSV) ──AT──► G_W(s) ────────────────────┬───────────────────────┐
   │  K=0,987 T1=86 min Tz=22 min                   │ W                     │ W
   │                                                ▼                       ▼
   └─ sekundy słońca ─► ułamek × sin(wys. słońca) ─► P11 G_S(s)          ┌─────┐
       (x zimowe tłumienie 0,5)                     │ S_h ─────────────► │  +  │─► HRT
   moc żądana ─► bezpiecznik ─► zabezp. 45°C ─► u ──►│ S_c ─────┐         └─────┘
   (kontroler)   normy (max)    (zeruje moc)         │          ▼            ▲ H
                                                     │       ┌─────┐   G_H(s) K=47,2 T1=41 min
                                                     │       │  +  │─► CRT     ▲
                                                     │       └─────┘           │
                                                     │          ▲ HC    G_HC(s) K=4,72 T1=4 h (ZAŁOŻONA)
   HRT + pogoda ─► MODEL ŚNIEGU I LODU ─► śnieg [mm], lód [mm]
```

### Odpowiedź na pełną moc grzania od zera (bez pogody i bez słońca)

| po czasie | wkład w HRT | wkład w CRT |
|---|---|---|
| 32 min | 27,3 °C | 0,6 °C |
| 41 min (T1 HRT) | 31,3 °C | 0,7 °C |
| 1 h | 37,1 °C | 1,0 °C |
| 4 h (T1 CRT) | 47,0 °C | 3,0 °C |
| 12 h | 47,2 °C | 4,5 °C |
| stan ustalony | 47,2 °C | 4,7 °C |

Przy samym włączeniu mocy HRT skacze natychmiast o ok. 3,9 °C (człon różniczkujący modelu). Sedno wizualne: **HRT
reaguje szybko i mocno, CRT prawie wcale i bardzo wolno** - na wykresie warto użyć jednej wspólnej osi °C (żeby
widać było skalę różnicy) plus osobnego, powiększonego panelu tylko dla CRT.

Stan ustalony samej pogody (bez słońca, bez grzania): szyna ≈ 0,99 × AT. Przy pełnym słońcu w zenicie dochodzi do
tego dodatkowo ok. +12,8 °C na CRT i +9,6 °C na HRT (przed zimowym tłumieniem x0,5).

## 3. Kontroler

Każdy algorytm sterujący dziedziczy wspólny "rdzeń kontrolera" i widzi WYŁĄCZNIE to, co dostarcza blok czujników -
nie ma dostępu do prawdziwej fizyki symulacji (np. prawdziwej grubości śniegu czy nasłonecznienia).

### 3.1 Co widzi kontroler (blok czujników, P7)
`CRT` (prawdziwe, czyli pogoda + słońce + bardzo słaby wkład grzania z poprzedniego kroku), `HRT` (z poprzedniego
kroku), `AT`, wilgotność względna, opad, intensywność opadu śniegu, punkt rosy, wiatr. **Nie widzi** nasłonecznienia
ani prawdziwej grubości śniegu (musi ją sam oszacować, patrz K7 niżej).

### 3.2 Obiekty wspólnego rdzenia
| ID | Obiekt | Co robi |
|---|---|---|
| K1 | Pamięć czujników | średnie kroczące w binach 15-minutowych (bufor 36 binów = 9 h) |
| K2 | Prognoza temperatury powietrza | filtr Kalmana (poziom + trend), horyzont 2 h = 8 kroków po 15 min |
| K3 | Prognoza CRT (Kalman "fizyczny") | model pogoda→CRT (te same stałe co P1, ale bez słońca) korygowany na bieżąco zmierzonym CRT |
| K4 | Autotest przy starcie | skok mocy 0→100%, dopasowanie modelu drugiego rzędu z opóźnieniem (SOPDT); test kończy się przy HRT=38°C, ustabilizowaniu odpowiedzi, albo po 4 h |
| K5 | Cyfrowy bliźniak HRT | model z autotestu (K4); prognozuje zanikanie ciepła po wyłączeniu grzania |
| K6 | Cyfrowy bliźniak CRT | model G_HC (te same stałe co P4, **założone**, gotowy od pierwszego kroku, bo autotest by go nie wykrył) |
| K7 | Estymator grubości śniegu | bilans własny: przyrost = intensywność opadu śniegu; ubytek = 0,001 mm/s na °C x max(**CRT**, 0) - topnienie liczone z CRT |
| K8 | Prognoza opadu | intensywność 0-3, horyzont 2 h |

### 3.3 Wyznaczanie celu (funkcja ryzyka - współdzielona przez wiele rodzin algorytmów)
Kaskada priorytetów, pierwszy spełniony wygrywa:
1. **Marznący deszcz** → grzej bezwarunkowo, cel 3 °C.
2. **Opad śniegu lub zalegający śnieg > 5 mm** → grzej (cel 2 °C + kara rosnąca z grubością śniegu, max +0,88 °C),
   chyba że prognoza CRT pokazuje naturalne ocieplenie w ~30 min przy cienkiej pokrywie - wtedy czekaj.
   Wariant 2b: jeszcze nie pada, ale prognoza opadu pokazuje nadchodzący front w ~30 min i temperatura jest blisko
   zera → grzanie wyprzedzające.
3. **Ochrona przed spadkiem CRT poniżej −10 °C**: gdy CRT ≤ −8 °C albo prognoza 2h ≤ −12 °C → cel −5 °C.
4. **Suchy mróz** (AT ≤ −5 °C) → cel −5 °C.
5. W innym razie: brak zagrożenia, nie grzej.

Progi celu (2 °C, 3 °C, −5 °C) pochodzą z kolumny "szyna nieogrzewana" tabel normy LET-1. Twardy, bezwzględny dolny
limit bezpieczeństwa szyny to −10 °C.

### 3.4 Rodzaje regulatorów (jak cel zamienia się na moc)
| Typ regulatora | Zasada działania |
|---|---|
| Histereza binarna | włącz gdy CRT < cel, wyłącz gdy CRT ≥ cel + 2 °C; min. odstęp między przełączeniami 60 s, limit 100 przełączeń/dobę |
| PI ciągły (0-100%) | błąd liczony względem CRT, nastawy metodą SIMC z autotestu, z zabezpieczeniem przed nasyceniem całki |
| Kaskada dwóch PI | pętla zewnętrzna (wolna): błąd CRT → zadana temperatura HRT; pętla wewnętrzna (szybka): błąd HRT → moc |
| PI binarny z histerezą 2 °C | błąd CRT + całka (ograniczona ±2 °C) → przekaźnik: załącz przy +1 °C błędu, wyłącz przy −1 °C |
| ADRC / LADRC / NADRC | obserwator stanu rozszerzonego zamiast klasycznej całki |
| MPC (regulator predykcyjny) | optymalizacja mocy na 8 blokach po 15 min naprzód; koszt = energia + odchylenie od celu + zmiany mocy + duża kara za przekroczenie 45°C |
| Fuzzy logic (Sugeno) | trzy warianty: ciągły, binarny, PWM co 60 s |
| Uczenie z kar | PI do progów normy + współczynnik korygowany raz na dobę na podstawie zsumowanych kar |
| Automat/histereza z normy | bezpośrednio progi normy LET-1 (załącz/wyłącz), także wariant górski z podniesionym progiem |

## 4. Rodziny algorytmów (52 algorytmy w sumie)

```
Algorytmy
├─ Wg normy LET-1: automat/histereza (zwykły + górski), automat referencyjny, PI do progów normy, fuzzy do progów normy
├─ Funkcja ryzyka (pamięć + Kalman + bliźniaki + opad, CRT jako wyznacznik):
│    ├─ binarna (zwykła + z prognozą opadu)
│    ├─ PI ciągły (zwykły + z prognozą opadu + z auto-strojeniem progów)
│    ├─ PI binarny z histerezą 2°C
│    ├─ kaskada dwóch PI (zwykła + z prognozą opadu)
│    └─ ADRC liniowy i nieliniowy
├─ MPC: ciągłe / binarne x {liniowy, z prognozą pogody, miękkie ograniczenia} + warianty "zabezpieczone"
├─ Fuzzy logic (22 warianty): "surowe" wokół stałego celu, "z ryzykiem" (+ opad, adaptacyjny, agresywny), specjalne warianty CRT
├─ Uczenie z kar (5 wariantów: bazowy, temperaturowy, opadowy, z bliźniakiem, z pełnym ryzykiem)
└─ Z literatury naukowej: histereza z pamięcią punktu rosy, predykcja z prostym wygładzaniem
```
Uwaga: zabezpieczenie termiczne 45°C u algorytmów "fuzzy" tylko monitoruje, nie wymusza zerowania mocy.

## 5. Zgodność modelu z realnymi danymi

Model dopasowano do 21 dni realnych pomiarów z urządzenia (Wrocław, kwiecień-maj, wiosna, jedna lokalizacja).
RMSE pomiar vs model (im mniej, tym lepiej):

| Okres | CRT | HRT |
|---|---|---|
| całe 21 dni | 1,22 °C (poprzednio, bez słońca: 2,23 °C) | 1,15 °C (poprzednio: 2,72 °C) |
| jeden tydzień | 1,39 °C (było 2,22) | 1,07 °C (było 2,01) |
| jedna doba | 1,54 °C (było 2,54) | 0,78 °C (było 2,37) |

Dodanie kanału słonecznego wymagało też przeliczenia toru pogodowego P1 - bez tego stary model "wchłaniał" średnie
nagrzewanie słoneczne w swoim wzmocnieniu, co maskowało realny efekt słońca.

## 6. Metryki wyjściowe symulacji

Energia [kWh], liczba przełączeń grzania, IAE/ISE/ITAE (jakość śledzenia celu), **kara bezpieczeństwa** (osobno dla
HRT i CRT: zalegający śnieg powyżej 5 mm + marznący deszcz przy szynie poniżej 2 °C + spadek poniżej −10 °C),
maksymalna/minimalna temperatura HRT i CRT, czas spędzony powyżej 45°C. Skala: 44 lokalizacje × 52 algorytmy ≈
2300 kombinacji, liczone równolegle.

## 7. Ograniczenia i uczciwe zastrzeżenia (proszę ująć w legendzie/opisie rysunku)

- Kanał **moc → CRT (blok P4/K6)** jest **założeniem**, nie pomiarem - realny efekt grzania jednej szyny na drugą,
  sąsiednią, nieogrzewaną szynę nie został jednoznacznie zmierzony.
- Kanał **słoneczny (P11)** dopasowano na **jednej wiośnie**, w **jednym miejscu** - nasłonecznienie pochodzi z danych
  reanalizy pogodowej, nie z pomiaru na miejscu. Stała czasowa słońca dla HRT (~10 h) jest słabo zidentyfikowana.
- **Zimą wkład słońca jest celowo tłumiony o połowę** (współczynnik 0,5) - to świadome, ostrożne założenie (błąd "na
  minus"), bo model nie uwzględnia odbicia promieniowania od śniegu (albedo).
- Histereza zwolnienia zabezpieczenia termicznego 45°C (5 °C) jest założona - sam limit 45°C to wymóg sprzętu.
- Moc grzania w danych referencyjnych jest zapisana tylko w dwóch krótkich oknach (ok. 80 min każde); poza nimi stan
  grzania jest nieznany.
- W bardzo zimnych scenariuszach wiele algorytmów pracuje niemal cały czas na 100% mocy - różnice między nimi widać
  głównie w karze bezpieczeństwa HRT i w łagodniejszych scenariuszach pogodowych.
