# Algorytmy/rejestr_algorytmow.py
#
# Mapa: nazwa algorytmu -> (moduł, klasa, metoda decyzyjna). Używana przez wszystkie
# trzy skrypty testujące:
#   - test_jeden_algorytm_jedna_lokalizacja.py       (JEDEN algorytm, JEDNA lokalizacja + GUI)
#   - test_wszystkie_algorytmy_jedna_lokalizacja.py  (WSZYSTKIE algorytmy, JEDNA lokalizacja)
#   - test_wszystkie_algorytmy_wszystkie_lokalizacje.py (WSZYSTKIE algorytmy, WSZYSTKIE lokalizacje)
# dzięki temu wszystkie trzy zawsze widzą ten sam, spójny zestaw dostępnych
# algorytmów i nie trzeba nigdzie duplikować ścieżek importu.
#
# Metoda decyzyjna może zwracać:
#   - samą moc [%] (float)                    - jak compute_control, algorytm_z_normy, fuzzy_logic_*
#   - krotkę (moc [%], diagnostyka: dict)      - jak risk_function*, fuzzy_ryzyko_*, norma_pid, fuzzy_normy_*
#
# Każdy algorytm ma własny plik (łatwiejsza nawigacja). Wspólna infrastruktura:
#   - rdzen_kontrolera.py         - pamięć czujników + prognoza Kalmana + autotest
#   - funkcja_ryzyka_wspolne.py   - setpoint funkcji ryzyka (Kalman + kara za śnieg),
#                                   współdzielony przez risk_function/risk_function_pid
#                                   i fuzzy_ryzyko_* (KontrolerRyzykaBazowy), oraz
#                                   wariant z prognozą OPADU (przewidywanie_opadow.py,
#                                   KontrolerRyzykaOpadBazowy), współdzielony przez
#                                   *_opad
#   - funkcja_normy_wspolne.py    - setpoint z progów normy LET-1 (bez pamięci/prognozy),
#                                   współdzielony przez norma_pid i fuzzy_normy_*
#   - silniki_fuzzy.py            - rdzenie wnioskowania rozmytego (FL1/FL2/FL2v2/FL3),
#                                   współdzielone przez fuzzy_logic_*, fuzzy_ryzyko_*,
#                                   fuzzy_normy_*
#   - przewidywanie_opadow.py     - prognoza intensywności opadu (0-3, horyzont 2h,
#                                   model wilgotności względnej/mokrego termometru na
#                                   prognozie AT z Kalmana), używana przez *_opad, żeby
#                                   NIE grzać na zapas, gdy front opadowy kończy się, a
#                                   pokrywa jest cienka - ufamy bezwładności cieplnej.
# Żaden z tych plików nie jest samodzielnym algorytmem i nie ma tu wpisu.
#
# 'bezpiecznik': True oznacza, że w porównaniach (test_wszystkie_algorytmy_*)
# algorytm dostaje grubość śniegu/moc algorytm_z_normy jako referencję i NIE
# WOLNO mu przekroczyć jej w żadnej chwili (patrz symulacja_fizyczna.uruchom_kontroler,
# parametr snow_reference_mm). Wyłączone tylko dla algorytm_z_normy (sam jest
# wyznacznikiem) i compute_control (od początku projektu traktowany jako
# osobny, wcześniej istniejący algorytm referencyjny) - wszystkie pozostałe,
# "inteligentne" algorytmy (funkcja ryzyka, fuzzy logic, PID/fuzzy z normą)
# podlegają bezpiecznikowi.
#
# Pola opisowe (do zakładki opisowej w Podsumowanie_wynikow.xlsx - patrz
# generuj_excel_podsumowanie.py):
#   'typ'          - rodzaj regulatora wykonawczego (Histereza / PID / Fuzzy logic ...).
#   'cel'          - na czym oparty jest setpoint (temperatura zadana): Progi normy LET-1
#                    (statyczne progi, bez pamięci/prognozy), Funkcja ryzyka (pamięć +
#                    prognoza Kalmana + kara za zalegający śnieg), Funkcja ryzyka + prognoza
#                    opadu (jw. plus przewidywanie_opadow.py), albo Stały cel (fuzzy_logic_*
#                    - brak zewnętrznej strategii, cel wpisany na sztywno w silnik rozmyty).
#   'adaptacyjny'  - czy kontroler ma JEDNORAZOWY autotest startowy (skok grzania
#                    0%->100%, identyfikacja SOPDT) i przestraja się/buduje cyfrowy
#                    bliźniak na jego podstawie (patrz rdzen_kontrolera.autotest) - True
#                    tylko dla risk_function_pid(*) i fuzzy_ryzyko_*(*) (w tym warianty
#                    _opad). Pozostałe albo nie mają autotestu wcale, albo (norma_pid)
#                    używają nastaw SIMC wyliczonych offline raz, nie na żywo.
#
# Pola złożoności obliczeniowej (do zakładki "Zlozonosc_obliczeniowa" w Excelu) -
# SZACUNKOWE, wyliczone analizą kodu (liczenie operacji w każdej ścieżce), NIE
# zmierzone profilerem - traktuj jako rząd wielkości, nie dokładną liczbę cykli:
#   'zlozonosc_czasowa'      - notacja O() na krok symulacji (1 wywołanie metody
#                    decyzyjnej = 1 symulowana sekunda). Kontrolery dziedziczące
#                    KontrolerBazowy dopisują odczyt do sensor_history co krok
#                    (O(1) amortyzowane dzięki przycinaniu przy
#                    SENSOR_HISTORY_MAX_SAMPLES), ale te z prognozą Kalmana
#                    (_forecast_attribute) mają dodatkowo skok co
#                    TEMP_FORECAST_REFRESH_S=300 kroków, gdy przelicza się
#                    prognozę na PEŁNEJ zebranej historii (do 43200 próbek) - a
#                    te z cyfrowym bliźniakiem (_prognoza_zanikania_ciepla)
#                    dodatkowy skok co 300 kroków o rozmiarze
#                    HORIZON_STEPS*STEP_SECONDS=7200 kroków symulacji modelu w
#                    przód. Autotest startowy (adaptacyjne) to JEDNORAZOWY koszt
#                    O(czas trwania autotestu, do 14400 kroków) - nie wliczony
#                    do poniższych FLOPs/krok (te opisują stan USTALONY, PO
#                    autotescie).
#   'flops_na_krok'          - przybliżona ŚREDNIA liczba operacji zmiennoprzecinkowych
#                    NA KROK (uwzględniająca amortyzację powyższych skoków) -
#                    wyłącznie logika DECYZYJNA algorytmu, bez współdzielonej
#                    fizyki obiektu/śniegu (identycznej dla wszystkich
#                    algorytmów, więc nieróżnicującej). Rzędu dziesiątek-setek
#                    FLOPs/krok dla każdego algorytmu - realny czas symulacji
#                    (minuty/godziny) wynika z narzutu interpretera
#                    Pythona/pandas na krok, NIE z limitu przepustowości FLOPs
#                    procesora (to zadanie jest memory/interpreter-bound, nie
#                    compute-bound).
#   'zlozonosc_pamieciowa'   - notacja O() pamięci stanu instancji kontrolera
#                    względem liczby dotychczasowych kroków symulacji.
#   'pamiec_przyblizona_mb'  - przybliżony rozmiar stanu w stanie USTALONYM (po
#                    wypełnieniu/przycięciu buforów historii) w MB.

