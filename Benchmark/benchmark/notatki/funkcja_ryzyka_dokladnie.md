# Funkcja ryzyka – jak działa dokładnie (i gdzie ma słabe punkty)

Opis oparty na kodzie: `Algorytmy/funkcja_ryzyka_wspolne.py`, `funkcja_ryzyka_binarna.py`,
`funkcja_ryzyka_pid.py`, `rdzen_kontrolera.py`. Fragmenty oznaczone **[zmierzone]** sprawdziłem
uruchomieniem symulacji, resztę wyciągnąłem z czytania kodu.

---

## 1. Co to właściwie jest

„Funkcja ryzyka” to **nie jest sam regulator**. To warstwa decyzyjna, która w każdym kroku odpowiada
na dwa pytania:

1. **Czy w ogóle trzeba grzać?** (`need_heat`)
2. **Do jakiej temperatury szyny ogrzewanej (HRT) grzać?** (`target_temperature`, „setpoint”)

Robi to jedna metoda, `KontrolerRyzykaBazowy._evaluate_risk_setpoint()`. To, **jak** ten setpoint
zamienia się na moc grzania, zależy od algorytmu wykonawczego, który po niej dziedziczy (histereza,
PI, fuzzy, MPC…). Dzięki temu ta sama „wiedza o zagrożeniach” jest wspólna dla dużej rodziny
algorytmów, a różni je tylko sposób sterowania.

Uwaga na nazewnictwo. W projekcie są **trzy różne rzeczy** z „ryzykiem” w nazwie:

| Nazwa | Co to jest | Gdzie |
|---|---|---|
| **funkcja ryzyka** (ten dokument) | kaskada priorytetów → `target_temperature` + `need_heat` | `funkcja_ryzyka_wspolne.py` |
| `wylicz_poziom_ryzyka(row_data)` | punktowa ocena zagrożenia 0–10 z bieżącego odczytu, karmi silnik fuzzy FL2v2 | `histereza_let1.py` |
| **kara bezpieczeństwa** | metryka oceny wyniku (nie sterowanie) | `symulacja_fizyczna.py`, [kara_bezpieczenstwa.md](kara_bezpieczenstwa.md) |

Nie mają wspólnej logiki. Wspólne są tylko niektóre progi (−10 °C, 5 mm śniegu) zdefiniowane w
jednym miejscu.

---

## 2. Architektura

```
KontrolerBazowy  (rdzen_kontrolera.py)
  pamięć czujników, prognoza Kalmana, estymator śniegu, autotest, cyfrowy bliźniak
    └─ KontrolerRyzykaBazowy   (funkcja_ryzyka_wspolne.py)
         _evaluate_risk_setpoint()  →  (target_temperature, need_heat, reason, forecast_min_c, warmup_soon)
         ├─ KontrolerRyzykaBinarny  – histereza 0/100 %           → risk_function
         ├─ KontrolerRyzykaPID      – regulator PI (SIMC)          → risk_function_pid
         │    └─ …PIDAutoStrojenie  – strojenie progów setpointu   → risk_function_pid_auto
         ├─ LADRC / NADRC           – regulatory ADRC              → risk_function_ladrc / _nadrc
         ├─ fuzzy_ryzyko_*          – silniki rozmyte FL1/FL2/FL2v2/FL3
         ├─ MPC (mpc_wspolne)       – predykcyjny na tym samym setpoincie
         ├─ nauka_kary_* (część)    – adaptacyjny czynnik uczony z kar
         └─ KontrolerRyzykaOpadBazowy  – dokłada prognozę OPADU     → *_opad
```

Przepływ w każdym kroku sterowania:

1. Kontroler dostaje wiersz odczytów (`row_data`).
2. `_evaluate_risk_setpoint` liczy prognozy, estymuje śnieg i przechodzi kaskadę priorytetów.
3. Wynik (`target`, `need_heat`) trafia do algorytmu wykonawczego, który wybiera moc 0–100 %.

