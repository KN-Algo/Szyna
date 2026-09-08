# AGENTS.md — Szyna_2 / Benchmark

Ten plik ma być NA BIEŻĄCO aktualizowany przy każdej istotnej zmianie w projekcie,
żeby dowolny agent (Claude albo inny) wchodzący w projekt na nowo wiedział, co
już jest zrobione, co jest w trakcie i jakie decyzje projektowe już zapadły
(żeby ich nie kwestionować/nie robić od nowa bez potrzeby).

## Cel projektu

Benchmark porównawczy algorytmów sterowania elektrycznym ogrzewaniem rozjazdów
kolejowych (ochrona przed oblodzeniem/zaleganiem śniegu) dla PKP PLK, wg normy
Iet-1 "Instrukcja eksploatacji i utrzymania urządzeń elektrycznego ogrzewania
rozjazdów". Cel: znaleźć algorytm minimalizujący zużycie energii przy
zachowaniu wymaganego poziomu bezpieczeństwa (norma jako twardy wyznacznik).

## Architektura (skrót)

- `symulacja_fizyczna.py` — wspólny rdzeń fizyki: transmitancje pogoda/grzanie
  (zidentyfikowane SOPDT z danych pomiarowych), fizyczny model śniegu/lodu
  (`Model_sniegu_SnowClim/`, pochodna pySnowClim). Jedna implementacja fizyki
  używana przez WSZYSTKIE skrypty testujące, żeby symulacje różniły się
  wyłącznie algorytmem decyzyjnym.
- `Algorytmy/` — każdy algorytm w osobnym pliku (nawigacja). Wspólna
  infrastruktura:
  - `rdzen_kontrolera.py` — `KontrolerBazowy`: pamięć czujników + prognoza
    Kalmana (AT/CRT, 2h horyzont/15min krok) + autotest (identyfikacja SOPDT
    skokiem grzania) + "cyfrowy bliźniak" grzałki zbudowany z wyniku autotestu
    (prognozuje fizycznie zanikające ciepło z już wydanych komend mocy) +
    licznik RZECZYWISTYCH FLOPs (`_dodaj_flopy`, patrz niżej).
  - `funkcja_ryzyka_wspolne.py` — `KontrolerRyzykaBazowy` (setpoint z pamięci +
    prognozy Kalmana + kary za zalegający śnieg) i `KontrolerRyzykaOpadBazowy`
    (jw. + prognoza OPADU z `przewidywanie_opadow.py` jako dodatkowy warunek
    zwalniający z grzania przy cienkiej, zanikającej pokrywie).
  - `funkcja_normy_wspolne.py` — setpoint z progów normy LET-1 (bez
    pamięci/prognozy, choć DZIEDZICZY KontrolerBazowy więc i tak akumuluje
    historię czujników — patrz "Rzeczy do pamiętania" niżej).
  - `silniki_fuzzy.py` — rdzenie wnioskowania rozmytego Sugeno: FL1 (6 reguł,
    ciągły z miękkim obcięciem), FL2 (jak FL1, binaryzowany), FL2v2 (7 reguł,
    binaryzowany, próg "lodowato" zależny od opadu), FL3 (jak FL1, PWM 60s).
  - `rejestr_algorytmow.py` — mapa nazwa→(moduł, klasa, metoda) + metadane
    opisowe (`opis`/`typ`/`cel`/`adaptacyjny`) + metadane złożoności
    (`zlozonosc_czasowa`/`flops_na_krok`/`zlozonosc_pamieciowa`/
    `pamiec_przyblizona_mb` — szacunki ANALITYCZNE, patrz sekcja FLOPs niżej).
- `przewidywanie_opadow.py` — prognoza intensywności opadu (0-3, horyzont 2h,
  model wilgotności względnej/mokrego termometru na prognozie AT z Kalmana).
- Skrypty testujące (wszystkie przez `rejestr_algorytmow.ALGORYTMY`, żeby nie
  rozjeżdżały się listą dostępnych algorytmów):
  - `test_jeden_algorytm_jedna_lokalizacja.py` — GUI, jeden algorytm.
  - `test_wszystkie_algorytmy_jedna_lokalizacja.py` / `..._wszystkie_lokalizacje.py`
    — sekwencyjne, z wykresami PNG.
  - `test_wszystkie_rownolegle.py` — RÓWNOLEGŁA wersja (ProcessPoolExecutor),
    do uruchamiania na wielu rdzeniach/superkomputerze. BEZ wykresów PNG
    (świadome uproszczenie, dane są w zapisanych CSV). Autodetekcja liczby
    rdzeni: zmienne SLURM/PBS/LSF, potem `os.sched_getaffinity`, potem
    `os.cpu_count()`. Sterowanie przez zmienne środowiskowe `SZYNA_*` (patrz
    nagłówek pliku) — KONIECZNE, bo przy `ProcessPoolExecutor` w trybie
    `spawn` (Windows) i przy uruchamianiu przez SLURM procesy potomne na nowo
    importują moduł, więc zwykłe nadpisanie atrybutu w procesie głównym nie
    dotrze do nich.
  - `generuj_excel_podsumowanie.py` — buduje `Podsumowanie_wynikow.xlsx`
    (zakładki: Dane, Podsumowanie_algorytmy, Podsumowanie_lokalizacje,
    Opisy_algorytmow, Zlozonosc_obliczeniowa, Wnioski). Wywoływane
    automatycznie na końcu `test_wszystkie_rownolegle.py`.

## Zbiór algorytmów (37 sztuk, w `rejestr_algorytmow.ALGORYTMY`)

Rodziny: automat/histereza wg normy (2, + wariant górski `compute_control_gorski`
= 3), funkcja ryzyka binarna/PID/LADRC/NADRC (4, patrz `notatki/algorytmy/adrc.md`)
+ ich warianty `_opad` (2 — binarna/PID), PID/fuzzy do progów normy (5), fuzzy
logic "surowy" wokół stałego celu (4), fuzzy + funkcja ryzyka (4) + ich warianty
`_opad` (4), uczenie adaptacyjne z kar `nauka_kary*` (5 — bazowy + temp/opad/
bliźniak/ryzyko), MPC (3 — `mpc_liniowy`/`mpc_prognoza_pogody`/
`mpc_miekkie_ograniczenia`, patrz sekcja "MPC (regulator predykcyjny)" niżej),
inspirowane literaturą (2 — `histereza_pamiec_rosy`/`predykcja_wygladzanie_prosta`,
Chiaradonna i in. 2021). Dokładne opisy typu/celu/adaptacyjności — patrz zakładka "Opisy_algorytmow" w
Excelu albo bezpośrednio `rejestr_algorytmow.py`. Opis DZIAŁANIA każdego
algorytmu z osobna (bardziej szczegółowy niż jednolinijkowy `opis` w
rejestrze) — patrz `notatki/algorytmy/*.md` (jeden plik na algorytm,
**musi być aktualizowany w tym samym kroku co zmiana logiki danego
algorytmu** — patrz `notatki/algorytmy/README.md`).

## Wyniki z pełnej skali na klastrze (2026-09-03)

Użytkownik uruchomił zadania na WCSS i przesłał wyniki (zip-y w `wyniki/`) - pliki
`.xlsx` wyekstrahowane do `wyniki/wyniki_excela/<scenariusz>/`, pełna analiza liczbowa
(przeliczona z surowych arkuszy `Dane`/`Wyniki`/itp. przez pandas, NIE odczytana z
formuł Excela - te nie mają cache'owanych wartości, bo plik nigdy nie był otwarty w
prawdziwym Excelu) w `wyniki/_analiza_klastra.md`. Poniżej kluczowe liczby.

Uwaga terminologiczna (WYJAŚNIONE, nie jest to błąd): `przeglad_wielu_lokalizacji.zip`
ma 1290 wierszy = **43 pliki pogodowe × 30 algorytmów**, dokładnie pełna skala. Kolumna
"Lokalizacja" w Excelu pokazuje NAZWĘ MIASTA (10 unikalnych: Abisko, Fairbanks, Jakuck,
Kraków, Ojmiakon, Old Crow, Oslo, Puszcza Białowieska, Suwałki, Wrocław), bo
`parsuj_lokalizacje` rozdziela surową nazwę pliku na miasto/interwał/rok jako OSOBNE
kolumny - 8 z tych miast ma po 5 plików (2021-2025) = 40, Suwałki 2 pliki (2010, 2023),
Wrocław 1 plik (2024) = 40+2+1=43 pliki. Więc "10 unikalnych miast" i "43 pliki pogodowe"
to nie sprzeczność - jedno liczy miasta, drugie pliki/lata. Przebieg jest KOMPLETNY.

- **Główny przegląd (energia)**: zwycięzca energetycznie -
  `fuzzy_ryzyko_2v2_opad` (Fuzzy+ryzyko+opad FL2v2) - 8031.5 kWh śr., -44.8% vs
  `algorytm_z_normy` (14541.2 kWh). REKOMENDACJA PRAKTYCZNA z arkusza (nie zmieniona
  przez pełną skalę): `risk_function_pid` - jedyny z 4 wariantów funkcji ryzyka BEZ
  ani jednego przypadku przegrzania >35°C (35/35 pozostałych ma anomalie - wyczerpanie
  dobowego budżetu przełączeń przy oscylujących warunkach, HRT dryfuje do ~47°C), przy
  11598.5 kWh (tylko nieznacznie gorzej niż wariant binarny 12492.6 kWh) i 59.4x mniej
  przełączeń. Najniższe IAE: `risk_function_pid_opad` (8.19M °C·s).
- **Wrażliwość transmitancji K/T1** (nominal + 7 scenariuszy, też 10 lok. × 30 alg.):
  K DOMINUJE (K+15% → -9.96% energii, monotonicznie), T1 PRAKTYCZNIE BEZ ZNACZENIA
  (-0.06%...+0.01%, szum statystyczny). Scenariusz łączony K10_T1_10 (-6.78%) ≈ sam
  K+10% (-6.87%) - cały efekt kombinacji pochodzi z K.
- **Wrażliwość 2 lokalizacje + szum** (Abisko/Ojmiakon, 14 scenariuszy K/L/T1 x
  szum on/off): patrz zaktualizowany wpis wyżej w "W trakcie / do ustalenia" -
  katastrofalne załamanie identyfikacji SOPDT pod szumem POTWIERDZONE na pełnej skali
  (K: 0.05%→98.4% błędu, T1: 1.1%→99.4%, R²: 1.000→-0.001), a `autotest_fit_ok` tego
  NIE wykrywa.
- **Krok sterowania** (top-3: `fuzzy_normy_2v2`/`fuzzy_ryzyko_2v2_opad`/`nauka_kary_opad`,
  43 lok.): wpływ na energię mały (rozstęp 1.4-4.5% między najlepszym a najgorszym
  krokiem), krok 600s systematycznie najgorszy. Wpływ na IAE WYRAŹNIEJSZY - do +14.6%
  dla `nauka_kary_opad` między 60s (najlepszy) a 300s (najgorszy) - regulator uczący
  się z karą traci precyzję śledzenia przy rzadszym próbkowaniu bardziej niż energię.
  Krok 10-60s zawsze blisko optymalny, 1s nie daje wyraźnej poprawy.