ALGORYTMY = {
    'compute_control': {
        'modul': 'histereza_let1',
        'klasa': 'KontrolerHisterezaLET1',
        'metoda': 'compute_control',
        'opis': 'Obecny algorytm sterownika (LET-1, histereza CRT/HRT) - histereza_let1.py.',
        'bezpiecznik': False,
        'typ': 'Histereza',
        'cel': 'Progi normy LET-1',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok (amortyzowane)',
        'flops_na_krok': 45,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) - pamięć czujników',
        'pamiec_przyblizona_mb': 18.0,
    },
    'algorytm_z_normy': {
        'modul': 'algorytm_z_normy',
        'klasa': 'AutomatPogodowyNorma',
        'metoda': 'compute_control',
        'opis': 'Czysty automat pogodowy wg instrukcji Iet-1 (referencja/wyznacznik dopuszczalnej ilości śniegu).',
        'bezpiecznik': False,
        'typ': 'Automat pogodowy (histereza)',
        'cel': 'Progi normy LET-1',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 18,
        'zlozonosc_pamieciowa': 'O(1) - brak pamięci/historii',
        'pamiec_przyblizona_mb': 0.001,
    },
    'risk_function': {
        'modul': 'funkcja_ryzyka_binarna',
        'klasa': 'KontrolerRyzykaBinarny',
        'metoda': 'risk_function',
        'opis': 'Funkcja ryzyka z pamięcią i prognozą Kalmana - wyjście binarne (0/100%) - funkcja_ryzyka_binarna.py.',
        'bezpiecznik': True,
        'typ': 'Histereza',
        'cel': 'Funkcja ryzyka (Kalman)',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (prognoza Kalmana)',
        'flops_na_krok': 145,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200))',
        'pamiec_przyblizona_mb': 18.0,
    },
    'risk_function_pid': {
        'modul': 'funkcja_ryzyka_pid',
        'klasa': 'KontrolerRyzykaPID',
        'metoda': 'risk_function_pid',
        'opis': 'Jak risk_function, ale z ciągłym regulatorem PI (0-100%) dostrojonym metodą SIMC - funkcja_ryzyka_pid.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, SIMC)',
        'cel': 'Funkcja ryzyka (Kalman)',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak 7200 kroków)',
        'flops_na_krok': 450,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'norma_pid': {
        'modul': 'funkcja_pid_normy',
        'klasa': 'KontrolerNormaPID',
        'metoda': 'norma_pid',
        'opis': 'Ciągły regulator PI dążący do progów normy LET-1 (bez pamięci/prognozy) - funkcja_pid_normy.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, SIMC offline)',
        'cel': 'Progi normy LET-1',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 18,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) - dziedziczona pamięć czujników (niewykorzystywana)',
        'pamiec_przyblizona_mb': 18.0,
    },
    'fuzzy_logic_1': {
        'modul': 'fuzzy_logic_1',
        'klasa': 'KontrolerFuzzy1',
        'metoda': 'compute_control',
        'opis': 'Regulator rozmyty (Sugeno) wokół stałego celu 3°C, wyjście ciągłe z miękkim obcięciem krańców - fuzzy_logic_1.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL1, ciągły)',
        'cel': 'Stały cel (3°C)',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 40,
        'zlozonosc_pamieciowa': 'O(1) - brak pamięci',
        'pamiec_przyblizona_mb': 0.001,
    },
    'fuzzy_logic_2': {
        'modul': 'fuzzy_logic_2',
        'klasa': 'KontrolerFuzzy2',
        'metoda': 'compute_control',
        'opis': 'Jak fuzzy_logic_1, ale wyjście twardo zbinaryzowane (próg 50%) - fuzzy_logic_2.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2, binarny)',
        'cel': 'Stały cel (3°C)',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 40,
        'zlozonosc_pamieciowa': 'O(1) - brak pamięci',
        'pamiec_przyblizona_mb': 0.001,
    },
    'fuzzy_logic_2v2': {
        'modul': 'fuzzy_logic_2v2',
        'klasa': 'KontrolerFuzzy2v2',
        'metoda': 'compute_control',
        'opis': 'Wariant fuzzy_logic_2 z dodatkową regułą i progiem "lodowato" zależnym od opadu - fuzzy_logic_2v2.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2v2, binarny, 7 reguł)',
        'cel': 'Stały cel (3°C)',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 48,
        'zlozonosc_pamieciowa': 'O(1) - brak pamięci',
        'pamiec_przyblizona_mb': 0.001,
    },
    'fuzzy_logic_3': {
        'modul': 'fuzzy_logic_3',
        'klasa': 'KontrolerFuzzy3',
        'metoda': 'compute_control',
        'opis': 'Jak fuzzy_logic_1, ale wyjście modulowane PWM (okno 60s) zamiast ciągłe - fuzzy_logic_3.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL3, PWM)',
        'cel': 'Stały cel (3°C)',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 42,
        'zlozonosc_pamieciowa': 'O(1) - stan PWM (2 liczby)',
        'pamiec_przyblizona_mb': 0.001,
    },
    'fuzzy_ryzyko_1': {
        'modul': 'funkcja_fuzzy_ryzyko_1',
        'klasa': 'KontrolerFuzzyRyzyko1',
        'metoda': 'fuzzy_ryzyko',
        'opis': 'Cel z funkcji ryzyka (Kalman + kara za śnieg), wykonawczo silnik FL1 (ciągłe) - funkcja_fuzzy_ryzyko_1.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL1, ciągły)',
        'cel': 'Funkcja ryzyka (Kalman)',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak 7200 kroków)',
        'flops_na_krok': 490,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_ryzyko_2': {
        'modul': 'funkcja_fuzzy_ryzyko_2',
        'klasa': 'KontrolerFuzzyRyzyko2',
        'metoda': 'fuzzy_ryzyko',
        'opis': 'Cel z funkcji ryzyka, wykonawczo silnik FL2 (binarne) - funkcja_fuzzy_ryzyko_2.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2, binarny)',
        'cel': 'Funkcja ryzyka (Kalman)',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak 7200 kroków)',
        'flops_na_krok': 490,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_ryzyko_2v2': {
        'modul': 'funkcja_fuzzy_ryzyko_2v2',
        'klasa': 'KontrolerFuzzyRyzyko2v2',
        'metoda': 'fuzzy_ryzyko',
        'opis': 'Cel z funkcji ryzyka, wykonawczo silnik FL2v2 (binarne, 7 reguł) - funkcja_fuzzy_ryzyko_2v2.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2v2, binarny, 7 reguł)',
        'cel': 'Funkcja ryzyka (Kalman)',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak 7200 kroków)',
        'flops_na_krok': 498,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_ryzyko_3': {
        'modul': 'funkcja_fuzzy_ryzyko_3',
        'klasa': 'KontrolerFuzzyRyzyko3',
        'metoda': 'fuzzy_ryzyko',
        'opis': 'Cel z funkcji ryzyka, wykonawczo silnik FL3 (PWM) - funkcja_fuzzy_ryzyko_3.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL3, PWM)',
        'cel': 'Funkcja ryzyka (Kalman)',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak 7200 kroków)',
        'flops_na_krok': 492,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_normy_1': {
        'modul': 'funkcja_fuzzy_normy_1',
        'klasa': 'KontrolerFuzzyNormy1',
        'metoda': 'fuzzy_normy',
        'opis': 'Cel z progów normy LET-1, wykonawczo silnik FL1 (ciągłe) - funkcja_fuzzy_normy_1.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL1, ciągły)',
        'cel': 'Progi normy LET-1',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 40,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) - dziedziczona pamięć czujników (niewykorzystywana)',
        'pamiec_przyblizona_mb': 18.0,
    },
    'fuzzy_normy_2': {
        'modul': 'funkcja_fuzzy_normy_2',
        'klasa': 'KontrolerFuzzyNormy2',
        'metoda': 'fuzzy_normy',
        'opis': 'Cel z progów normy LET-1, wykonawczo silnik FL2 (binarne) - funkcja_fuzzy_normy_2.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2, binarny)',
        'cel': 'Progi normy LET-1',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 40,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) - dziedziczona pamięć czujników (niewykorzystywana)',
        'pamiec_przyblizona_mb': 18.0,
    },
    'fuzzy_normy_2v2': {
        'modul': 'funkcja_fuzzy_normy_2v2',
        'klasa': 'KontrolerFuzzyNormy2v2',
        'metoda': 'fuzzy_normy',
        'opis': 'Cel z progów normy LET-1, wykonawczo silnik FL2v2 (binarne, 7 reguł) - funkcja_fuzzy_normy_2v2.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2v2, binarny, 7 reguł)',
        'cel': 'Progi normy LET-1',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 48,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) - dziedziczona pamięć czujników (niewykorzystywana)',
        'pamiec_przyblizona_mb': 18.0,
    },
    'fuzzy_normy_3': {
        'modul': 'funkcja_fuzzy_normy_3',
        'klasa': 'KontrolerFuzzyNormy3',
        'metoda': 'fuzzy_normy',
        'opis': 'Cel z progów normy LET-1, wykonawczo silnik FL3 (PWM) - funkcja_fuzzy_normy_3.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL3, PWM)',
        'cel': 'Progi normy LET-1',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok',
        'flops_na_krok': 42,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) - dziedziczona pamięć czujników (niewykorzystywana)',
        'pamiec_przyblizona_mb': 18.0,
    },
    'risk_function_opad': {
        'modul': 'funkcja_ryzyka_binarna_opad',
        'klasa': 'KontrolerRyzykaBinarnyOpad',
        'metoda': 'risk_function_opad',
        'opis': 'Jak risk_function, plus prognoza opadu (przewidywanie_opadow.py) - nie grzeje na zapas, gdy front '
                'kończy się a pokrywa jest cienka - funkcja_ryzyka_binarna_opad.py.',
        'bezpiecznik': True,
        'typ': 'Histereza',
        'cel': 'Funkcja ryzyka (Kalman) + prognoza opadu',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 155,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200))',
        'pamiec_przyblizona_mb': 18.0,
    },
    'risk_function_pid_opad': {
        'modul': 'funkcja_ryzyka_pid_opad',
        'klasa': 'KontrolerRyzykaPIDOpad',
        'metoda': 'risk_function_pid_opad',
        'opis': 'Jak risk_function_pid, plus prognoza opadu (przewidywanie_opadow.py) - nie grzeje na zapas, gdy '
                'front kończy się a pokrywa jest cienka - funkcja_ryzyka_pid_opad.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, SIMC)',
        'cel': 'Funkcja ryzyka (Kalman) + prognoza opadu',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 465,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_ryzyko_1_opad': {
        'modul': 'funkcja_fuzzy_ryzyko_1_opad',
        'klasa': 'KontrolerFuzzyRyzyko1Opad',
        'metoda': 'fuzzy_ryzyko_opad',
        'opis': 'Jak fuzzy_ryzyko_1, plus prognoza opadu (przewidywanie_opadow.py) - funkcja_fuzzy_ryzyko_1_opad.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL1, ciągły)',
        'cel': 'Funkcja ryzyka (Kalman) + prognoza opadu',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 505,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_ryzyko_2_opad': {
        'modul': 'funkcja_fuzzy_ryzyko_2_opad',
        'klasa': 'KontrolerFuzzyRyzyko2Opad',
        'metoda': 'fuzzy_ryzyko_opad',
        'opis': 'Jak fuzzy_ryzyko_2, plus prognoza opadu (przewidywanie_opadow.py) - funkcja_fuzzy_ryzyko_2_opad.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2, binarny)',
        'cel': 'Funkcja ryzyka (Kalman) + prognoza opadu',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 505,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_ryzyko_2v2_opad': {
        'modul': 'funkcja_fuzzy_ryzyko_2v2_opad',
        'klasa': 'KontrolerFuzzyRyzyko2v2Opad',
        'metoda': 'fuzzy_ryzyko_opad',
        'opis': 'Jak fuzzy_ryzyko_2v2, plus prognoza opadu (przewidywanie_opadow.py) - funkcja_fuzzy_ryzyko_2v2_opad.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL2v2, binarny, 7 reguł)',
        'cel': 'Funkcja ryzyka (Kalman) + prognoza opadu',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 513,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
    'nauka_kary': {
        'modul': 'funkcja_nauka_kary_pid',
        'klasa': 'KontrolerNaukaKaryPID',
        'metoda': 'nauka_kary',
        'opis': 'Cel z progów normy LET-1 + adaptacyjny czynnik uczony z kar (przegrzanie/śnieg/lód), '
                'czysto reaktywny (bez prognozy) - funkcja_nauka_kary_pid.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, uczący się z kar)',
        'cel': 'Progi normy LET-1 + nauczony czynnik',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) na krok, aktualizacja uczenia raz na dobę',
        'flops_na_krok': 30,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + log uczenia (rośnie ~1 wpis/dobę)',
        'pamiec_przyblizona_mb': 18.0,
    },
    'nauka_kary_temp': {
        'modul': 'funkcja_nauka_kary_pid_temp',
        'klasa': 'KontrolerNaukaKaryPIDTemp',
        'metoda': 'nauka_kary',
        'opis': 'Jak nauka_kary, plus prognoza temperatury powietrza (Kalman) - wyprzedzający bonus do celu '
                'i wyprzedzająca kara przy głębokim mrozie w prognozie - funkcja_nauka_kary_pid_temp.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, uczący się z kar)',
        'cel': 'Progi normy LET-1 + nauczony czynnik + prognoza temperatury',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman)',
        'flops_na_krok': 165,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + log uczenia',
        'pamiec_przyblizona_mb': 18.0,
    },
    'nauka_kary_opad': {
        'modul': 'funkcja_nauka_kary_pid_opad',
        'klasa': 'KontrolerNaukaKaryPIDOpad',
        'metoda': 'nauka_kary',
        'opis': 'Jak nauka_kary, plus prognoza opadu (przewidywanie_opadow.py) - wyprzedzający bonus przy '
                'nadchodzącym froncie, szybszy zanik czynnika przy kończącym się froncie i cienkiej pokrywie - '
                'funkcja_nauka_kary_pid_opad.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, uczący się z kar)',
        'cel': 'Progi normy LET-1 + nauczony czynnik + prognoza opadu',
        'adaptacyjny': False,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 175,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + log uczenia',
        'pamiec_przyblizona_mb': 18.0,
    },
    'nauka_kary_blizniak': {
        'modul': 'funkcja_nauka_kary_pid_blizniak',
        'klasa': 'KontrolerNaukaKaryPIDBlizniak',
        'metoda': 'nauka_kary',
        'opis': 'Jak nauka_kary, ale ADAPTACYJNY (autotest + cyfrowy bliźniak) - wyprzedzająca kara liczona z '
                'przewidywanej trajektorii HRT (fizyczny model reakcji obiektu na już wydane komendy), nie z '
                'prognozy pogody - funkcja_nauka_kary_pid_blizniak.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, SIMC, uczący się z kar)',
        'cel': 'Progi normy LET-1 + nauczony czynnik + prognoza cyfrowego bliźniaka',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak 7200 kroków)',
        'flops_na_krok': 470,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu + log uczenia',
        'pamiec_przyblizona_mb': 21.0,
    },
    'nauka_kary_ryzyko': {
        'modul': 'funkcja_nauka_kary_pid_ryzyko',
        'klasa': 'KontrolerNaukaKaryPIDRyzyko',
        'metoda': 'nauka_kary',
        'opis': 'Najbardziej zaawansowany wariant - ŁĄCZY prognozę temperatury, opadu i cyfrowego bliźniaka w '
                'JEDNĄ złożoną ocenę ryzyka i uczy się na jej podstawie (adaptacyjny, autotest) - '
                'funkcja_nauka_kary_pid_ryzyko.py.',
        'bezpiecznik': True,
        'typ': 'PID (PI, SIMC, uczący się z kar)',
        'cel': 'Progi normy LET-1 + nauczony czynnik + złożone ryzyko (temp+opad+bliźniak)',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 640,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu + log uczenia',
        'pamiec_przyblizona_mb': 21.0,
    },
    'fuzzy_ryzyko_3_opad': {
        'modul': 'funkcja_fuzzy_ryzyko_3_opad',
        'klasa': 'KontrolerFuzzyRyzyko3Opad',
        'metoda': 'fuzzy_ryzyko_opad',
        'opis': 'Jak fuzzy_ryzyko_3, plus prognoza opadu (przewidywanie_opadow.py) - funkcja_fuzzy_ryzyko_3_opad.py.',
        'bezpiecznik': True,
        'typ': 'Fuzzy logic (FL3, PWM)',
        'cel': 'Funkcja ryzyka (Kalman) + prognoza opadu',
        'adaptacyjny': True,
        'zlozonosc_czasowa': 'O(1) amortyzowane, skok co 300 kroków (Kalman + cyfrowy bliźniak) + rzadkie wywołania prognozy opadu',
        'flops_na_krok': 507,
        'zlozonosc_pamieciowa': 'O(min(krok, 43200)) + bufory autotestu/modelu',
        'pamiec_przyblizona_mb': 21.0,
    },
}


def stworz_kontroler(nazwa, **kwargs):
    """Tworzy instancję kontrolera po nazwie z ALGORYTMY. Zwraca (kontroler, nazwa_metody)."""
    if nazwa not in ALGORYTMY:
        dostepne = ', '.join(ALGORYTMY.keys())
        raise ValueError(f"Nieznany algorytm '{nazwa}'. Dostępne: {dostepne}")

    wpis = ALGORYTMY[nazwa]
    modul = __import__(wpis['modul'])
    klasa = getattr(modul, wpis['klasa'])
    kontroler = klasa(**kwargs)
    return kontroler, wpis['metoda']


def podlega_bezpiecznikowi(nazwa):
    """Czy dany algorytm w porównaniach dostaje śnieg/moc normy jako referencję bezpieczeństwa."""
    return ALGORYTMY[nazwa].get('bezpiecznik', False)
