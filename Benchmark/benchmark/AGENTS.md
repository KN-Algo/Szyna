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

## Zbiór algorytmów (23 sztuki, w `rejestr_algorytmow.ALGORYTMY`)

Rodziny: automat/histereza wg normy (2), funkcja ryzyka binarna/PID (2) + ich
warianty `_opad` (2), PID/fuzzy do progów normy (5), fuzzy logic "surowy" wokół
stałego celu (4), fuzzy + funkcja ryzyka (4) + ich warianty `_opad` (4).
Dokładne opisy typu/celu/adaptacyjności — patrz zakładka "Opisy_algorytmow" w
Excelu albo bezpośrednio `rejestr_algorytmow.py`.

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

## Orkiestracja wszystkich zadań SLURM naraz

`uruchom_wszystko.sh` (zwykły skrypt bash, NIE sbatch - uruchamiany bezpośrednio
`bash uruchom_wszystko.sh`) zleca WSZYSTKIE 4 zadania naraz w łańcuchu zależności
SLURM (`sbatch --dependency=afterok:<job_id>`): smoke_test -> pelny_przeglad ->
wrazliwosc_transmitancji -> test_awarie, sekwencyjnie (nie równolegle - żeby nie
mnożyć jednoczesnej rezerwacji CPU-godzin i nie trafić znów na
QOSGrpCPUMinutesLimit). Jeśli którekolwiek zadanie w łańcuchu zawiedzie
(exit != 0), SLURM automatycznie anuluje resztę (DependencyNeverSatisfied) -
zero ręcznej interwencji potrzebnej między zadaniami. Dodano też
`slurm_test_awarie.sh` (brakujący dotąd sbatch script dla
test_awarie_czujnikow.py, 16 rdzeni/100G/2h, partycja lem-cpu-short).

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

- [ ] **Nowa rodzina algorytmów: PID z "czynnikiem opadu"** — PID dążący do
      błędu=0, z offsetem setpointu rosnącym wraz z ryzykiem oblodzenia/opadem,
      anti-windup ograniczający narastanie błędu. USTALONE z użytkownikiem:
      MUSI samodzielnie estymować ile śniegu zalega/stopiło się na podstawie
      historii opad+temperatura (NIE korzysta z prawdziwej grubości śniegu z
      symulacji) - bo ma to być docelowo spójne z tym, co widziałby prawdziwy
      sterownik na sprzęcie (bez dostępu do danych "z boga" symulacji fizycznej).
      Warianty: bazowy, + prognoza temperatury (Kalman AT), + prognoza opadu
      (`przewidywanie_opadow.py`). Zaprojektowany szkic mechanizmu (jeszcze nie
      zaimplementowany): licznik `czynnik_opadu` rośnie przy wykrytym opadzie
      śniegu (na podstawie zmierzonego opadu), maleje wg szacowanego tempa
      topnienia gdy HRT > 0°C; setpoint PID = baza (np. próg suchego mrozu) +
      offset proporcjonalny do `czynnik_opadu` (z górnym limitem, podobnie jak
      RISK_SNOW_PENALTY_* w funkcja_ryzyka_wspolne.py). DODATKOWO (ustalone
      później z użytkownikiem): offset/czynnik ma też rosnąć, gdy HRT zbliża
      się do -10°C (ochrona przed floorem) - niezależnie od opadu, analogicznie
      do RISK_HRT_FLOOR_TRIGGER_C/RISK_HRT_ABSOLUTE_FLOOR_C już istniejących w
      funkcja_ryzyka_wspolne.py.
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