- **Szum wielu czujników**: patrz zaktualizowany wpis wyżej w sekcji "Status/co jest
  zrobione" (pełna skala, kluczowe liczby: WIATR/PUNKT_ROSY zero wpływu, SNOW/PRECIP
  dominują 42.6%/34.7%, `norma_pid` najbardziej odporny reaktywny algorytm).
- **Awarie czujników** (pełna skala, 30 algorytmów): HRT_rozłączenie najgorszy typ
  awarii (40.3% śr. |Δ energii|), AT_rozłączenie zerowy wpływ na WSZYSTKIE 30
  algorytmów (żaden nie polega krytycznie na ciągłości AT). Najbardziej "kruche":
  `risk_function`/`risk_function_opad` przy HRT_szum PRAWIE PODWAJAJĄ energię
  (+110.6%/+109.3%) - ich warianty PID (`risk_function_pid*`) w TYM SAMYM scenariuszu
  są niemal całkowicie stabilne (-0.6%) - kolejny mocny argument za PID nad binarną
  wersją funkcji ryzyka (dodatkowo do braku anomalii przegrzania z głównego przeglądu).

Pełne liczby, tabele per-scenariusz i metodologia weryfikacji - `wyniki/_analiza_klastra.md`.

## Wdrożenie na superkomputer (WCSS)

- Klaster: WCSS, dostęp przez `ssh uzytkownik@ui.wcss.pl` albo OnDemand
  (VSCode w przeglądarce). Dokumentacja: https://man.e-science.pl/pl/kdm/slurm/
- `requirements.txt` — numpy, pandas, scipy, numba, openpyxl, matplotlib.
- `slurm_smoke_test.sh` — MAŁY test (8 rdzeni, 30 min, kilka lokalizacji/algorytmów)
  do weryfikacji środowiska/wielowątkowości PRZED pełnym przeglądem. Sprawdź w
  logu linię "Wykryto limit rdzeni ze zmiennej SLURM_CPUS_PER_TASK=... -> N
  procesów" — to dowód, że autodetekcja rdzeni faktycznie działa na klastrze.
- `slurm_pelny_przeglad.sh` — pełny przegląd (wszystkie lokalizacje x wszystkie
  algorytmy, PEŁNY zakres dat). **Zasoby dobrane pod BUDŻET CPU-GODZIN konta**
  (`service-balance`), nie pod optymalną wydajność — konto ma limit QOS
  (`QOSGrpCPUMinutesLimit`), niezależny od tego, ile węzłów jest fizycznie
  wolnych. `--mem` NIE liczy się do tego budżetu (tylko `cpus x czas`), więc
  jest ustawiony hojnie.
- WAŻNE, ustalone empirycznie na klastrze:
  - Zlecaj TYLKO przez `sbatch`, nigdy `sh`/`bash` bezpośrednio — inaczej
    dyrektywy `#SBATCH` są ignorowane i skrypt wykonuje się w środowisku
    bieżącej (zwykle bardzo ograniczonej) sesji interaktywnej.
  - SLURM kopiuje zlecony skrypt do katalogu spool na przydzielonym węźle
    (`/var/spool/slurmd/<węzeł>/job<id>/`) i uruchamia go STAMTĄD — dlatego
    skrypty liczą katalog roboczy z `$SLURM_SUBMIT_DIR` (ustawianego przez
    SLURM), a NIE z `${BASH_SOURCE[0]}`/`$0` (to wykryłoby katalog spool, nie
    katalog z kodem).
  - Sesja interaktywna OnDemand (np. VSCode) to TEŻ zadanie SLURM — jeśli
    dostanie dużo rdzeni/długi czas, rezerwuje to na cały czas trwania sesji
    (rdzenie × zadeklarowany czas, nie faktyczne zużycie), co potrafi zjeść
    prawie cały budżet konta. Do samej edycji/zlecania `sbatch` wystarczą 2-4
    rdzenie / 2-4h.
  - `pip install` w skrypcie sbatch powinno być BEZWARUNKOWE (nie tylko przy
    tworzeniu nowego venv) — częściowo postawiony venv z przerwanej wcześniejszej
    próby inaczej zostaje cicho aktywowany bez pakietów.

## Zoptymalizowana pamięć (`symulacja_fizyczna.uruchom_kontroler`)

Historia przebiegu symulacji budowana jest jako PREALOKOWANE tablice numpy
(nie lista słowników Pythona) — zmierzone szczytowe zużycie pamięci na jedno
zadanie (pełny zakres dat, ~13 mln kroków) spadło z ~9.4GB do ~4.4GB po tej
zmianie. To był realny problem na klastrze (OOM przy 48 równoległych procesach
z za ciasnym `--mem`).

## Licznik RZECZYWISTYCH FLOPs (na bieżąco, per przebieg)

Odróżnij od `rejestr_algorytmow.ALGORYTMY[...]['flops_na_krok']` (szacunek
ANALITYCZNY, stały na algorytm, policzony ręcznie z analizy kodu). Licznik
RZECZYWISTY (`self._flops_licznik`, metoda `_dodaj_flopy` w
`rdzen_kontrolera.KontrolerBazowy` + lokalne liczniki w `algorytm_z_normy.py`/
`fuzzy_logic_*.py`, które nie dziedziczą tej klasy) sumuje FAKTYCZNIE wykonane
operacje w KONKRETNYM przebiegu (zależne od realnej długości historii/prognoz,
nie tylko typu algorytmu) i trafia do `stats['flops_rzeczywiste']` →
`PRZEGLAD_ZBIORCZY.csv` → zakładka "Dane" (kolumna "FLOPs (zmierzone)") i
"Zlozonosc_obliczeniowa" (kolumny "Śr. FLOPs/krok (zmierzone)" - porównanie z
szacunkiem analitycznym obok). Odkrycie z testów: `risk_function` mierzy się
na ~3.3x więcej niż szacunek analityczny sugerował (historia czujników rośnie
do ~86400 próbek, nie 43200, zanim przycinanie w ogóle zadzieje - przycinanie
odpala się dopiero przy przekroczeniu 2x limitu SENSOR_HISTORY_MAX_SAMPLES).

## Status / co jest zrobione

- [x] Numba JIT dla gorących pętli, pasek postępu.
- [x] Rozbicie każdego algorytmu na osobny plik + rejestr.
- [x] Generator Excela (formuły, nie hardkodowane wartości, formatowanie warunkowe).
- [x] Wykrywanie lokalizacji ze WSZYSTKICH plików pogodowych (43 lokalizacje).
- [x] 13 nowych algorytmów (raw fuzzy logic, fuzzy+ryzyko, PID/fuzzy+norma) = 17 razem.
- [x] Downsampling zapisywanych CSV (60s) przy zachowaniu pełnej rozdzielczości do statystyk.
- [x] Pełny zakres dat zamiast okna 7-dniowego (na żądanie użytkownika).
- [x] Digital-twin / cyfrowy bliźniak grzałki (model-based HRT forecast) +
      autotest startowy dla algorytmów adaptacyjnych.
- [x] Skrypt równoległy (`test_wszystkie_rownolegle.py`) ze sterowaniem przez
      zmienne środowiskowe, gotowy pod SLURM.
- [x] Naprawiony bug: `_przelicz_nastawy_simc` w `funkcja_ryzyka_pid.py` była
      zdefiniowana, ale nigdy nie wywoływana (PID zawsze na nastawach
      fabrycznych) — teraz wywoływana raz po autoteście.
- [x] Prognoza opadu (`przewidywanie_opadow.py`) zintegrowana jako 6 nowych
      algorytmów `_opad` (risk_function, risk_function_pid, fuzzy_ryzyko_1/2/2v2/3).
- [x] Opisy algorytmów + złożoność obliczeniowa (analityczna) w Excelu.
- [x] Wdrożenie na klaster WCSS — smoke test i pierwsza próba pełnego
      przeglądu (ograniczona do 48 rdzeni / 64h ze względu na budżet CPU-godzin konta).
- [x] Optymalizacja pamięci (numpy zamiast listy słowników) — ~2.1x mniej RAM/zadanie.
- [x] Licznik RZECZYWISTYCH FLOPs na bieżąco (patrz sekcja wyżej).

- [x] **Analiza wrażliwości na zmiany transmitancji grzania** —
      `symulacja_fizyczna.przygotuj_modele_stanowe` przyjmuje teraz opcjonalne
      procentowe zaburzenia (`k_h_pct`/`t1_h_pct`/`t2_h_pct`/`l_h_pct`) transmitancji
      SOPDT grzania (K/T1/T2/L) - domyślnie 0.0 = zero zmian w zachowaniu.
      `test_wszystkie_rownolegle.py` czyta je ze zmiennych `SZYNA_PERTURB_K/T1/T2/L`
      (+ `SZYNA_SCENARIUSZ` jako etykieta), zapisuje w stats/CSV
      (`scenariusz`/`perturb_*_pct`) i taguje nazwy plików wyjściowych etykietą
      scenariusza (poza `nominal`, który zachowuje oryginalne nazwy). Ustalony z
      użytkownikiem zakres: PEŁNE 43 lokalizacje x 23 algorytmy x 8 scenariuszy
      (nominal, K+5/10/15%, T1+5/10/15%, K+10%&T1+10% razem) - użytkownik
      świadomie zaakceptował koszt (~8x pełny przegląd) i zdecydował się
      dołożyć budżetu CPU-godzin w razie potrzeby zamiast zawężać zakres.
      `slurm_wrazliwosc_transmitancji.sh` (job array `--array=0-7`) odpala
      wszystkie 8 scenariuszy, każdy do osobnego podfolderu
      `wyniki/wrazliwosc_transmitancji/<scenariusz>/`. Zweryfikowane lokalnie:
      nominal = identyczne wyniki jak przed zmianą, K+10% daje realnie inne
      energia/max_hrt (perturbacja faktycznie wpływa na fizykę).
      Sens badania: algorytmy ADAPTACYJNE (autotest) same identyfikują
      zaburzony obiekt z pomiarów i powinny się dostroić; NIEADAPTACYJNE
      (stałe SIMC liczone offline z nominalnych parametrów, np. norma_pid) nie
      wiedzą o zaburzeniu - to pokazuje odporność jednych vs drugich.