---

## 3. Wejścia

### Używane w decyzji
| Pole | Do czego |
|---|---|
| `AT_temp_powietrza` | marznący deszcz (≤ 1 °C), suchy mróz (≤ −5 °C), historia do prognozy |
| `CRT_temp_niegrzana` | marznący deszcz (≤ 1 °C), prognoza Kalmana szyny |
| `HRT_temp_grzana` | błąd regulacji, ochrona przed −10 °C, topnienie w estymatorze śniegu |
| `PRECIP_opad` | wykrycie deszczu (> 0,0001 mm/s) |
| `SNOW_snieg` | wykrycie śniegu (> 0,0001 mm/s) i przyrost estymowanej pokrywy |
| `PUNKT_ROSY_C`, `WIATR_M_S` | **tylko** w wariancie `*_opad` (prognoza opadu) |

### Odczytywane, ale NIE wpływające na decyzję
`RH_wilgotnosc_wzgledna` trafia do historii, ale kaskada priorytetów jej nie sprawdza. To samo dotyczy
ciśnienia. Wiatr i punkt rosy nie działają w podstawowej wersji. Funkcja ryzyka **nie widzi więc
szronu ani mgły**. Widzi tylko opad i temperatury.

### Czego kontroler NIE dostaje
Pole `SNIEG_GRUBOSC_MM` (prawdziwa grubość śniegu z modelu) jest w wierszu, ale służy wyłącznie
bezpiecznikowi symulacji. Kontroler szacuje śnieg sam (sekcja 5), tak jak robiłby to prawdziwy
sterownik.

---

## 4. Pamięć i prognoza

**Pamięć.** Każda próbka trafia do historii (`_append_sensor_history`). Do prognoz używana jest
**krocząca średnia w oknach 15-minutowych**, maksymalnie 36 okien, czyli ok. 9 godzin.

**Prognoza (filtr Kalmana).** `_kalman_forecast_core` to filtr Kalmana ze stanem *poziom + trend*,
z wariancją procesu 0,05 i wariancją pomiaru 0,25. Prognozuje **8 kroków po 15 min = 2 godziny**.
Jest przeliczana najwyżej raz na 5 minut. Model jest prosty: poziom i trend wyciągnięty w przyszłość
liniowo. Nie zna fizyki pogody, dobowego cyklu ani frontów.

Prognozowana jest temperatura **szyny nieogrzewanej (CRT)**, a nie powietrza. CRT uwzględnia
bezwładność szyny, więc lepiej mówi, czy szyna sama się ociepli.

**Ciepło resztkowe (cyfrowy bliźniak).** Jeśli kontroler ma zidentyfikowany model obiektu (autotest,
sekcja 6), do prognozy CRT dodaje się fizyczną prognozę **zanikania ciepła z już wydanych komend
mocy**. Bez tego prognoza „nie wie”, że szyna jest jeszcze ciepła po niedawnym grzaniu. Wynik to
`forecast_hrt`, z którego liczone są:

- `warmup_soon` – czy w najbliższych 2 krokach (30 min) `forecast_hrt` przekroczy 0 °C,
- `forecast_min_c` – minimum `forecast_hrt` w całym horyzoncie 2 h.

---

## 5. Estymator grubości śniegu

Kontroler prowadzi własny bilans „ile śniegu leży” (`_estymuj_grubosc_sniegu_mm`):

```
przyrost = SNOW_snieg [mm/s] · dt
ubytek   = 0,001 mm/s/°C · max(HRT, 0) · dt
stan     = max(0, stan + przyrost − ubytek)
```

Przyrost to intensywność opadu (woda, mm). Ubytek to prosty model „degree-day” z HRT.

