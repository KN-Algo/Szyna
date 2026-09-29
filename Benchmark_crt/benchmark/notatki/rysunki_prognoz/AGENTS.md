# AGENTS.md - prognoza temperatury i opadów, opis do wizualizacji (dla innego czatu/agenta)

Samodzielny opis - nie wymaga dostępu do repozytorium. Dotyczy WYŁĄCZNIE dwóch podsystemów prognozy
(czym innym niż fizyka obiektu, opisana w `notatki/rysunki/AGENTS.md` - jeśli chcesz zwizualizować oba
tematy razem, to dwa osobne, uzupełniające się dokumenty). Stan na 2026-09-29.

## 0. Zadanie

Zwizualizuj dwa NIEZALEŻNE podsystemy prognozy, którymi posługuje się kontroler (żaden z nich nie ma
dostępu do przyszłości - obie prognozy budowane są WYŁĄCZNIE z historii odczytów czujników):
1. **Prognoza temperatury** (sekcja 1) - trzy warianty tego samego filtru Kalmana, różniące się modelem
   procesu: czysto statystyczny (poziom+trend) dla powietrza i dla CRT, oraz "fizyczny" (model procesu =
   znana transmitancja pogodowa) dla CRT - ten ostatni jest tym używanym w praktyce do decyzji.
2. **Prognoza opadu** (sekcja 2) - klasyfikator intensywności opadu zimowego (0-3) na najbliższe 2h,
   zbudowany na prognozowanej temperaturze z punktu 1 + punkcie rosy + wietrze.

Sugerowane widoki - patrz sekcja 4. Konwencje kolorystyczne: **niebieski = AT** (powietrze),
**pomarańczowy = CRT**, **żółty/bursztynowy = opad/intensywność**, **szary = niepewność/pasmo prognozy**.
Linia **ciągła = pomiar/prawda**, **przerywana = prognoza**.

## 1. Prognoza temperatury (filtr Kalmana, horyzont 2h)

Wspólne dla obu "gałęzi" (AT i CRT) parametry siatki:
- **Horyzont: 8 kroków co 15 min = 2 godziny.**
- Kontroler NIE trzyma surowej historii - utrzymuje **bufor kroczący średnich 15-minutowych**, max
  **36 binów (9 h)** wstecz. Aktualny, jeszcze niedomknięty bin liczy się ze swojej dotychczasowej średniej.
- Prognoza jest **cache'owana i odświeżana nie częściej niż raz na 300 s (5 min)** - obiekt ma stałe
  czasowe rzędu dziesiątek minut, więc częstsze przeliczanie nic by nie dało, a kosztowałoby dużo (koszt
  liczony jest na historię przy każdym przeliczeniu).

### 1.1 Wariant A i B: generyczny filtr Kalmana "poziom + trend" (dla AT i dla CRT)

Klasyczny filtr Kalmana ze stanem 2-wymiarowym: **poziom** (bieżąca wartość) i **trend** (tempo zmian).
Model procesu: `poziom(t+1) = poziom(t) + trend(t)`, `trend(t+1) = trend(t)` (stały trend + szum procesu).
Parametry: **wariancja procesu = 0,05**, **wariancja pomiaru = 0,25** (te same dla obu gałęzi).

- **Wariant A** (`temperature_prediction`): wejście = historia **AT** (powietrze). Podstawowa prognoza
  pogody, używana przez WSZYSTKIE algorytmy z pamięcią (nie tylko funkcję ryzyka) oraz jako **wejście**
  do prognozy opadu (sekcja 2).
- **Wariant B** (`rail_temperature_prediction`): TEN SAM silnik Kalmana, ale wejście = historia **CRT**
  zamiast AT. Istnieje w kodzie, ale w praktyce **NIE jest używany** do decyzji sterowania - zastąpiony
  przez wariant C (dokładniejszy), zostawiony jako prostszy punkt odniesienia/do porównań.

Ten silnik **ignoruje znaną fizykę obiektu** - tylko ekstrapoluje poziom i trend z ostatnich punktów.
Dobry na krótki horyzont, na dłuższym (2h) rozjeżdża się bez ograniczenia, jeśli trend się zmieni.

### 1.2 Wariant C: filtr Kalmana z modelem procesu = ZNANA FIZYKA (używany w praktyce dla CRT)

`crt_transmittance_prediction()` - to jest wariant faktycznie napędzający decyzje sterownika
(`_evaluate_risk_setpoint`). Różnica względem wariantu B: model procesu w kroku PREDYKCJI filtru to nie
abstrakcyjny "poziom+trend", tylko **prawdziwa, zidentyfikowana transmitancja pogoda→CRT** (ta sama
transmitancja G_W co w fizyce obiektu - patrz `notatki/rysunki/AGENTS.md`, blok P1: K=0,987, T1=86 min,
Tz=22 min). Krok KOREKTY filtru dalej korzysta ze zmierzonego CRT, dokładnie jak zwykły Kalman.

