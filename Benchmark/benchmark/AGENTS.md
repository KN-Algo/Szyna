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

## Zbiór algorytmów (30 sztuk, w `rejestr_algorytmow.ALGORYTMY`)

Rodziny: automat/histereza wg normy (2, + wariant górski `compute_control_gorski`
= 3), funkcja ryzyka binarna/PID (2) + ich warianty `_opad` (2), PID/fuzzy do
progów normy (5), fuzzy logic "surowy" wokół stałego celu (4), fuzzy + funkcja
ryzyka (4) + ich warianty `_opad` (4), uczenie adaptacyjne z kar `nauka_kary*`
(5 — bazowy + temp/opad/bliźniak/ryzyko).
Dokładne opisy typu/celu/adaptacyjności — patrz zakładka "Opisy_algorytmow" w
Excelu albo bezpośrednio `rejestr_algorytmow.py`. Opis DZIAŁANIA każdego
algorytmu z osobna (bardziej szczegółowy niż jednolinijkowy `opis` w
rejestrze) — patrz `notatki/algorytmy/*.md` (jeden plik na algorytm,
**musi być aktualizowany w tym samym kroku co zmiana logiki danego
algorytmu** — patrz `notatki/algorytmy/README.md`).

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
      zadań, obie lokalizacje, Excel z 4 zakładkami). PRELIMINARY FINDING
      (smoke test, 3-dniowe okno - do potwierdzenia na pełnym 45-dniowym
      przebiegu): szum 2°C na HRT/CRT DRASTYCZNIE psuje identyfikację SOPDT
      (błąd K/T1 rzędu -97%/-99% w jednym obserwowanym przypadku, mimo
      `fit_ok=True`) - autotest wygląda na bardzo nieodporny na realistyczny
      szum czujników w krótkim oknie identyfikacji. NIE URUCHOMIONE jeszcze w
      pełnej skali (~60-90 core-h szacunkowo dla okna 45 dni) - czeka na
      decyzję: lokalnie (dłużej) czy `sbatch slurm_wrazliwosc_2lok.sh`.
- [x] **IAE/ISE/ITAE (jakość regulacji)** — `symulacja_fizyczna.uruchom_kontroler`
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
      KOSZT PEŁNEJ SKALI: zmierzone ~0.19 core-min/zadanie przy oknie 2-dniowym,
      ekstrapolacja do domyślnego okna 10-dniowego (5x) ≈ 135 core-h szacunkowo
      - NIE URUCHOMIONE jeszcze w pełnej skali, czeka na decyzję (lokalnie w
      tle vs `sbatch slurm_szum_wielu_czujnikow.sh`).
- [x] **`notatki/` - dokumentacja poza kodem** - `notatki/FLOPs.md` (pełny
      mechanizm liczenia FLOPs, analityczny vs rzeczywisty, z tabelą WSZYSTKICH
      miejsc `_dodaj_flopy` w kodzie) + `notatki/algorytmy/*.md` (jeden plik
      opisowy na każdy z 28 algorytmów, `README.md` tam jako indeks). Musi być
      aktualizowane razem ze zmianami kodu - patrz przypis przy "Zbiór
      algorytmów" wyżej.

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