- [x] **Krok symulacji/sterowania zmieniony z 1s na 10s (domyślnie)** w
      `test_wszystkie_rownolegle.py` (`SZYNA_KROK_S`, domyślnie `10.0`; `1`
      przywraca dawną rozdzielczość) - na żądanie użytkownika ("nie ma co
      robić całości co sekundę"). Wymagało naprawienia 3 miejsc, które po cichu
      zakładały dt=1s: `symulacja_fizyczna.przygotuj_modele_stanowe`
      (`punkty_opoznienia` nie dzielił przez dt - realny bug, tylko niewidoczny
      przy jedynym dotąd używanym dt=1), `wczytaj_pogode_1s` (nowy parametr
      `dt`, domyślnie 1.0 = bez zmian), oraz cyfrowy bliźniak
      (`rdzen_kontrolera.KontrolerBazowy._dt_sterowania`, ustawiane przez
      `uruchom_kontroler` zaraz po utworzeniu kontrolera; `_autotest_startowy`
      buduje model z `dt=self._dt_sterowania` i poprawnie przelicza liczbę
      kroków "przewijania"; `_evaluate_risk_setpoint` poprawnie przelicza
      długość/siatkę prognozy zanikania ciepła przez `_dt_sterowania`).
      Zweryfikowane: dt=1.0 daje BIT-IDENTYCZNE wyniki jak przed zmianą
      (energia, K/T1/T2/L z autotestu), dt=10.0 daje energię różniącą się o
      ~0.02-0.1% (fizycznie sensowne, autotest nadal poprawnie identyfikuje
      obiekt) przy **~13x szybszej symulacji** - bezpośrednio łagodzi ciasny
      budżet CPU-godzin z analizy wrażliwości (#3) i pełnego przeglądu.

- [x] **Wznawianie przerwanego przebiegu** (`test_wszystkie_rownolegle.py`) -
      domyślnie WŁĄCZONE (`SZYNA_WZNOW=0` wyłącza): jeśli `PRZEGLAD_ZBIORCZY.csv`
      z poprzedniego, niedokończonego przebiegu już istnieje w
      `FOLDER_WYNIKOW`, wczytuje go, pomija zadania (lokalizacja, algorytm) już
      w nim obecne i liczy TYLKO brakujące - stare wyniki trafiają do
      finalnego CSV razem z nowymi (nic nie ginie). Zweryfikowane: obcięcie
      CSV do 5/8 wierszy + ponowne uruchomienie -> poprawnie doliczyło tylko
      brakujące 3, finalny CSV ma wszystkie 8 z poprawnymi wartościami. Adresuje
      wprost obawę użytkownika o utratę wyników przy wyczerpaniu limitu
      czasu/pamięci na klastrze. Punkt kontrolny (PRZEGLAD_ZBIORCZY.csv)
      zapisywany PO KAŻDYM zadaniu (nie co 10, jak pierwotnie) - koszt
      pomijalny (pojedyncze ms) wobec czasu liczenia zadania (minuty), a
      minimalizuje ilość pracy do policzenia ponownie, gdyby proces padł tuż
      przed zapisem.
- [x] **Budżet przełączeń** dla algorytmów o wyjściu binarnym/dyskretnym -
      `MAX_SWITCHES_PER_DAY` podniesione z 12 do 100/dzień (`SZYNA_MAX_PRZELACZEN_DZIEN`),
      wywiedzione z założonego budżetu ŻYCIOWEGO przekaźnika
      (`BUDZET_PRZELACZEN_CALKOWITY`, domyślnie 500 000, `SZYNA_BUDZET_PRZELACZEN`).
      W Excelu (`Podsumowanie_algorytmy`) doszły kolumny "Przełączenia/dzień",
      "Przewidywane przełączenia/rok", "% budżetu życiowego zużyty/rok" -
      WYŁĄCZNIE dla algorytmów dyskretnych (typ inny niż PID/FL1 w rejestrze),
      dla ciągłych puste (nic nie mówią o zużyciu mechanicznym styku).
- [x] **Rodzina "uczenie z kar"** (5 nowych algorytmów:
      `nauka_kary`/`_temp`/`_opad`/`_blizniak`/`_ryzyko`, pliki
      `Algorytmy/funkcja_nauka_kary_pid*.py` + wspólna baza
      `funkcja_nauka_kary_wspolna.py`) - PID do progów normy LET-1 +
      adaptacyjny `_czynnik_nauczony` (start=0, aktualizowany raz/dobę na
      podstawie zsumowanych kar: przegrzanie HRT>35°C zmniejsza, zalegający
      śnieg>5mm/lód>2mm zwiększa). Warianty _temp/_opad dokładają wyprzedzającą
      karę z prognozy (Kalman AT / przewidywanie_opadow.py); _blizniak
      (adaptacyjny, autotest) liczy wyprzedzającą karę z przewidywanej
      trajektorii HRT (cyfrowy bliźniak); _ryzyko (adaptacyjny) łączy WSZYSTKIE
      trzy źródła w jedną ocenę ryzyka. Historia każdej aktualizacji uczenia
      logowana do `kontroler.historia_uczenia` -> osobny plik
      `<lokalizacja>_<algorytm>_uczenie.csv` -> zakładka "Uczenie_adaptacyjne"
      w Excelu (pełna tabela + wykres liniowy krzywej uczenia dla pierwszej
      lokalizacji). WYMAGAŁO przeniesienia `_autotest_startowy`/
      `_ostatnia_moc_autotestu` z `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy`
      do `rdzen_kontrolera.KontrolerBazowy` (czysto strukturalne, zero zmiany
      zachowania - zweryfikowane bit-identycznym wynikiem risk_function_pid
      przed/po). Zweryfikowane działanie na 10-dniowym oknie: `nauka_kary`
      (czysto reaktywny) nie zareagował (brak przekroczeń progów w tym oknie),
      `nauka_kary_ryzyko` (z prognozami) poprawnie wykrył ryzyko WCZEŚNIEJ i
      czynnik_nauczony sensownie rósł dzień po dniu (1.0 -> 6.0 w 9 dni).
- [x] **Test odporności na awarie czujników** (`test_awarie_czujnikow.py` +
      `generuj_excel_awarie.py`, osobny mały skrypt/Excel, NIE część głównego
      przeglądu) - dodano `fault_injector` do `symulacja_fizyczna.uruchom_kontroler`
      (opcjonalny callable(row, index)->dict, wołany TUŻ PRZED przekazaniem
      odczytu kontrolerowi - PRAWDZIWA fizyka zawsze liczy się z
      niezafałszowanych wartości, dokładnie jak realna awaria czujnika). 7
      scenariuszy (brak_awarii/referencja + bias +5°C/szum std=2°C/rozłączenie
      w połowie okna, każdy na HRT i na AT) x wszystkie algorytmy, 1
      lokalizacja (abisko, 10 dni, uzgodniony z użytkownikiem zakres startowy -
      łatwo rozszerzyć o kolejne czujniki/typy awarii). Zakładka
      "Odpornosc_na_awarie" w osobnym `Podsumowanie_awarii.xlsx` - wiersz per
      algorytm, kolumna per scenariusz, wartość = % odchylenia energii od
      scenariusza referencyjnego (skala barwna: im większe odchylenie, tym
      gorsza odporność).
- [x] **Test skuteczności `przewidywanie_opadow.py`** (`test_skutecznosc_prognozy_opadow.py`,
      w katalogu głównym) - ocenia dokładnie tę klasę, która realnie jedzie w
      produkcji (`Algorytmy/funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy`),
      na WSZYSTKICH 43 plikach pogodowych, z auto-wykryciem kroku próbkowania
      (15 vs 60 min) per plik. Lokalny, bez klastra (~6s na wszystkie 43
      pliki). Wynik: `wyniki/Podsumowanie_prognozy_opadow.xlsx` (3 zakładki:
      Wyniki_lokalizacje, Podsumowanie_ogolne, Definicje_poziomow). Zmierzone:
      80.1% globalna skuteczność osłony, 81.3% trafność alarmu (duży rozrzut
      między lokalizacjami, np. wroclaw_2024 tylko 62% trafności).
- [x] **Pogłębiona wrażliwość transmitancji + szumu na 2 lokalizacjach**
      (`test_wrazliwosc_dwie_lokalizacje.py` + `generuj_excel_wrazliwosc.py` +
      `slurm_wrazliwosc_2lok.sh`) - Abisko (najwięcej opadu/śniegu) i Ojmiakon
      (najzimniejsza), 14 scenariuszy transmitancji (K/L/T1 pojedynczo +10/+20%
      i w kombinacjach, do potrójnego K20+L20+T1_20) x 2 warianty (z/bez
      białego szumu 2.0°C std na HRT+CRT, ten sam mechanizm co
      `test_awarie_czujnikow.py`) x wszystkie algorytmy. Dla algorytmów
      adaptacyjnych DODATKOWO porównuje zidentyfikowane K/T1/L (z
      `controller.autotest_result`) z PRAWDZIWYMI zaburzonymi wartościami
      (`symulacja_fizyczna.K_H/T1_H/L_H * (1+pct/100)`) - kolumny
      `blad_identyfikacji_*_pct`. Zweryfikowane end-to-end (smoke test, 24/24
      zadań, obie lokalizacje, Excel z 4 zakładkami). **PEŁNA SKALA URUCHOMIONA
      NA KLASTRZE, PRELIMINARY FINDING POTWIERDZONY** (2026-09-03, patrz sekcja
      "Wyniki z pełnej skali na klastrze" niżej i `wyniki/_analiza_klastra.md`):
      błąd identyfikacji K rośnie z 0.05% (bez szumu) do 98.4% (z szumem),
      T1 z 1.1% do 99.4%, L z 0.74% do 67.2%, R² dopasowania spada z 1.000 do
      -0.001 - katastrofalne załamanie POTWIERDZONE na pełnym oknie, nie tylko
      w smoke teście. ISTOTNE: flaga `autotest_fit_ok` zostaje `True` w 100%
      przypadków ZARÓWNO bez, jak i z szumem - NIE wykrywa tego załamania,
      więc nie nadaje się jako bramka jakości identyfikacji w praktycznym
      wdrożeniu (otwarty problem, patrz "W trakcie / do ustalenia" niżej).
- [x] **IAE/ISE/ITAE (jakość regulacji)** — pełny opis z wzorami i tabelą
      "skąd target_temperature dla każdego algorytmu" w `notatki/IAE_ISE_ITAE.md`.
      `symulacja_fizyczna.uruchom_kontroler`
      teraz przechwytuje diagnostykę zwracaną przez algorytm (`_get_power`
      zwraca `(moc, diagnostics)` zamiast samej mocy) i całkuje błąd
      `target_temperature - HRT_rzeczywista` PO CZASIE, tylko na krokach z
      `need_heat=True` (poza tym target=HRT z definicji, zerowy błąd byłby
      sztuczny). ITAE liczone względem czasu OD POCZĄTKU BIEŻĄCEGO epizodu
      grzania (reset przy każdym need_heat False→True), nie względem
      absolutnego czasu symulacji - inaczej długie przebiegi (miesiące)
      byłyby zdominowane samą swoją długością. DOPISANE (2026-09-02, na wyraźne
      życzenie użytkownika - "dla każdego algorytmu, w głównej pętli") do
      WSZYSTKICH 29 algorytmów, w tym tych bez natywnego ciągłego celu:
      `compute_control`/`compute_control_gorski`/`algorytm_z_normy` teraz
      zwracają diagnostykę z `target_temperature` = próg WYŁĄCZENIA aktywnej
      gałęzi (opady/suchy mróz) gdy `heating_on`, bo to ten próg kończy dany
      epizod grzania; `fuzzy_logic_1/2/2v2/3` zwracają
      `target_temperature = T_ZADANA` (stały cel), `need_heat=True` zawsze -
      te cztery wcześniej zwracały SAMĄ moc bez krotki, teraz `(moc,
      diagnostics)` jak reszta (`_get_power` już to obsługiwał). Zweryfikowane:
      29/29 algorytmów ma `iae` niepuste w PRZEGLAD_ZBIORCZY.csv. Dodane do `PRZEGLAD_ZBIORCZY.csv`
      (test_wszystkie_rownolegle.py), `AWARIE_ZBIORCZY.csv`
      (test_awarie_czujnikow.py) i zakładek "Dane"/"Podsumowanie_algorytmy" w
      Excelu. Przy okazji dodano też "Max śnieg GLOBALNIE" per algorytm
      (MAXIFS przez wszystkie przebiegi, nie tylko średnia) do
      "Podsumowanie_algorytmy". Zweryfikowane end-to-end (3 algorytmy, 2 dni -
      poprawne None dla nieadaptacyjnych bez celu, realne liczby dla
      risk_function_pid).
- [x] **Diagnostyka wizualna funkcji ryzyka** (`test_diagnostyka_funkcji_ryzyka.py`) -
      uruchamia wybrane algorytmy (domyślnie `risk_function_pid`) na jednej
      lokalizacji (domyślnie Abisko, okno 14 dni), zapisuje CSV per algorytm +
      Excel z wykresami (AT/CRT/HRT/Target_temperature razem, osobno moc %) -
      korzysta z nowych kolumn `Target_temperature`/`Need_heat`, które
      `uruchom_kontroler` teraz ZAWSZE dopisuje do `df_hist` (NaN, gdy
      algorytm nie ma jawnego celu - ten sam mechanizm co IAE/ISE/ITAE).
      Zweryfikowane (2 algorytmy, 5 dni, 2 zakładki + 4 wykresy poprawnie).
- [x] **Wrażliwość na krok sterowania** (`test_wrazliwosc_kroku_sterowania.py`) -
      dla wskazanych algorytmów (domyślnie 3 kandydaci: `risk_function_pid`,
      `nauka_kary_ryzyko`, `fuzzy_ryzyko_1` - PODMIENIĆ na faktyczne top-3, gdy
      znane z pełnego przeglądu) sprawdza energię i IAE/ISE/ITAE przy kroku
      1/10/60/300/600s, na WSZYSTKICH lokalizacjach (domyślnie okno 30 dni dla
      szybkości). Wykres średniej energii vs krok w Excelu. Zweryfikowane (2
      algorytmy x 2 kroki x 1 lokalizacja, 4/4 OK).
- [x] **Wstępny ranking (2 lokalizacje, okno 30 dni, wszystkie 29 algorytmów)** -
      zakończony (2026-09-02). Ranking wg średniej energii (abisko+ojmiakon):
      DOMINUJE rodzina fuzzy (18 pierwszych miejsc, 4036-4250 kWh) - PID/histereza
      (risk_function*, norma_pid, nauka_kary*, compute_control*) wyraźnie
      wyżej (5556-6705 kWh, +38% do +66%). #1 ogólnie: `fuzzy_ryzyko_2v2_opad`
      (4036.6 kWh). WAŻNA PUŁAPKA znaleziona po drodze: pierwszy przebieg miał
      1 brakujące zadanie (nauka_kary_ryzyko/ojmiakon, zgubione mimo
      "Zakończono... Sukcesy: 57/58" w logu - proces widocznie padł tuż przed
      dopisaniem ostatniego wiersza) - średnia energia z n=1 (tylko Abisko,
      2968.5) była MYLĄCO niska; po dopisaniu brakującego zadania (Ojmiakon,
      9917.7) prawdziwa średnia to 6443.1 - WNIOSEK: zawsze sprawdzaj `n` przy
      agregacji wyników rankingowych, nie ufaj samej liczbie "Sukcesy: X/Y" w
      logu bez policzenia realnych wierszy w CSV.
      TOP-3 wybrane do grid-search NIE są literalnym top-3 wg energii (to by
      były 3 prawie identyczne warianty `fuzzy_ryzyko_*`, strojące TE SAME
      stałe RISK_* - nieinformatywne) - zamiast tego 3 ZRÓŻNICOWANI zwycięzcy,
      po jednym z każdej rodziny strojalnych stałych:
        1. `fuzzy_ryzyko_2v2_opad` (#1 ogólnie, 4036.6 kWh) - stałe RISK_* w
           funkcja_ryzyka_wspolne.py (współdzielone z risk_function*, wszystkimi fuzzy_ryzyko_*).
        2. `fuzzy_normy_2v2` (#8, 4079.9 kWh) - stałe NORMA_* w funkcja_normy_wspolne.py
           (współdzielone z norma_pid, wszystkimi fuzzy_normy_*).
        3. `nauka_kary_opad` (najlepszy z rodziny uczenia z kar, 6127.3 kWh) -
           stałe KARA_*/WSPOLCZYNNIK_UCZENIA_C/CZYNNIK_NAUCZONY_MIN/MAX_C w
           funkcja_nauka_kary_wspolna.py.
      Użyte jako domyślne w `test_wrazliwosc_kroku_sterowania.py`
      (SZYNA_ALGORYTMY_KROK) - PODMIEŃ, jeśli użytkownik zażąda literalnego top-3.
- [ ] **Strojenie progów (grid search)** - NASTĘPNY KROK, na bazie powyższego
      top-3: grid search na RISK_*/NORMA_*/KARA_* per algorytm, metodologia:
      strojenie na 2 lokalizacjach (Abisko+Ojmiakon), walidacja na reszcie.
- [x] **Nowy algorytm: `risk_function_pid_auto`** (2026-09-02) - REALNA implementacja
      propozycji auto-strojenia (`notatki/propozycja_auto_strojenie.md`), na
      bazie `risk_function_pid` (nie fuzzy_ryzyko/nauka_kary mimo lepszego
      rankingu - użytkownik chciał konkretnie "tej funkcji ryzyka"). Stroi 4
      progi (hrt_on_precip, at_low_freeze, hrt_on_dry, risk_snow_penalty_per_mm_c)
      co 7 dni metodą perturb-and-observe. Wymagało PROMOCJI
      `RISK_SNOW_PENALTY_PER_MM_C` z modułowej stałej na atrybut instancji w
      `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` (zero zmiany zachowania
      dla pozostałych 29 algorytmów - domyślna wartość = stała modułowa).
      Zweryfikowane: 30/30 algorytmów w smoke teście, progi realnie oscylują
      zgodnie z logiką hill-climbingu (prześledzone ręcznie), własna zakładka
      Excela "Strojenie_progow_ryzyka" (schemat inny niż "Uczenie_adaptacyjne"
      rodziny nauka_kary_*, stąd rozdzielone - `pliki_uczenia` w
      generuj_excel_podsumowanie.py teraz filtrowane do TYLKO
      KLUCZE_UCZENIA_KARY, żeby nie mieszać niekompatybilnych schematów CSV).
      Patrz notatki/algorytmy/risk_function_pid_auto.md po pełny opis i
      zaobserwowane ograniczenie (koszt zaszumiony zmiennością pogody).
- [x] **MPC (regulator predykcyjny): `mpc_liniowy` + `mpc_prognoza_pogody` + `mpc_miekkie_ograniczenia`**
      (2026-09-03) - PRAWDZIWY MPC (optymalizuje CAŁĄ trajektorię mocy na
      horyzoncie 2h), w odróżnieniu od `nauka_kary_blizniak`/`_ryzyko` (cyfrowy
      bliźniak tam to feedforward tylko na POJEDYNCZY krok). Mechanika (wspólna,
      `Algorytmy/mpc_wspolne.py`, mixin `_MPCMachineryMixin` dziedziczony RAZEM z
      `KontrolerRyzykaBazowy`/`KontrolerRyzykaOpadBazowy`, BEZ diamentu w MRO):
        - Z wyniku autotestu (K/T1/T2/L, ten sam mechanizm co `risk_function_pid`)
          budowany DRUGI model stanowy, w rozdzielczości BLOKU 15-minutowego
          (`dt=STEP_SECONDS=900s`, NIE `dt_sterowania` jak "cyfrowy bliźniak"
          reszty algorytmów) - świadoma decyzja (patrz "Otwarte pytanie 1"
          niżej), nie przeoczenie.
        - Na KAŻDEJ granicy bloku 15-min: QP (`scipy.optimize.minimize`,
          L-BFGS-B, boxy 0-100%, BEZ nowej zależności - scipy już jest w
          requirements.txt) na 8 przyszłych wartościach mocy, koszt = energia +
          kara za deficyt wobec progu z funkcji ryzyka + kara za skoki mocy.
          Aplikuje STAŁĄ moc z pierwszego bloku planu przez CAŁY blok ("move
          blocking") - klasyczny receding horizon co krok byłby nieopłacalny
          obliczeniowo (dt_sterowania=1s x rok x 43 lokalizacje).
        - `mpc_liniowy`: zaburzenie (CRT) na horyzoncie ZAKŁADANE STAŁE (wariant
          kontrolny, "bez prognozy pogody"). `mpc_prognoza_pogody`: zaburzenie z
          prognozy Kalmana + cel z wariantem funkcji ryzyka Z prognozą opadu
          (`KontrolerRyzykaOpadBazowy`) - "pełna" wersja. Różnica energetyczna
          między nimi = czysta wartość dodana prognozy pogody przy PEŁNEJ
          optymalizacji trajektorii (w odróżnieniu od par `*_opad` reszty
          algorytmów, gdzie różnica dotyczy tylko furtki ucieczki).
        - Bezpieczeństwo: `need_heat=False` w BIEŻĄCEJ chwili natychmiast zeruje
          moc (nie czeka na granicę bloku) - asymetria celowa (szybkie
          wyłączenie, rozważne załączenie).
        - Fallback: brak zidentyfikowanego modelu -> prosty regulator P;
          niepowodzenie solvera (wyjątek/NaN) -> OSTATNIA zastosowana moc (nie
          0%, nie norma) - status w `diagnostics['mpc_status']`.
      Trzy "otwarte pytania" z propozycji użytkownika rozstrzygnięte (i
      udokumentowane w nagłówku `mpc_wspolne.py`): (1) częstotliwość
      przeplanowania = raz na blok 15-min (nie co krok), (2) solver = scipy
      L-BFGS-B (nie osqp/cvxpy - problem wypukły, boxy proste, nowa zależność
      niepotrzebna), (3) fallback solvera = ostatnia zastosowana moc.
      Oprócz 2 wariantów WYSOKIEGO priorytetu (`mpc_liniowy`/`mpc_prognoza_pogody`)
      dobudowany (2026-09-03, na życzenie użytkownika) 3. wariant ŚREDNIEGO
      priorytetu: **`mpc_miekkie_ograniczenia`** - IDENTYCZNY jak
      `mpc_prognoza_pogody`, ale z INNYM kształtem kary za zbliżanie się do
      progu bezpieczeństwa: bariera wykładnicza (`_kara_bezpieczenstwa_mpc`
      nadpisany - `kara = W × exp(-K × margin)`, nigdy dokładnie zero, rośnie
      SZYBCIEJ niż kwadratowo pod progiem) zamiast kary czysto progowej (zero
      aż do przekroczenia). Zaimplementowane jako HOOK w `_MPCMachineryMixin`
      (`_kara_bezpieczenstwa_mpc`, domyślna implementacja = stara kara
      kwadratowa progowa), żeby wariant dzielił CAŁĄ resztę maszynerii MPC bez
      duplikacji kodu. Zweryfikowane: smoke test (abisko, 3 dni) pokazał
      OCZEKIWANY kierunek - mpc_miekkie_ograniczenia zużywa WIĘCEJ energii
      (423.7 kWh) niż mpc_liniowy (402.1) i mpc_prognoza_pogody (400.4),
      zgodnie z hipotezą "bariera zostawia większy zapas cieplny". "Economic
      MPC" (priorytet niski, wymaga taryfy zmiennej ceny energii, której NIE
      MAMY) świadomie POMINIĘTY na wyraźne życzenie użytkownika - nie budować
      niczego opartego o ceny/budżet energetyczny bez realnych danych taryfowych.
      `flops_na_krok` w rejestrze dla `mpc_liniowy`/`mpc_prognoza_pogody` to
      WYJĄTKOWO wartość ZMIERZONA (nie szacunek analityczny jak reszta
      algorytmów) - liczba iteracji solvera QP nie da się sensownie oszacować
      czytaniem kodu, patrz `notatki/FLOPs.md` (`mpc_miekkie_ograniczenia` ma
      szacunek po analogii, jeszcze niezmierzony realnie). Zweryfikowane:
      energia mpc_liniowy=402.1 kWh, mpc_prognoza_pogody=400.4 kWh (prognoza
      pogody realnie oszczędza energię, zgodnie z oczekiwaniem),
      mpc_miekkie_ograniczenia=423.7 kWh (bariera zostawia zapas, zgodnie z
      hipotezą), IAE/ISE/ITAE i FLOPy rzeczywiste policzone poprawnie, 0
      błędów. Patrz `notatki/algorytmy/mpc_liniowy.md`/`mpc_prognoza_pogody.md`/
      `mpc_miekkie_ograniczenia.md`.
- [x] **2 algorytmy z literatury: `histereza_pamiec_rosy` + `predykcja_wygladzanie_prosta`**
      (2026-09-03, na życzenie użytkownika, wprost z przesłanej pracy: S.
      Chiaradonna, G. Masetti, F. Di Giandomenico, F. Righetti, C. Vallati,
      "Enhancing sustainability of the railway infrastructure: Trading energy
      saving and unavailability through efficient switch heating policies",
      Sustainable Computing: Informatics and Systems 30 (2021) 100519). Druga
      przesłana praca (Jiang i in., "Distributed Energy Management..." - ADMM,
      SOCP, traction grid + budynek stacji) NIE dotyczy bezpośrednio grzania
      rozjazdów (inny problem: cała trakcja + komfort cieplny budynku stacji,
      taryfa zmienna) - świadomie pominięta, nie ma naturalnego przełożenia na
      "jeden kontroler jednego rozjazdu" bez wymyślania nowego problemu.
        - **`histereza_pamiec_rosy`** (polityka "P_mem" + próg "koordynatora" z
          pracy) - **PIERWSZY i JEDYNY algorytm w projekcie faktycznie
          czytający `PUNKT_ROSY_C`** (potwierdzone wcześniej empirycznie: szum
          na tym czujniku miał 0.00% wpływu na WSZYSTKIE pozostałe algorytmy -
          żaden go nie używał). Reguła: załącz gdy `HRT <= punkt_rosy + T_thr`
          ORAZ `HRT <= T_thr` (T_thr=3.0°C, spójne z `hrt_off_dry` reszty
          projektu - praca testowała 0/5°C jako skrajności analizy wrażliwości,
          bez jednej rekomendowanej wartości). Mechanizm "pamięci" z pracy
          (użyj ostatniego znanego punktu rosy przez Δm kroków po awarii
          łącza, potem przejdź na próg bez punktu rosy) zaimplementowany BEZ
          osobnego modelu awarii sieci - wykrywamy "zawieszenie" wprost z
          danych (punkt rosy niezmieniony przez DELTA_M_KROKOW=20 kroków,
          dokładnie taki sam objaw jak realne rozłączenie czujnika).
        - **`predykcja_wygladzanie_prosta`** (polityka "P_pre" z pracy) -
          decyzja na PROGNOZIE HRT (wygładzanie wykładnicze Holta - poziom +
          trend, O(1)/krok, na WŁASNEJ historii, binowanej co 15 min),
          CAŁKOWICIE ODDZIELNEJ od wspólnej prognozy Kalmana z
          `rdzen_kontrolera.py` używanej przez `risk_function_pid`/`mpc_*` -
          świadomie uboższa metoda, zgodnie z ideą pracy "lokalny kontroler bez
          dostępu do bogatszych zasobów koordynatora". **Kluczowa idea z pracy
          (cytat, sekcja 4.2.3): próg bezpieczeństwa = próg bazowy + WŁASNY, na
          bieżąco śledzony błąd bezwzględny prognozy (ε_f, średnia z do 50
          ostatnich błędów |prognoza-rzeczywistość|)** - JEDYNY algorytm w
          projekcie, w którym margines bezpieczeństwa NIE jest stałą.
      Oba `bezpiecznik: True`, `adaptacyjny: False` (brak autotestu SOPDT -
      to inny rodzaj adaptacji niż flaga rejestru mierzy). Registry: 35
      algorytmy razem. Zweryfikowane smoke testem (Abisko+Ojmiakon, 5 dni,
      6/6 OK) - ODKRYCIE: `histereza_pamiec_rosy` oszczędza dużo energii
      (354-459 kWh, poniżej normy) kosztem BARDZO WYSOKIEJ kary bezpieczeństwa
      (do 14.4 mln °C·s, min_hrt do -60°C w Ojmiakonie!) - dokładnie ten typ
      kompromisu energia/dostępność, który sama praca źródłowa opisuje jako
      ryzyko polityk P_mem/P_pre (jej Rys. 8-10). `predykcja_wygladzanie_prosta`
      zachowuje się umiarkowaniej (energia zbliżona do normy, kara
      bezpieczeństwa 9-16 tys. °C·s, min_hrt do -25°C) - margines
      samokalibrujący pomaga, ale nie eliminuje ryzyka całkowicie w skrajnie
      zimnych warunkach. Żaden z dwóch NIE MA (świadomie, wierność źródłu)
      osobnego priorytetu "bezwzględna ochrona przed głębokim mrozem", jaki ma
      kaskada funkcji ryzyka (priorytet #3) - realny, udokumentowany kompromis,
      nie błąd implementacji. Patrz `notatki/algorytmy/histereza_pamiec_rosy.md`/
      `predykcja_wygladzanie_prosta.md`.
- [x] **Kara bezpieczeństwa (nowy wskaźnik) + Min HRT/epizody HRT<-10°C w Excelu**
      (2026-09-03, na życzenie użytkownika) - UZUPEŁNIA IAE/ISE/ITAE, nie
      zastępuje: IAE/ISE/ITAE mierzą jak DOBRZE algorytm trzyma się WŁASNEGO
      celu, kara bezpieczeństwa mierzy jak BEZPIECZNY jest fizyczny WYNIK
      wobec BEZWZGLĘDNYCH progów normy (te same 3 progi dla WSZYSTKICH
      algorytmów w rejestrze, liczone ZAWSZE na każdym kroku - nie tylko gdy
      need_heat=True - i z PRAWDZIWYCH odczytów, nie zafałszowanych
      fault_injectorem). Trzy składowe (użytkownik podał dokładnie te
      warunki), każda aktywna tylko przy przekroczeniu progu, °C-ekwiwalent,
      CAŁKOWANA po czasie jak IAE: (1) zalegający śnieg > RISK_SNOW_LINGER_THRESHOLD_MM
      (5mm, próg WSPÓLNY z funkcja_ryzyka_wspolne.py, przeliczony na °C przez
      RISK_SNOW_PENALTY_PER_MM_C - też reużyty, nie nowy współczynnik), (2)
      marznący deszcz + HRT wciąż <2°C, (3) HRT poniżej bezwzględnego floora
      normy (-10°C). Osobno (na wyraźne życzenie użytkownika): `min_hrt`
      (istniał już w stats, teraz dodany do Excela) i `epizody_ponizej_floor`
      (licznik ZDARZEŃ z detekcją zbocza, jak `przelaczenia` - nie suma
      kroków). W Excelu: 3 nowe kolumny w "Dane" (Min HRT/Kara
      bezpieczeństwa/Epizody HRT<-10°C, podświetlane jak anomalie
      przegrzania), 4 nowe w "Podsumowanie_algorytmy" (średnia kara, Min HRT
      GLOBALNIE, **lokalizacja tego najgorszego przypadku** przez INDEX/MATCH
      z podwójnym kryterium bez formuły tablicowej CSE - odpowiedź na "połącz
      z miejscem gdzie to nastąpiło", suma epizodów), nowa sekcja "5)
      NARUSZENIA BEZPIECZEŃSTWA" w "Wnioski" (tekst z realnie policzonymi
      liczbami, jak sekcja anomalii przegrzania). Zweryfikowane: 64/64
      algorytmy x 2 lokalizacje (abisko+ojmiakon, 5 dni) - Ojmiakon ujawnił
      realny problem: rodzina `fuzzy_logic_*`/`fuzzy_normy_*` (stały cel 3°C,
      bez priorytetu ochrony przed floorem) spada tam do HRT ≈-27...-33°C
      (kara bezpieczeństwa rzędu milionów °C·s w oknie 5-dniowym) - dokładnie
      ten typ ryzyka, którego IAE/ISE/ITAE NIE wykrywa (te algorytmy trzymają
      się SWOJEGO celu nieźle, problem w samym celu). Patrz
      `notatki/kara_bezpieczenstwa.md` po pełny opis z przykładem.
- [x] **Analiza wrażliwości WAG kary bezpieczeństwa (nowa zakładka "Wrazliwosc_wag_kary")**
      (2026-09-07, na życzenie użytkownika - przygotowanie do publikacji: "dlaczego akurat
      te wagi?"). Trzy wagi (`KARA_WAGA_SNIEG_C_PER_MM`/`KARA_WAGA_MROZ_DESZCZ`/`KARA_WAGA_FLOOR`
      w `funkcja_ryzyka_wspolne.py`) CELOWO wydzielone jako stałe NIEZALEŻNE od tych sterujących
      funkcją ryzyka (mimo nominalnie identycznej wartości dla śniegu) - dzięki temu 6
      scenariuszy (±50% na jednej wadze na raz, `KARA_WAGI_SCENARIUSZE`) liczy się RÓWNOLEGLE z
      wariantem nominalnym W TYM SAMYM przebiegu symulacji, BEZ ponownej symulacji fizyki (w
      odróżnieniu od testu wrażliwości transmitancji K/T1, który faktycznie wymaga 8 osobnych
      przebiegów, bo tam zaburzenie zmienia zachowanie regulatora). Nowa zakładka pokazuje ranking
      algorytmów wg kary + Δ rangi per scenariusz + korelację Spearmana (odporność rankingu).
      Przy okazji naprawiony realny bug: finalny zapis `PRZEGLAD_ZBIORCZY.csv` w
      `test_wszystkie_rownolegle.py`/`test_wszystkie_algorytmy_wszystkie_lokalizacje.py`/
      `test_awarie_czujnikow.py` miał TWARDĄ listę znanych kolumn i PO CICHU gubił każdą kolumnę
      spoza niej (więc te 6 nowych kolumn ginęłoby bez śladu i bez błędu) - teraz dopisuje
      nieznane kolumny na końcu zamiast je odrzucać. Też dodany `SZYNA_ZAPISZ_CSV_SZCZEGOLOWE=0`
      w `slurm_wrazliwosc_transmitancji.sh` (na życzenie użytkownika - "nie generuj mi masy CSV") -
      wyłącza zapis pełnej trajektorii per (lokalizacja, algorytm) [+ *_uczenie.csv] dla testu
      transmitancji (8x44x35 = tysiące zbędnych plików, nieużywanych przez żaden generator Excela,
      PRZEGLAD_ZBIORCZY.csv zapisywany zawsze). Patrz `notatki/kara_bezpieczenstwa.md` (sekcja
      "Analiza wrażliwości wag").
- [x] **2 nowe algorytmy: ADRC liniowy i nieliniowy (`risk_function_ladrc`/
      `risk_function_nadrc`, rejestr 35→37)** (2026-09-07, na życzenie
      użytkownika - "dodaj algorytm ADCR i różne jego warianty", potwierdzone
      jako ADRC/Active Disturbance Rejection Control). Ta sama logika
      wyznaczania celu co `risk_function_pid` (`_evaluate_risk_setpoint`) -
      różnica WYŁĄCZNIE w regulacji wokół celu: Extended State Observer (ESO,
      2-stanowy: estymata HRT + estymata "całkowitego zakłócenia") zamiast
      całkowania błędu (PI). LADRC = liniowy (Gao 2003, bandwidth-parameterization,
      2 parametry pasma omega_c/omega_o=5x omega_c), NADRC = nieliniowy (Han
      2009, funkcja fal() w obserwatorze i prawie sterowania, skalibrowana
      żeby w wąskiej strefie liniowej pokrywać się z LADRC). Oba robią ten sam
      autotest startowy co risk_function_pid i wyliczają parametry z
      identyfikacji SOPDT (K/T1/T2/L) - patrz `wylicz_parametry_adrc` w
      `funkcja_ryzyka_adrc_wspolne.py`. **Złapany i naprawiony błąd skalowania
      przy weryfikacji** (smoke test): pierwsza wersja miała `b0=K/tau` bez
      podziału przez 100 - ponieważ cyfrowy bliźniak (`rdzen_kontrolera.
      _krok_modelu`) operuje na `u=moc_procent/100` (frakcja 0-1), a
      kontrolery ADRC na `moc_procent` (0-100), sterowanie wychodziło ~100x za
      słabe: HRT schodziło do -18...-20°C (norma: -9.2°C) zamiast trzymać się
      w okolicy pozostałych algorytmów. Po poprawce (`b0=K/(100*tau)`):
      min HRT -12.1...-12.4°C, energia 1319-1455 kWh - porównywalne z
      risk_function_pid (1223 kWh, min HRT -12.9°C). Patrz
      `notatki/algorytmy/adrc.md` po pełny opis, w tym obserwację, że kara
      bezpieczeństwa obu wariantów ADRC jest wciąż wyraźnie wyższa niż PID
      mimo podobnego min HRT (dłuższy czas w strefie zagrożenia, nie głębsze
      minimum) - niewytłumaczone/niedostrojone dalej w tej sesji, ciekawy
      punkt do analizy porównawczej.
- [x] **Przekierowanie ciężkich CSV na PD (`SZYNA_FOLDER_CSV_SZCZEGOLOWE`) + zbiorcze
      porównanie algorytmów w Excelu wrażliwości transmitancji** (2026-09-07,
      na życzenie użytkownika). Katalog roboczy/domowy na WCSS ma za mało
      miejsca na ~1628 plików pełnej trajektorii (44 lok. x 37 algorytmów) +
      *_uczenie.csv z pełnego przeglądu - użytkownik ma osobną, dużą usługę PD
      (`PD-info`, 400G/1M plików, prawie pusta). Nowa zmienna
      `SZYNA_FOLDER_CSV_SZCZEGOLOWE` (domyślnie = `SZYNA_FOLDER_WYNIKOW`, więc
      ZERO zmian w zwykłym użyciu) w `testy/test_wszystkie_rownolegle.py`
      przenosi WYŁĄCZNIE te dwa typy ciężkich plików gdzie indziej -
      `PRZEGLAD_ZBIORCZY.csv` i finalny Excel ZOSTAJĄ w `SZYNA_FOLDER_WYNIKOW`
      (małe, potrzebne lokalnie). **Musi być ustawiona identycznie w
      `generatory_excel/generuj_excel_podsumowanie.py`** (ta sama zmienna) -
      inaczej zakładka "Uczenie_adaptacyjne" cicho wyjdzie pusta (glob szukałby
      `*_uczenie.csv` w złym miejscu) - złapane i naprawione RAZEM w tym samym
      kroku, zweryfikowane end-to-end (3 algorytmy w tym `nauka_kary`, plik
      `_uczenie.csv` wylądował w przekierowanym folderze, zakładka
      "Uczenie_adaptacyjne" poprawnie go odczytała). Włączone w
      `slurm_pelny_przeglad.sh`/`slurm_smoke_test.sh`
      (`PDDIR=/lustre/pd03/hpc-wikjan2416-1787599067` - podmień, jeśli usługa
      PD użytkownika ma inną ścieżkę). Przy okazji: nowa zakładka
      "Podsumowanie_algorytmy" w `generuj_excel_wrazliwosc_transmitancji.py` -
      jeden wiersz na algorytm uśredniony po WSZYSTKICH 8 scenariuszach naraz
      (nie per scenariusz jak istniejąca "Podsumowanie_scenariusze") - energia/
      kara/min HRT + kolumna "Stabilność energii (CV%)" (odchylenie std.
      średniej energii MIĘDZY scenariuszami / średnia - niska = odporny na
      niepewność modelu obiektu).
- [x] **`notatki/wyniki_excel/` - jak czytać każdy plik Excela z wynikami**
      (2026-09-03, na życzenie użytkownika) - jeden plik notatki NA KAŻDY z 8
      generatorów Excela w projekcie (`podsumowanie_wynikow.md`,
      `podsumowanie_wrazliwosc.md`, `podsumowanie_kroku_sterowania.md`,
      `podsumowanie_szumu.md`, `podsumowanie_awarii.md`,
      `podsumowanie_prognozy_opadow.md`, `diagnostyka_funkcji_ryzyka.md`,
      `podsumowanie_master.md`, `README.md` jako indeks) - dla każdego: jakie
      ma zakładki, co znaczy KAŻDA kolumna, i dokładny wzór/agregacja, jakim
      dana wartość jest liczona (w tym które komórki to FORMUŁY EXCELA -
      wymagają otwarcia w prawdziwym Excelu/LibreOffice raz, żeby scache'ować
      wartość, zanim odczyta je np. pandas - opisane w README.md tego
      folderu). Napisane wprost z kodu generatorów (nie z pamięci) - patrz
      `notatki/wyniki_excel/README.md`.
- [x] **Konsolidacja + przygotowanie klastra na 3 nowe algorytmy (2026-09-03)**
      - użytkownik POCZĄTKOWO poprosił o doliczenie 3 nowych algorytmów
      (2 istniejące MPC + nowy `mpc_miekkie_ograniczenia`) do WSZYSTKICH
      testów LOKALNIE na laptopie (4 rdzenie/16GB) i scalenie z wynikami
      klastra - policzony realny szacunek czasu (~13-14h dla 5 z 6 kategorii
      testów, ale ~4-5 DNI dla samej wrażliwości transmitancji 8-scenariuszowej
      przy tylko 4 rdzeniach) - **PLAN PORZUCONY W TRAKCIE**, użytkownik
      zmienił zdanie: (1) dane pogodowe będą się zmieniać, szczegóły w
      OSOBNEJ, jeszcze nieotrzymanej wiadomości - NIE rozpoczynać żadnych
      dalszych dużych obliczeń zależnych od konkretnych lokalizacji/plików
      pogodowych, dopóki ta wiadomość nie przyjdzie; (2) zamiast liczyć
      lokalnie, PRZYGOTOWAĆ całość do uruchomienia na SUPERKOMPUTERZE (nie
      laptopie) z nowymi algorytmami. Efekt tej zmiany planu:
        - `test_wrazliwosc_kroku_sterowania.py`: domyślna lista algorytmów
          rozszerzona z 3 do 6 (dopisane `mpc_liniowy`/`mpc_prognoza_pogody`/
          `mpc_miekkie_ograniczenia`) - zweryfikowane smoke testem (12/12 OK,
          wszystkie 3 MPC działają poprawnie przy różnych krokach sterowania).
          `slurm_krok_sterowania.sh` zaktualizowany (szacunek kosztu 14→28
          core-h, liczba zadań 645→1290).
        - Pozostałe 5 kategorii testów (główny przegląd, wrażliwość
          transmitancji 8x, wrażliwość 2-lokalizacyjna+szum, szum wielu
          czujników, awarie czujników) już DYNAMICZNIE iterują cały rejestr
          `ALGORYTMY` - ZERO zmian kodu potrzebnych, nowe algorytmy trafią
          tam automatycznie przy najbliższym uruchomieniu `uruchom_wszystko.sh`.
          `scipy` (jedyna zależność MPC) już jest w `requirements.txt`.
        - Dodano `SZYNA_ALGORYTMY`/wznowienie-scalanie do
          `test_awarie_czujnikow.py` (wcześniej nie miał ANI filtra algorytmów,
          ANI wznowienia - każde uruchomienie NADPISYWAŁO CSV od zera) - teraz
          spójne z resztą skryptów, przyda się przy każdym przyszłym
          doliczaniu tylko wybranych algorytmów.
        - **`generuj_excel_wrazliwosc_transmitancji.py`** (NOWY, na życzenie
          użytkownika: "jedne zbiorczy plik excel z wynikami całości" dla
          różnych transmitancji) - konsoliduje 8 osobnych plików
          `Podsumowanie_wynikow.xlsx` (nominal + 7 scenariuszy K/T1) z
          `wyniki/wyniki_excela/<scenariusz>/` w JEDEN plik
          `wyniki/wyniki_excela/Podsumowanie_wrazliwosc_transmitancji_WSZYSTKIE.xlsx`
          (3 zakładki: Dane_wszystkie [10320 wierszy], Podsumowanie_scenariusze
          [macierz algorytm x scenariusz, energia + %vs nominal], Wnioski
          [tekst] - zweryfikowane na realnych danych z klastra, liczby zgodne
          z wcześniejszą analizą w `wyniki/_analiza_klastra.md`: K+15%→-9.96%,
          T1 praktycznie bez znaczenia).
        - **`zbierz_wyniki_excel.py`** (NOWY, na życzenie użytkownika: "do
          osobnego folderu wszystkie excele z wynikami") - reużywalna wersja
          ręcznej ekstrakcji zipów wykonanej wcześniej (patrz wpis o
          `wyniki/wyniki_excela/` wyżej w tym pliku) - skanuje `wyniki/*.zip`,
          wyciąga TYLKO pliki `.xlsx` (pomija ogromne surowe CSV per-krok) do
          `wyniki/wyniki_excela/<nazwa_zipa>/`, wykrywa i pomija bajt-identyczne
          duplikaty. NIE uruchomiony przeciw obecnym danym (folder już był
          ręcznie uporządkowany wcześniej w tej sesji - uruchomienie od nowa
          stworzyłoby inaczej nazwane, zduplikowane foldery) - gotowy do użycia
          przy NASTĘPNYM uploadzie wyników z klastra.
        - `test_wrazliwosc_kroku_sterowania.py`: domyślna lista algorytmów
          ZNOWU rozszerzona (2026-09-03, na kolejne życzenie użytkownika -
          "przeliczyć dla WSZYSTKICH algorytmów, nie tylko wybranych, żeby
          całość była bardziej miarodajna") - teraz WSZYSTKIE 33 z rejestru
          zamiast poprzedniej curatorowanej 6-tki (import `ALGORYTMY` na
          poziomie modułu, `list(ALGORYTMY)` jako domyślna wartość
          `SZYNA_ALGORYTMY_KROK`). `slurm_krok_sterowania.sh` ponownie
          zaktualizowany: 1290→7095 zadań, szacunek kosztu 28→154 core-h,
          `--time` 2h→6h (bezpieczny zapas 288 core-h).
        - **IAE/ISE/ITAE/kara bezpieczeństwa % względem normy LET-1** (nowe
          kolumny P/Q/R/S w zakładce "Dane", `generuj_excel_podsumowanie.py`)
          - na życzenie użytkownika: "niech norma [algorytm_z_normy] będzie
          naszym punktem odniesienia do całości". Wzór:
          `(wartość − wartość_normy) / wartość_normy × 100`, baseline OSOBNY
          dla KAŻDEJ (Lokalizacja, Interwał, Rok) - nie jeden globalny numer,
          bo jakość regulacji/bezpieczeństwo zależy silnie od konkretnej
          pogody. Puste, gdy baseline normy = 0 (częste dla kary
          bezpieczeństwa - norma z definicji rzadko łamie własne progi).
          Zweryfikowane smoke testem (algorytm_z_normy, risk_function_pid,
          mpc_liniowy, fuzzy_logic_1, 2 lokalizacje) - norma zawsze 0% (self-
          comparison), i ujawniło REALNY wynik: `fuzzy_logic_1` w Ojmiakonie
          ma karę bezpieczeństwa 46015% WYŻSZĄ niż norma (14 216.8 vs
          6 556 146.7 °C·s) - norma z definicji prawie nigdy nie łamie
          własnych progów, więc odchylenie w tysiącach % u innych algorytmów
          jest natychmiast czytelnym sygnałem realnego naruszenia
          bezpieczeństwa. Patrz `notatki/IAE_ISE_ITAE.md` i
          `notatki/kara_bezpieczenstwa.md` (sekcje "% względem normy LET-1").
          Podsumowanie_algorytmy (zakładka zbiorcza) NIE rozszerzone o
          analogiczne średnie kolumny - jeśli potrzebne, dorobić przy
          najbliższej okazji (świadomie pominięte teraz, żeby nie rozdmuchać
          już bardzo szerokiej tabeli bez wyraźnej prośby).
      **OTWARTE - czeka na wiadomość użytkownika**: szczegóły zmiany danych
      pogodowych (jaka zmiana, czy dotyczy istniejących 43 plików czy nowego
      zestawu) - wstrzymać dalsze duże obliczenia/uruchomienia klastrowe do
      czasu otrzymania tych szczegółów.
- [x] **Redukcja złożoności pamięciowej: bufor kroczący zamiast surowej
      historii** (2026-09-02, na życzenie użytkownika) - `rdzen_kontrolera.KontrolerBazowy`
      trzymał surową historię odczytów (`self.sensor_history` - lista obiektów
      RowData, okazała się CAŁKOWICIE NIEUŻYWANA nigdzie poza samym
      dopisywaniem, usunięta; `_hist_bin_ids/_hist_at/_hist_crt` - listy rosnące
      do 86400 próbek, re-binowane OD ZERA co TEMP_FORECAST_REFRESH_S przez
      `_bin_average_core`) - O(min(krok,86400)) pamięci NA INSTANCJĘ kontrolera.
      Zastąpione bufora KROCZĄCEJ ŚREDNIEJ 15-minutowej (`_roll_bin_ids/_roll_means_at/_crt`,
      `deque(maxlen=MAX_ROLLING_HISTORY=36)`) aktualizowanego PRZYROSTOWO w
      `_append_sensor_history` (sumowanie bieżącego binu + domknięcie przy
      zmianie bin_id) - O(1)/O(36) pamięci NIEZALEŻNIE od długości symulacji.
      Matematycznie równoważne (bin_id w tym symulatorze zawsze ściśle
      kolejne, więc interpolacja luk w `_forecast_attribute` jest no-opem w
      praktyce - "ostatnie 36 binów z małego bufora" == "ostatnie 36 binów
      wyliczone z całej historii"). ZWERYFIKOWANE: (1) izolowany test
      regresyjny (deterministyczna syntetyczna seria odczytów, 600 kroków, 8
      checkpointów) - `temperature_prediction()`/`rail_temperature_prediction()`
      BIT-IDENTYCZNE stary/nowy kod; (2) pełny smoke test 29/29 algorytmów
      (abisko, 3 dni) - te same wartości energii co przed zmianą; (3) pomiar
      pamięci (tracemalloc, 200k kroków ~23 dni) - stary kod: ~45MB rosnącej
      pamięci związanej z historią, nowy kod: ~0MB (RowData od razu
      zbierane przez GC, brak referencji trzymanej długoterminowo). Przy okazji
      USUNIĘTA martwa funkcja `_bin_average_core` (JIT numba) i stała
      `SENSOR_HISTORY_MAX_SAMPLES` (obie nieużywane po zmianie) - FLOPy w
      `_forecast_attribute` też spadły (koszt liczony teraz na ≤37 binach, nie
      na całej surowej historii) - TODO: przeliczyć `zlozonosc_pamieciowa`/
      `pamiec_przyblizona_mb`/`flops_na_krok` w rejestr_algorytmow.py dla
      wszystkich algorytmów dziedziczących KontrolerBazowy (nagłówek pola już
      zaktualizowany z ostrzeżeniem, wartości liczbowe jeszcze NIE
      przeliczone - zostały stare, zawyżone szacunki jako bezpieczna górna granica).
- [x] **Rozdzielczość zapisu CSV zwiększona do 10 min** (2026-09-02, na
      życzenie użytkownika) - `SZYNA_ZAPISZ_CO_N_SEKUND` domyślnie `600`
      (10 min, było `60`=1 min) w `test_wszystkie_rownolegle.py` i
      `test_wszystkie_algorytmy_wszystkie_lokalizacje.py` - dotyczy WYŁĄCZNIE
      zapisywanych plików CSV (mniejsze pliki), statystyki (energia/IAE/ISE/ITAE/...)
      liczone jak zawsze z pełnej rozdzielczości obliczeniowej (SZYNA_KROK_S)
      PRZED tym zmniejszeniem - zero wpływu na dokładność liczb w Excelu.
- [x] **Pełny test szumu wielu czujników** (`test_szum_wielu_czujnikow.py` +
      `slurm_szum_wielu_czujnikow.sh`, 2026-09-02) - w odróżnieniu od
      `test_awarie_czujnikow.py` (3 typy awarii, 2 czujniki, 1 poziom, 1
      lokalizacja) ten skrypt sprawdza 4 POZIOMY białego szumu (lekki/
      umiarkowany/silny/ekstremalny, kalibrowane osobno per typ sygnału) na 7
      czujnikach (HRT/CRT/AT/punkt rosy/wiatr/opad/śnieg) x 10 LOSOWYCH
      lokalizacji (seed=20260902, powtarzalny wybór) x wszystkie 29 algorytmów
      = 8410 zadań. IAE/ISE/ITAE liczone jak zawsze w głównej pętli
      (`uruchom_kontroler`), więc automatycznie w wynikach. Zweryfikowane
      (2 lokalizacje x 2 algorytmy x 29 scenariuszy = 116/116 OK, 5.6 min).
      **URUCHOMIONE W PEŁNEJ SKALI NA KLASTRZE** (2026-09-03, wyniki
      przeanalizowane, patrz sekcja "Wyniki z pełnej skali na klastrze" i
      `wyniki/_analiza_klastra.md`): degradacja energii rośnie monotonicznie z
      poziomem szumu (lekki 10.4% śr. odchylenia -> ekstremalny 15.7%), ale
      NIE dramatycznie. Kluczowe odkrycie: czujniki WIATR/PUNKT_ROSY mają
      ZEROWY wpływ na KAŻDY algorytm (nieużywane w logice decyzyjnej żadnego z
      32), za to SNOW/PRECIP dominują wrażliwość (42.6%/34.7% śr. odchylenia -
      rząd wielkości więcej niż czujniki temperatury HRT 7.0%/AT 3.7%/CRT
      2.4%). Najbardziej odporny reaktywny algorytm: `norma_pid` (3.5% śr.
      odchylenia); najmniej: `compute_control_gorski` (27.1%).
- [x] **`notatki/` - dokumentacja poza kodem** - `notatki/FLOPs.md` (pełny
      mechanizm liczenia FLOPs, analityczny vs rzeczywisty, z tabelą WSZYSTKICH
      miejsc `_dodaj_flopy` w kodzie) + `notatki/algorytmy/*.md` (jeden plik
      opisowy na każdy z 32 algorytmów, `README.md` tam jako indeks). Musi być
      aktualizowane razem ze zmianami kodu - patrz przypis przy "Zbiór
      algorytmów" wyżej.

## Orkiestracja wszystkich zadań SLURM naraz

`slurm/uruchom_wszystko.sh` (zwykły skrypt bash, NIE sbatch - uruchamiany
bezpośrednio `bash slurm/uruchom_wszystko.sh`, Z KATALOGU Benchmark/benchmark)
zleca WSZYSTKIE 7 zadań naraz w łańcuchu zależności SLURM
(`sbatch --dependency=afterok:<job_id>`): smoke_test -> pelny_przeglad ->
wrazliwosc_transmitancji -> wrazliwosc_2lok -> krok_sterowania ->
szum_wielu_czujnikow -> test_awarie, sekwencyjnie (nie równolegle - żeby nie
mnożyć jednoczesnej rezerwacji CPU-godzin i nie trafić znów na
QOSGrpCPUMinutesLimit). Jeśli którekolwiek zadanie w łańcuchu zawiedzie
(exit != 0), SLURM automatycznie anuluje resztę (DependencyNeverSatisfied) -
zero ręcznej interwencji potrzebnej między zadaniami. Rozszerzone 2026-09-02 o
3 nowe sbatch scripty (poprzednio 4 zadania/`slurm_test_awarie.sh` jedyny
dodatek): `slurm_wrazliwosc_2lok.sh` (~60-90 core-h szacunkowo),
`slurm_krok_sterowania.sh` (~14 core-h szacunkowo, NOWY - wcześniej ten test
nie miał sbatch scriptu wcale), `slurm_szum_wielu_czujnikow.sh` (~135 core-h
szacunkowo). Po zakończeniu WSZYSTKICH zadań:
`python generatory_excel/generuj_excel_master.py` (patrz
`generatory_excel/generuj_excel_master.py`) buduje JEDEN skonsolidowany
`wyniki/Podsumowanie_MASTER.xlsx` ze wszystkich wyników naraz - działa też
bezpośrednio na klastrze, nie tylko lokalnie (pomija bez błędu zadania, które
jeszcze nie mają wyników).

**Reorganizacja katalogu (2026-09-07, na życzenie użytkownika - "posegreguj
całość")**: wszystkie `.sh` (7x `slurm_*.sh` + `uruchom_wszystko.sh` +
`wznow_od_transmitancji.sh`) przeniesione do `slurm/`; wszystkie
`generuj_excel_*.py`/`zbierz_wyniki_excel.py` do `generatory_excel/`; wszystkie
`test_*.py`/`uruchom_wszystkie_testy.py` do `testy/`. `symulacja_fizyczna.py`,
`przewidywanie_opadow.py`, `Algorytmy/`, `notatki/`, `wyniki/` i foldery
pogodowe/danych zostały w `benchmark/` bez zmian. Każdy przeniesiony plik ma
poprawiony `BASE_DIR` (o jeden poziom w górę, z powrotem do `benchmark/`) i
jawne `sys.path.insert` dla katalogów, z których importuje - zweryfikowane
end-to-end (smoke test test_wszystkie_rownolegle.py, regeneracja Excela z
realnych danych klastra, pełny przebieg test_awarie_czujnikow.py z jego
generatorem). WAŻNE dla dalszej pracy: `sbatch`/`bash` na skrypty w `slurm/`
zlecaj ZAWSZE z katalogu `benchmark/` (np. `sbatch slurm/slurm_pelny_przeglad.sh`),
NIE z wnętrza `slurm/` - `SLURM_SUBMIT_DIR` (i tym samym `cd` w środku każdego
skryptu) odpowiada katalogowi, z którego wywołano `sbatch`/`bash`, nie
katalogowi samego pliku .sh.

## Pełna weryfikacja przed wdrożeniem na klaster (2026-08-27)

Po serii zmian (rodzina nauka_kary_*, budżet przełączeń, wznawianie, test
awarii czujników) wykonano pełny przegląd sprawdzający, czy nic się nie
zepsuło:
- [x] Składnia: wszystkie 43 pliki .py w projekcie kompilują się bez błędu.
- [x] Regresja: 56/56 zadań (28 algorytmów x 2 lokalizacje, 2 dni) - 0 błędów,
      wartości energii fizycznie sensowne.
- [x] Excel: wszystkie 7 zakładek kompletne (Dane/Podsumowanie_algorytmy/
      Podsumowanie_lokalizacje/Opisy_algorytmow/Zlozonosc_obliczeniowa/
      Uczenie_adaptacyjne/Wnioski), wszystkie 28 algorytmów obecne wszędzie,
      zero ostrzeżeń/błędów przy generowaniu.
- [x] Test awaryjności czujników (`test_awarie_czujnikow.py`) - PIERWSZY RAZ
      doprowadzony do końca (poprzednia próba przerwana wyłączeniem laptopa):
      196/196 zadań (28 algorytmów x 7 scenariuszy), 0 błędów,
      `Podsumowanie_awarii.xlsx` generuje się poprawnie. Sensowny wynik
      przykładowy: fuzzy_ryzyko_3_opad z biasem +5°C na czujniku HRT drastycznie
      niedogrzewa (max HRT spada do -2.6°C zamiast ~31°C) - dokładnie ten typ
      wykrycia wrażliwości, po który ten test powstał.
- [x] Analiza wrażliwości transmitancji - potwierdzona działająca RAZEM z
      resztą zmian (dt=10, zrefaktorowany autotest, rodzina nauka_kary_* w tym
      adaptacyjny nauka_kary_blizniak) - 4/4 zadania OK ze scenariuszem K+10%.
- [x] Wznawianie przerwanego przebiegu - potwierdzone (patrz sekcja wyżej).
- [x] Skrypty SLURM (`slurm_*.sh`) - sprawdzone bajt-po-bajcie: czyste
      zakończenia linii LF (Unix), zero CRLF/samotnych CR - bezpieczne do
      wgrania na klaster Linux (UWAGA: `grep -c $'\r'` w tym środowisku Bash
      okazał się zawodny/dawał fałszywe alarmy - do weryfikacji zakończeń linii
      używać bezpośredniego sprawdzenia bajtów w Pythonie, nie tego grepa).

## W trakcie / do ustalenia

- [x] **Nowa rodzina algorytmów: uczenie adaptacyjne z kar** — zrealizowana
      jako `nauka_kary*` (5 wariantów: bazowy, `_temp`, `_opad`, `_blizniak`,
      `_ryzyko` — patrz `notatki/algorytmy/nauka_kary.md` i pochodne).
- [x] **Naprawiono: estymacja grubości śniegu PRZEZ KONTROLER, nie ground
      truth** (2026-09-02) — `_evaluate_risk_setpoint` i
      `_evaluate_nauczony_setpoint` czytały wprost `row_data['SNIEG_GRUBOSC_MM']`,
      które w `symulacja_fizyczna.py` jest ustawiane z PRAWDZIWEJ
      `ice_model.snow_depth_m` (ground truth, dostępne tylko bezpiecznikowi
      symulacji) - niespójne z wymogiem samodzielnej estymacji przez
      sterownik. Naprawione: `rdzen_kontrolera.KontrolerBazowy._estymuj_grubosc_sniegu_mm`
      liczy WŁASNY, prosty bilans masy (przyrost z odczytu intensywności
      opadu śniegu SNOW_snieg × dt, ubytek wg prostego modelu degree-day
      proporcjonalnego do HRT>0°C, stała `SNIEG_TOPNIENIE_MM_S_NA_C=0.001`) -
      obie metody teraz wołają tę metodę zamiast czytać pole z row_data.
      Ponieważ liczone z pól row_data, ten estymator automatycznie dziedziczy
      podatność na fault_injector (bias/szum/rozłączenie) używany w
      `test_awarie_czujnikow.py` - nie trzeba osobnego mechanizmu zaszumiania.
      Zweryfikowane: 28/28 algorytmów przechodzi smoke test bez błędów po
      zmianie (test_wszystkie_rownolegle.py, abisko_60min_2024, 3 dni).
- [x] **Nowy algorytm: `compute_control_gorski`** — wariant `compute_control`
      dla rejonów górskich wg LET-1 pkt 2.4.18.7 ("W rejonach górskich gdzie
      występują bardzo intensywne opady śniegu... można ustawić temperaturę
      wyłączenia na +10°C") - podnosi WYŁĄCZNIE próg wyłączenia HRT przy
      opadach z 7.0°C na 10.0°C (`histereza_let1_gorski.py`). Wartość
      potwierdzona przez użytkownika bezpośrednim cytatem z normy
      (2026-09-02), nie zgadywana.
- [ ] **Wykresy skuteczności prognoz temperatury/opadu** w różnych warunkach
      (lokalizacjach/porach roku) - do zaprojektowania po zamknięciu #4.

## Rzeczy do pamiętania / pułapki

- `norma_pid` i `fuzzy_normy_*` DZIEDZICZĄ `KontrolerBazowy` (przez
  `KontrolerNormyCiaglaBazowy`), więc AKUMULUJĄ historię czujników (pamięć
  O(min(krok,43200))), mimo że nigdy nie korzystają z prognozy Kalmana ani
  autotestu — to jest "niewykorzystywana" pamięć, celowo opisana tak w rejestrze.
- `risk_function`/`risk_function_opad` (wersje BINARNE) NIE mają autotestu/
  cyfrowego bliźniaka (świadomie wykluczone) — tylko wersje PID i fuzzy_ryzyko_*
  są adaptacyjne.
- Historia czujników (`sensor_history`, `_hist_bin_ids` itd.) jest przycinana
  DOPIERO przy przekroczeniu `SENSOR_HISTORY_MAX_SAMPLES * 2` (86400), nie przy
  samym `SENSOR_HISTORY_MAX_SAMPLES` (43200) — ma to realny wpływ na
  rzeczywisty koszt obliczeniowy (patrz sekcja FLOPs wyżej).
- Windows + `ProcessPoolExecutor` = tryb `spawn` = procesy potomne NA NOWO
  importują moduły ze źródła na dysku - żadne nadpisanie atrybutu modułu w
  procesie głównym (np. do celów testowych) nie dotrze do workerów. Do
  sterowania testami/produkcją służą WYŁĄCZNIE zmienne środowiskowe `SZYNA_*`.
- CPU-godziny na koncie WCSS (`hpc-wikjan2416-1787599067`) to twardy, NIE
  odnawialny limit (3500h przyznane), niezależny od fizycznej dostępności
  węzłów - QOS odrzuci zgłoszenie, jeśli `cpus x czas` przekroczy dostępny
  budżet, nawet gdy cały klaster stoi pusty.