### Znany problem **[zmierzone]**
Estymator dodaje milimetry **opadu (równoważnik wodny)** tak, jakby były milimetrami **grubości
pokrywy**. W modelu fizycznym grubość = woda ÷ gęstość, a świeży śnieg ma gęstość 50–250 kg/m³, więc
prawdziwa pokrywa jest kilkanaście razy grubsza niż „estymata”.

Pomiar: `risk_function`, Quebec City, najzimniejsze 20 dni sezonu:

| | max grubość |
|---|---|
| prawdziwa (model) | **5,4 mm**, w 86 krokach powyżej 5 mm |
| estymowana przez kontroler | **0,37 mm**, **ani razu** powyżej 5 mm |

Skutek: gałąź „zalegający śnieg > 5 mm” i „kara za grubość” (+0,05 °C/mm) w praktyce prawie się nie
uruchamiają. Kontroler reaguje na śnieg w trakcie opadu, ale prawie nie „pamięta” śniegu, który
zalega po jego ustaniu. To jeden pomiar dla jednego algorytmu i jednego okna, ale mechanizm
(niezgodność jednostek) jest ogólny.

---

## 6. Autotest i cyfrowy bliźniak

Dotyczy algorytmów z regulatorem ciągłym (PID, ADRC, część fuzzy/MPC), **nie** wersji binarnej.

- Przy starcie grzeje **100 %** i zbiera odpowiedź skokową.
- Test kończy się, gdy HRT dojdzie do 38 °C (40 °C minus 2 °C zapasu), odpowiedź się ustabilizuje
  (nachylenie < 0,0008 °C/s) albo minie 4 godziny.
- Identyfikuje model SOPDT: K, T₁, T₂, L.
- Z niego liczy nastawy PI metodą **SIMC** (λ = θ) i buduje cyfrowego bliźniaka do prognozy ciepła
  resztkowego.
- Nastawy fabryczne (gdy identyfikacja się nie uda): Kc = 2,9262 %/°C, Ti = 3571,88 s.

---

## 7. Kaskada priorytetów (rdzeń funkcji)

Warunki sprawdzane **po kolei, wygrywa pierwszy spełniony**:

| # | Warunek | `need_heat` | Cel (`target`) | `reason` |
|---|---|---|---|---|
| 1 | deszcz **i** (CRT ≤ 1 °C **lub** AT ≤ 1 °C) | tak | **7,0 °C** | marznący deszcz – grzanie bezwarunkowe |
| 2a | śnieg lub estymowana pokrywa > 5 mm, **ale** `warmup_soon` **i** pokrywa ≤ 5 mm | **nie** | bieżące HRT | czekamy na naturalny zanik |
| 2b | jak wyżej, ale wariant `*_opad` widzi koniec frontu opadu, a pokrywa ≤ 10 mm | **nie** | bieżące HRT | prognoza opadu pokazuje koniec frontu |
| 2c | śnieg / pokrywa (pozostałe przypadki) | tak | **4,0 °C + kara** | opad śniegu do wytopienia / zalegający śnieg |
| 3 | HRT ≤ −8 °C **lub** `forecast_min_c` ≤ −12 °C | tak | **−5,0 °C** | ochrona przed spadkiem HRT poniżej −10 °C |
| 4 | AT ≤ −5 °C | tak | **1,0 °C** | suchy mróz |
| – | nic z powyższego | nie | bieżące HRT | brak zagrożenia |

**Kara za śnieg (2c):** `kara = min(0,05 · grubość_mm, 6,0)`, cel = 4,0 + kara. Pokrywa 8 mm dałaby cel
4,4 °C; maksymalne +6 °C wymagałoby 120 mm estymowanego śniegu.

**Uwagi do kolejności:**
- Priorytet 1 nie zważa na prognozę. Gołoledź może powstać natychmiast.
- W priorytecie 2 cel 4 °C jest wyższy niż w 3, więc grzanie pod śniegiem „przykrywa” też ochronę
  floora.