**Dlaczego to lepsze niż A/B osobno (uzasadnienie z kodu):**
- Sama fizyka bez korekty pomiarem (otwarta pętla) - błąd modelu rośnie bez ograniczenia.
- Sam generyczny Kalman (wariant B) - ignoruje znaną bezwładność obiektu (stałą czasową ~86 min),
  ekstrapoluje tylko trend, rozjeżdża się na dłuższym horyzoncie.
- Kalman z fizyką jako modelem procesu łączy oba: PRZEWIDUJE fizyką (zna bezwładność całego obiektu),
  POPRAWIA pomiarem CRT (odporny na błąd modelu/zmiany słońca, których model procesu nie zna wprost).

**Mechanika (dwa etapy):**
1. **Dogonienie stanu bieżącego**: filtr Kalmana (predykcja+korekta) przechodzi przez NIEDAWNĄ historię
   (bufor kroczący, do 9h AT+CRT), krok po kroku, żeby dojść do wiarygodnego stanu bieżącego skorygowanego
   pomiarem - nie zaczyna "na zimno".
2. **Prognoza w przód (2h)**: z tego stanu, czystą fizyką (bez korekty - przyszłego CRT z definicji nie
   znamy), napędzaną prognozą AT z wariantu A (bo przyszłego powietrza też nie znamy, więc i tu jest to
   prognoza, nie pomiar).
- Współczynniki filtru: **Q=0,01** (niepewność modelu), **R=0,01** (niepewność pomiaru CRT) - dobrane
  metodą grid search minimalizującego RMSE prognozy 2h na realnych danych z Wrocławia.
- Model bez opóźnienia transportowego (transmitancja pogoda→CRT go nie ma) i **bez wkładu grzania** -
  to WYŁĄCZNIE prognoza pogodowej części CRT. Wkład grzania dochodzi OSOBNO, z innego modułu (cyfrowy
  bliźniak grzania → CRT, "zanikanie ciepła"), dodawany do tej prognozy w miejscu, gdzie funkcja ryzyka
  wyznacza cel - dwa oddzielne, sumowane ze sobą źródła prognozy.

**Zmierzona dokładność (realny log z Wrocławia, 19 dni, dni testu skokowego wykluczone), RMSE uśrednione
po całym horyzoncie 2h:**

| Metoda | Co robi | RMSE 2h |
|---|---|---|
| Generyczny Kalman (wariant B) | tylko statystyka, nie zna fizyki | 2,52°C |
| Sama fizyka, otwarta pętla | zna transmitancję, IGNORUJE pomiar | 2,24°C |
| **Kalman z fizyką (wariant C)** | zna transmitancję I koryguje pomiarem | **1,77°C** |

Wariant C wygrywa na każdym horyzoncie od ~30 min wzwyż (przy 120 min: 2,17°C vs 4,14°C dla generycznego
Kalmana - ten drugi rozjeżdża się bez ograniczenia). Przy 15 min generyczny Kalman jest odrobinę lepszy
(0,63°C vs 0,80°C) - na bardzo krótkim horyzoncie sama ekstrapolacja trendu wystarcza. **Dokładność wariantu
C NIE pogarsza się w okresach z nadchodzącym opadem/śniegiem** (sprawdzone osobno) - wychodzi tam nawet
nieco lepiej niż średnio.

## 2. Prognoza opadu (klasyfikator intensywności 0-3, horyzont 2h)

Moduł `przewidywanie_opadow.py`, wołany jako `_prognoza_intensywnosci_opadu` - zwraca **8 liczb (0-3)**,
jedną na każdy z 8 kroków prognozy temperatury z sekcji 1 (wariant A, AT).

### 2.1 Ważne ograniczenie architektury: to NIE jest detektor "znikąd"

Prognoza działa WYŁĄCZNIE, gdy w NIEDAWNEJ historii (`persistence_steps=1`, czyli ostatni krok) opad już
faktycznie wystąpił (suma > 0,02 mm - próg odcinający szum czujnika). **Jeśli teraz nie pada, prognoza
zawsze zwraca same zera** - moduł NIE przewiduje nadejścia opadu z zupełnie suchego stanu, tylko
KLASYFIKUJE, jak rozwinie się/zakończy front, który JUŻ trwa. To świadome uproszczenie (patrz nagłówek
kodu), nie błąd - ale ważne do zaznaczenia na wizualizacji (np. szara strefa "brak danych o froncie" przed
pierwszym opadem).