- Ochrona floora (3) reaguje **także na prognozę**, więc przy silnym mrozie (AT poniżej ok. −11 °C,
  bo CRT ≈ 1,09·AT) włącza się prawie stale. To główny tryb pracy w bardzo zimnych lokalizacjach i
  główny powód wysokiej energii.
- „Brak zagrożenia” dla suchego mrozu obejmuje **AT między −5 °C a 0 °C**, tak jak w normie LET-1.

### Stałe (`funkcja_ryzyka_wspolne.py`)
| Stała | Wartość |
|---|---|
| `RISK_FREEZING_RAIN_TARGET_C` | 7,0 °C |
| `RISK_HRT_ABSOLUTE_FLOOR_C` | −10,0 °C |
| `RISK_HRT_FLOOR_TRIGGER_C` | −8,0 °C |
| `RISK_HRT_FLOOR_TARGET_C` | −5,0 °C |
| `RISK_FORECAST_COLD_TRIGGER_C` | −12,0 °C |
| `RISK_NEAR_TERM_STEPS` | 2 (= 30 min) |
| `RISK_SNOW_LINGER_THRESHOLD_MM` | 5,0 mm |
| `RISK_SNOW_PENALTY_PER_MM_C` / `_MAX_C` | 0,05 °C/mm / 6,0 °C |
| `hrt_on_precip` (śnieg, cel bazowy) | 4,0 °C |
| `at_low_freeze` (suchy mróz, próg AT) | −5,0 °C |
| `hrt_on_dry` (suchy mróz, cel) | 1,0 °C |
| `RISK_OPAD_PROGNOZA_CIENKA_MM` | 10,0 mm |

Progi LET-1 (`hrt_on_precip`, `at_low_freeze`, `hrt_on_dry`) i kara za śnieg są atrybutami
instancji, więc `risk_function_pid_auto` może je stroić automatycznie co 7 dni.

---

## 8. Jak setpoint zamienia się na moc

**Binarny (`risk_function`).** Bez zagrożenia: 0 %. Gdy grzeje: trzyma, dopóki
`HRT < target + 2,0 °C`. Gdy nie grzeje: włącza dopiero przy `HRT < target`. Dodatkowo:
minimum **60 s** między przełączeniami i **dobowy limit przełączeń** (domyślnie 12, w przeglądach
ustawiony na 100).

**PID (`risk_function_pid`).** Błąd = `target − HRT`. Regulator PI z anty-windupem (całka zamrożona
przy nasyceniu), wyjście obcięte do 0–100 %. Gdy `need_heat = false`, moc = 0, a całka jest zerowana.

**Fuzzy (`fuzzy_ryzyko_*`).** Ten sam setpoint daje błąd `target − HRT`, który wchodzi do silnika
rozmytego. W wariantach FL2v2 przed silnikiem stoją jeszcze twarde reguły na HRT i AT (np. HRT <
−10 °C → 100 %, HRT ≥ 6 °C → 0 %), więc setpoint z funkcji ryzyka działa tylko w „środku” zakresu.

**Wariant `*_opad`.** Do warunku 2b dokłada prognozę opadu (`przewidywanie_opadow`): jeśli w
najbliższych 30 minutach nie widać opadu, a pokrywa jest cienka, nie grzeje „na zapas”.

---

## 9. Przykład (kilka kroków)

Warunki: opada śnieg, AT = −6 °C, CRT = −6,5 °C, HRT = 1 °C, estymowana pokrywa 0,2 mm.

1. Deszcz? Nie. Marznący deszcz nie zachodzi.
2. Śnieg? Tak. `warmup_soon`? Prognoza CRT ≈ −7 °C, nie. Gałąź 2c: `target = 4,0 + 0,01 = 4,01 °C`.
3. Binarny: `HRT (1) < target (4,01)` → włącz. Grzeje do `HRT ≥ 6,01 °C`, potem wyłącza (o ile opad
   trwa i target się nie zmienił).