**POPRAWIONY BŁĄD SKALI (2026-09-29, znaleziony przy budowie tej wizualizacji):** moduł oczekuje opadu w
mm, w skali NATYWNEGO kroku danych źródłowych (np. 0,3-0,5 mm/h). Symulator jednak przekazuje kontrolerowi
opad w **mm na SEKUNDĘ** (`symulacja_fizyczna.wczytaj_pogode_1s` dzieli sumę opadu przez krok źródłowy w
sekundach) - rząd wielkości 0,0001-0,0005, 40-200x mniejszy niż próg bramki 0,02. Bez poprawki bramka
"czy pada" NIGDY się nie otwierała w żadnym realnym przebiegu (zmierzone: 0 aktywacji na 43201 krokach
5-dniowego okna z realnym opadem) - cała prognoza opadu (priorytet 2b, "front ustępuje") była martwym
kodem. Naprawione w `funkcja_ryzyka_wspolne._prognoza_intensywnosci_opadu` - wartość mnożona przez
`STEP_SECONDS` (900 s) przed przekazaniem do modułu, żeby dostał liczbę w skali, na jaką faktycznie
reaguje. Po poprawce: priorytet 2b uruchamia się realnie (zmierzone: 6990/43201 kroków w tym samym oknie).
Rysunki w tym folderze są już WYGENEROWANE PO POPRAWCE.

### 2.2 Jak liczona jest intensywność każdego z 8 kroków

Dla każdego z 8 przyszłych kroków (z prognozowaną temperaturą `t_pred` z Kalmana wariantu A):
1. **Wilgotność względna** z temperatury i punktu rosy (BIEŻĄCEGO, nie prognozowanego - wzór Magnusa,
   stałe a=17,625, b=243,04): `RH = 100 · exp(α(punkt_rosy) − α(t_pred))`.
2. **Temperatura mokrego termometru Tw** - empiryczny wzór (Stull 2011) z `t_pred` i `RH`.
3. **Rozstęp** `spread = t_pred − punkt_rosy` (bieżący punkt rosy, nie prognozowany).
4. Klasyfikacja:
   - Jeśli `Tw ≤ 0,1°C` LUB `t_pred ≤ −0,5°C` → **poziom 1** (na tyle zimno, że pada śnieg/marznąca mżawka).
   - Jeśli dodatkowo `spread ≤ 0,6°C` (powietrze blisko nasycenia) → **poziom 2**.
   - Jeśli poziom 2 ORAZ wiatr ≥ 6 m/s → **poziom 3** (zamieć/nawałnica).
   - W innym razie (za ciepło) → **poziom 0**.

### 2.3 Definicje poziomów (do legendy wizualizacji)

| Poziom | Nazwa | Próg (dla danych rzeczywistych, do walidacji) |
|---|---|---|
| 0 | Brak opadu | 0,00 mm/15 min |
| 1 | Słaby opad | 0,01-0,35 mm/15 min (lekki śnieg/mżawka marznąca) |
| 2 | Średni opad | 0,36-1,00 mm/15 min (umiarkowany śnieg/deszcz marznący) |
| 3 | Mocny opad/nawałnica | > 1,00 mm/15 min LUB średni opad przy wietrze > 6 m/s |

(Progi walidacyjne 0,35/1,00 mm i próg wiatru 6 m/s są takie same jak w samym klasyfikatorze - świadomie
spójne, żeby ocena "trafień" mierzyła jakość prognozy, nie rozjazd definicji.)

### 2.4 Jak to jest używane przez kontroler (dwa przeciwne zastosowania tej samej prognozy)

- **Grzanie wyprzedzające** (WSZYSTKIE algorytmy funkcji ryzyka, priorytet 2b): jeśli jeszcze nie pada, ale
  AT lub CRT jest blisko zera (≤2°C) i prognoza pokazuje intensywność > 0 w najbliższych **2 krokach
  (~30 min)**, kontroler zaczyna grzać, ZANIM opad faktycznie się zacznie.
- **Ucieczka z grzania** (tylko warianty `*_opad`): gdy już pada, ale zalegająca pokrywa jest cienka
  (≤10 mm) i prognoza pokazuje **koniec** frontu w najbliższych 2 krokach (żadna z najbliższych 2 wartości
  > 0), kontroler NIE grzeje na zapas - ufa, że cienka pokrywa i tak niedługo zniknie sama.

### 2.5 Zmierzona skuteczność (walidacja na wszystkich 44 plikach pogodowych, oryginalny silnik)

- **80,1%** globalna skuteczność osłony (ile godzin realnego opadu było pod "parasolem" trafnej prognozy).
- **81,3%** trafność alarmu (ile z wygenerowanych alarmów grzania faktycznie pokrywało się z opadem).
- Duży rozrzut między lokalizacjami - np. dla Wrocławia (dane 2024) trafność spada do ok. 62%.

## 3. Schemat przepływu (do narysowania)

```
                    ┌─────────────────────────────┐
  historia AT ─────►│ K-A: Kalman poziom+trend     │──► prognoza AT (8x15min, 2h)
  (bufor 9h,        └─────────────────────────────┘         │
   36 binów 15-min)                                          │ (wejście "przyszła temperatura")
                    ┌─────────────────────────────┐          │
  historia CRT ────►│ K-C: Kalman + FIZYKA         │◄─────────┘
  (ten sam bufor)   │  (model procesu = G_W,       │
                    │   korekta = pomiar CRT)       │──► prognoza CRT (8x15min, 2h)  [UŻYWANA]
                    └─────────────────────────────┘         │
                                                              │ + osobno: bliźniak grzania (zanikanie ciepła)
                                                              ▼
                                                    forecast_crt = prognoza CRT + resztkowe ciepło

  ostatni opad (>0,02mm?) ──► BRAMKA "front aktywny" ──NIE──► zera (8x 0)
         │ TAK
         ▼
  dla każdego z 8 kroków prognozy AT:
     RH(t_pred, punkt_rosy) → Tw(t_pred, RH) → próg zimna? → spread≤0,6? → wiatr≥6? → poziom 0-3
                                                                                            │
                                                                                            ▼
                                                                         prognoza opadu (8x poziom 0-3, 2h)
```

## 4. Propozycje widoków

1. **Schemat przepływu** (sekcja 3) - dwa niezależne tory (temperatura, opad), pokazujące że opad
   KORZYSTA z prognozy temperatury jako wejścia.
2. **Porównanie 3 metod prognozy CRT** (sekcja 1.2, tabela RMSE) - słupki albo krzywa RMSE(horyzont) dla
   3 metod, pokazująca że przewaga fizyki+Kalmana rośnie z horyzontem.
3. **Przykładowy przebieg** (najlepszy pojedynczy obrazek): oś czasu kilku-kilkunastu godzin, linia ciągła
   = prawdziwe AT i CRT, w kilku chwilach "wachlarz" 8 punktów prognozy w przód (przerywana linia/kropki),
   żeby było widać, jak prognoza się przesuwa i koryguje w miarę napływu nowych pomiarów.
4. **Klasyfikator opadu jako drzewo decyzyjne** (sekcja 2.2) - Tw≤0,1 lub t≤−0,5 → spread≤0,6 → wiatr≥6.
5. **Oś czasu z realnym epizodem opadu**: opad rzeczywisty [mm], temperatura, prognozowana intensywność
   (8 kolorowych "smug" w przód z każdego kroku) nałożona na rzeczywisty przebieg - pokazuje "grzanie
   wyprzedzające" (priorytet 2b) i "ucieczkę z grzania" (`*_opad`) w akcji.

### Gotowe rysunki (wersja referencyjna, wygenerowane z realnych danych)
`notatki/rysunki_prognoz/05_prognoza_temperatury.png`, `06_prognoza_opadow.png` (generator
`generuj_wizualizacje_prognoz.py` w tym samym folderze).

## 5. Ograniczenia i zastrzeżenia (do legendy/opisu)

- Prognoza opadu **nie przewiduje frontu z zupełnie suchego stanu** - tylko klasyfikuje/przedłuża front
  już trwający (patrz 2.1). To świadome uproszczenie modelu, nie usterka.
- Wzory RH i temperatury mokrego termometru to standardowe przybliżenia empiryczne (Magnus, Stull), nie
  pomiar bezpośredni - punkt rosy i wiatr używane w klasyfikacji to wartości BIEŻĄCE (bez własnej prognozy),
  tylko temperatura jest prognozowana.
- Walidacja dokładności (80,1%/81,3%) pochodzi z oryginalnego (nie-CRT) benchmarku - sam moduł
  `przewidywanie_opadow.py` jest identyczny w obu wersjach projektu, więc liczby powinny się przenosić,
  ale nie zostały ponownie zmierzone po dzisiejszych zmianach fizyki (kanał słoneczny, tłumienie zimowe).
- Filtr Kalmana z fizyką (wariant C) prognozuje WYŁĄCZNIE pogodową część CRT - wkład grzania (słaby/wolny,
  patrz `notatki/rysunki/AGENTS.md`) jest prognozowany OSOBNYM modułem (cyfrowy bliźniak grzania) i
  sumowany dopiero w miejscu, gdzie funkcja ryzyka wyznacza cel sterowania.
- Współczynniki Kalmana (Q=0,01, R=0,01 dla wariantu C) i walidacja RMSE pochodzą z JEDNEJ lokalizacji
  (Wrocław, ta sama wiosna co reszta identyfikacji fizyki) - nie zweryfikowane osobno na pozostałych 43.