4. Po ustaniu opadu i przy pokrywie 0,3 mm (poniżej 5 mm) funkcja przechodzi do priorytetu 3 lub 4
   (zależnie od AT i prognozy). Pokrywa, która **naprawdę** leży, przestaje być widoczna dla
   kontrolera (sekcja 5).

---

## 10. Uczciwa ocena

### Mocne strony
- **Jasna, przewidywalna logika.** Priorytety można prześledzić i wytłumaczyć każdą decyzję (`reason`).
- **Wspólna dla wielu algorytmów**, więc porównanie między nimi dotyczy sposobu sterowania, a nie
  wiedzy o zagrożeniach.
- **Reaguje wyprzedzająco** dzięki prognozie CRT i ciepłu resztkowemu z cyfrowego bliźniaka.
- Marznący deszcz ma bezwarunkowy priorytet.

### Słabości i ryzyka
1. **Estymator śniegu zaniża grubość ok. 14× [zmierzone]** (sekcja 5). Rozwiązuje to tylko
   „śnieg w trakcie opadu”. Zalegająca pokrywa jest niewidoczna, a kara za grubość praktycznie zerowa.
2. **Ignoruje wilgotność, wiatr i punkt rosy** w wersji podstawowej. Szron i oblodzenie bez opadu
   nie są wykrywane.
3. **Dobowy limit przełączeń wygrywa z bezpieczeństwem** w wersji binarnej. Po wyczerpaniu limitu
   kontroler zostaje w poprzednim stanie, także podczas marznącego deszczu. W przeglądach limit to
   100/dobę, więc rzadko dochodzi do skutku, ale mechanizm istnieje.
4. **Prognoza jest bardzo prosta** (linia trendu). Szybko zmieniające się warunki (front, inwersja)
   są przewidywane słabo, a próg −12 °C w prognozie potrafi włączyć grzanie „na zapas” przy każdym
   dłuższym mrozie.
5. **Ochrona −10 °C nie jest gwarancją [zmierzone].** W tym samym przebiegu (Quebec, 20 dni,
   `risk_function`) minimalne HRT wyniosło **−14,9 °C**. Ochrona ma wyprzedzać i trzymać HRT powyżej
   −5 °C, ale bezwładność obiektu (opóźnienie ok. 20 min, stałe czasowe 19 i 41 min) i histereza
   binarna dopuszczają przekroczenie progu.
6. **Ucieczka „naturalny zanik” (2a/2b)** może wyłączyć grzanie w trakcie opadu, jeśli prognoza
   pokaże ocieplenie. Prognoza liniowa bywa zbyt optymistyczna.
7. **Martwy kod:** metoda `_poziom_ryzyka_funkcji` (mapowanie `reason` → 0–4) nie jest już nigdzie
   wołana. Warianty fuzzy 2v2 używają `wylicz_poziom_ryzyka` (skala 0–10). Docstring tej metody
   wciąż opisuje starą rolę.
8. **Metryka kary bezpieczeństwa nie jest niezależna od tej funkcji.** Dzieli z nią progi (−10 °C,
   5 mm), ale mierzy **prawdziwą** grubość śniegu, a kontroler jej nie zna (punkt 1). Kara za śnieg
   liczona z rzeczywistości i sterowanie liczone z zaniżonej estymaty to dwa różne światy.

### Co bym poprawił w pierwszej kolejności
1. Estymator śniegu: przeliczać opad na grubość przez gęstość (np. ×10 dla świeżego śniegu) albo
   estymować równoważnik wodny i próg 5 mm zdefiniować na tej samej skali.
2. Wyjątek od limitu przełączeń dla priorytetu 1 (marznący deszcz).
3. Uwzględnić RH i punkt rosy w jednym dodatkowym priorytecie „ryzyko szronu”.

To propozycje, nie zmiany wprowadzone w kodzie.
