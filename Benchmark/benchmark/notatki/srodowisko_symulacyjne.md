# Środowisko symulacyjne – modelowanie warunków pogodowych i obiektu

Opis wszystkiego, z czego składa się symulator używany w benchmarku algorytmów sterowania
ogrzewaniem rozjazdu: skąd bierzemy pogodę, jak zamieniamy ją na wejścia symulacji, jak
liczymy temperaturę szyny (transmitancje), jak liczymy śnieg i lód (model energetyczny), co
widzi sterownik i jak oceniamy wynik. Opis jest zgodny z kodem w `symulacja_fizyczna.py`,
`Model_sniegu_SnowClim/snowclim_physical_model.py`, `Generowanie_pogody/zaciaganie_pogody.py`
i `testy/test_wszystkie_rownolegle.py`.

---

## 1. Idea i architektura

Symulator jest **pętlą w zamkniętym układzie** (closed-loop), w której algorytm sterowania
dostaje „pomiary" i zwraca moc grzania 0–100 %, a symulator liczy, jak zareaguje szyna:

```
        pogoda (CSV, dane historyczne)
   AT, punkt rosy, opad, wiatr, nasłonecznienie
                     │
        interpolacja do kroku dt  ──►  składowa pogodowa CRT(t)   [transmitancja G_W]
                     │                            │
                     │                            ▼
   moc grzania u(t) ─┼──► opóźnienie L ─► G_H ─► składowa grzania
        ▲            │                            │
        │            │                            ▼
   ALGORYTM  ◄── odczyty:                HRT = CRT + składowa grzania
   (sterownik)   HRT, CRT, AT, RH, opad,        │
                 śnieg, grubość śniegu, ...     ▼
                     └──────────────►  model śniegu/lodu (bilans energii)
                                                │
                                                ▼
                                   grubość śniegu, lód ─► metryki (energia, kara, IAE...)
```

Kluczowe założenia:

1. **Pogoda jest wejściem zewnętrznym** – nie zależy od sterowania (szyna nie zmienia
   powietrza). Jest odtwarzana z danych historycznych.
2. **Obiekt (temperatura szyny) jest liniowy** – opisany dwiema transmitancjami, sumowanymi
   (zasada superpozycji).
3. **Śnieg i lód są liczone osobno**, modelem fizycznym, ze sprzężeniem zwrotnym od szyny:
   ciepło z szyny topi śnieg. Śnieg nie wpływa z powrotem na transmitancje.
4. **Wszystkie algorytmy dostają dokładnie tę samą pogodę i ten sam obiekt**. Różni je tylko
   decyzja o mocy, więc wyniki są porównywalne.

---

## 2. Dane pogodowe

### 2.1 Źródło

- **43 lokalizacje**: Open-Meteo *Historical Weather API* (`/v1/archive`), reanaliza
  **ERA5-Land**, rozdzielczość **godzinowa**, darmowe, bez klucza. Skrypt:
  `Generowanie_pogody/zaciaganie_pogody.py`. Zaleta: ta sama metodologia dla całego świata
  (ERA5-Land ma siatkę ~9–11 km pokrywającą cały ląd, więc nie ma „białych plam").
- **Wrocław** (`wroclaw_15min_2024`): osobne źródło – Open-Meteo *Historical Forecast API*,
  natywnie **15-minutowe** (`minutely_15`), sezon 2024/25. Plik celowo nie został nadpisany
  przy zmianie źródła pozostałych.
- Razem **44 pliki CSV** w `Pogoda_pomiary_15_minut/`, nazwa
  `{lokalizacja}_{rozdzielczość_min}min_{rok_startu}.csv`.

### 2.2 Zakres czasowy

- Półkula północna: **1 XI 2025 – 31 III 2026** (sezon zimowy). Wrocław: 1 XI 2024 – 31 III 2025.
- Półkula południowa (np. Ushuaia, Punta Arenas, Bariloche, Coyhaique, Sutherland, Mount
  Hotham): **1 V – 30 IX 2025** (tam zima jest w środku roku).
- Ok. 3600 wierszy godzinowych na lokalizację (Wrocław: ok. 14 500 wierszy 15-min).

### 2.3 Zmienne w pliku

| Kolumna | Jednostka | Uwagi |
|---|---|---|
| `data_czas` | czas | znacznik czasu |
| `temperatura_powietrza_C` | °C | temperatura powietrza na 2 m (AT) |
| `punkt_rosy_C` | °C | punkt rosy na 2 m |
| `opad_mm` | mm | **suma** opadu w oknie źródłowym (1 h lub 15 min) |
| `wiatr_m_s` | m/s | prędkość wiatru na 10 m |
| `naslonecznienie_sekundy` | s | liczba sekund słońca w oknie źródłowym (`sunshine_duration`) |

### 2.4 Dobór lokalizacji

Lokalizacje obejmują skrajnie zimne (Ojmiakon, Jakuck, Norylsk), śnieżne (Sapporo, Quebec,
Murmansk), górskie (Gulmarg, Manali, Lhasa), miejskie (Oslo, Kraków, Wrocław) i południowe
(Ushuaia, Sutherland). Dzięki temu benchmark nie jest dostrojony do jednego klimatu.

W skróconych przebiegach testowych wybieramy **najzimniejsze okno** o zadanej długości dni
(`wybierz_najzimniejsze_okno`: minimum średniej kroczącej temperatury na surowych danych).
Pierwsze N dni pliku mogłyby trafić na ciepły początek listopada, gdzie żaden algorytm nie
musi grzać i porównanie nic by nie mówiło. Pełny przegląd używa całego sezonu.

Dla ograniczonego zestawu 4 lokalizacji wybór zrobiono rankingiem łącznym: ranga wg minimalnej
temperatury powietrza plus ranga wg sumy opadu przy temp. ≤ 1 °C. Wygrały Sodankylä, Murmansk,
Quebec City i Norylsk.

---

## 3. Przygotowanie wejść: interpolacja do kroku symulacji

Funkcja `wczytaj_pogode_1s`. Nazwa jest historyczna (pierwotnie krok 1 s), dziś krok to
parametr `dt`.

**Krok symulacji `dt`**: w przeglądach na klastrze **10 s** (`SZYNA_KROK_S=10`). Zweryfikowano
wcześniej, że wynik energetyczny zmienia się o ok. 0,02 % względem kroku 1 s, a symulacja jest
ok. 13× szybsza. Wartość 1 s jest dostępna (`SZYNA_KROK_S=1`). Test wrażliwości na krok
sterowania sprawdza 1, 10, 60, 300 i 600 s.

Krok źródłowy jest wykrywany automatycznie jako mediana odstępów czasu, więc ten sam kod
obsługuje dane godzinowe i 15-minutowe.

| Zmienna | Sposób przeliczenia |
|---|---|
| temperatura powietrza, punkt rosy, wiatr | **interpolacja liniowa** między próbkami źródłowymi |
| opad | suma w oknie ÷ długość okna [s] = intensywność [mm/s], **stała** w całym oknie (`ffill`, opad ma charakter skokowy, nie interpolujemy go) |
| nasłonecznienie | interpolacja liniowa i przeskalowanie do wspólnego okna 900 s: `s · 900 / krok_źródłowy` |

Przeskalowanie nasłonecznienia jest konieczne, bo model śniegu oczekuje „sekund słońca w oknie
900 s". Dla danych godzinowych (0–3600 s) bez przeskalowania ułamek słońca byłby zawyżony do
4×.

W każdym kroku opad przekazywany do modelu to `intensywność · dt` [mm].

---

## 4. Model obiektu – temperatura szyny (transmitancje)

Temperatura szyny ogrzewanej (HRT) jest sumą dwóch niezależnych składowych:

```
HRT(t) = CRT(t) + T_grzania(t)
```

- **CRT** (szyna nieogrzewana, składowa pogodowa) zależy tylko od temperatury powietrza.
  W kodzie CRT to dokładnie składowa pogodowa, bez grzania.
- **T_grzania** zależy tylko od mocy grzania.

### 4.1 Składowa pogodowa (AT → CRT)

Człon pierwszego rzędu z zerem (lead-lag):

```
G_W(s) = K_W · (T_Z·s + 1) / (T₁_W·s + 1)
```

| Parametr | Wartość | Znaczenie |
|---|---|---|
| K_W | 1,09076 | wzmocnienie statyczne: w stanie ustalonym CRT ≈ 1,09 · AT |
| T₁_W | 5771,98 s (≈ 96 min) | stała czasu (bezwładność szyny względem powietrza) |
| T_Z | 780,03 s (≈ 13 min) | zero transmitancji |

### 4.2 Składowa grzania (moc → T_grzania)

Człon drugiego rzędu z opóźnieniem transportowym (SOPDT):

```
G_H(s) = K_H · e^(−L·s) / ((T₁_H·s + 1)(T₂_H·s + 1))
```

Wejście: moc u = moc_% / 100, czyli 0–1.

| Parametr | Wartość | Znaczenie |
|---|---|---|
| K_H | 51,116 °C | przyrost temperatury przy 100 % mocy w stanie ustalonym |
| T₁_H | 1120,91 s (≈ 18,7 min) | pierwsza stała czasu |
| T₂_H | 2450,97 s (≈ 40,9 min) | druga stała czasu |
| L_H | 1194,18 s (≈ 19,9 min) | opóźnienie transportowe |

### 4.3 Pochodzenie parametrów

Są to stałe zaszyte w kodzie, wcześniej **zidentyfikowane na rzeczywistym obiekcie**
(katalog `Identyfikacja_obiektu/`, wartości oznaczone w kodzie jako identyczne z `main_test.py`).
Sam autotest wewnątrz algorytmów adaptacyjnych identyfikuje obiekt na nowo z pomiarów, a nie
z tych stałych.

### 4.4 Dyskretyzacja i realizacja

- Oba człony są zamieniane na model stanowy (`tf2ss`) i dyskretyzowane metodą **ZOH**
  (`cont2discrete`) z krokiem `dt`.
- **Składowa pogodowa** jest liczona jednorazowo dla całej serii AT (`dlsim`), bo nie zależy
  od sterowania.
- **Składowa grzania** jest liczona rekurencyjnie w pętli: `x ← A·x + B·u_opóźnione`,
  `y = C·x + D·u_opóźnione`.
- **Opóźnienie transportowe** to przesunięcie w historii mocy o `round(L_H / dt)` próbek
  (przy `dt = 10 s` jest to 119 próbek, przy 1 s: 1194).
- Stan początkowy: HRT = 0,7 °C tylko w pierwszym kroku (odczyt dla sterownika), składowe
  liczone od zera.

### 4.5 Zaburzenia modelu (analiza wrażliwości)

Funkcja `przygotuj_modele_stanowe` przyjmuje procentowe zaburzenia `k_h_pct`, `t1_h_pct`,
`t2_h_pct`, `l_h_pct`. Zaburzany jest **prawdziwy** obiekt symulowany, a nie założenia
algorytmów – tak jak w realnym sprzęcie o innych parametrach niż projektowe. Test wrażliwości
na transmitancję ma 8 scenariuszy (na razie wyłączony z łańcucha zadań).

---

## 5. Model śniegu i lodu (bilans energii)

Zamiast prostego współczynnika topnienia użyto **punktowego bilansu energii pokrywy**
z mechanizmami przeportowanymi wprost z **pySnowClim** (A. Lute,
<https://github.com/abbylute/pySnowClim>). Krok równy `dt`, rdzeń liczony w numba (JIT),
stan w płaskiej tablicy `float64`.

### 5.1 Podział opadu na śnieg i deszcz

Regresja logistyczna Jenningsa i in. (2018), zależna od temperatury powietrza i wilgotności
względnej:

```
p_śnieg = 1 / (1 + exp(−10,04 + 1,41·AT + 0,09·RH))
śnieg_nowy = opad · p_śnieg,     deszcz = opad · (1 − p_śnieg)
```

RH jest liczone z AT i punktu rosy wzorem Magnusa/Boltona:
`RH = 100 · e_s(Td) / e_s(AT)`, `e_s(T) = 6,112 · exp(17,67·T / (T + 243,5))`.

### 5.2 Świeży śnieg i gęstość

- Gęstość świeżego śniegu (Anderson 1976 / Essery i in. 2013):
  `ρ_nowy = 50 + 1,7 · (max(AT, −15) + 15)^1,5` [kg/m³].
- Mieszanie z istniejącą pokrywą (Essery i in. 2013, eq. 17).
- Temperatura świeżego śniegu = min(0, punkt rosy), z niej zawartość zimna (cold content).
- Kompakcja (osiadanie) w czasie: Essery / Anderson / Boone.

### 5.3 Bilans energii pokrywy

Energia netto w kroku = krótkofalowe + długofalowe + turbulentne + ciepło deszczu +
przewodzenie od szyny:

| Składnik | Sposób liczenia |
|---|---|
| **Krótkofalowe** | Angström–Prescott (FAO-56): `Rs = (0,25 + 0,50·ułamek_słońca) · Ra`, `Ra` z geometrii słonecznej (deklinacja, kąt godzinny, dzień roku); netto = `Rs · (1 − albedo)` |
| **Długofalowe w dół** | Brutsaert (1975) dla czystego nieba plus zachmurzenie (Crawford & Duchon 1999): `ε_eff = c·1 + (1 − c)·ε_clear`, `c = 1 − ułamek_słońca`; w nocy używana ostatnia znana wartość dzienna zachmurzenia |
| **Długofalowe w górę** | Stefan–Boltzmann z emisyjnością 0,98 |
| **Turbulentne** (jawne i utajone) | bulk-aerodynamiczne, z korekcją stabilności liczbą Richardsona, zależne od wiatru, AT i wilgotności właściwej |
| **Ciepło deszczu** | `c_w · ρ_w · max(0, Td) · deszcz` |
| **Przewodzenie od szyny** | `G = h · max(0, HRT) · dt`, z `h = 0,01 kJ/m²/s/°C` |

Ostatni składnik jest głównym **sprzężeniem** modelu: zastępuje stały strumień gruntowy
z oryginału, bo źródłem ciepła pod pokrywą jest ogrzewana szyna.

### 5.4 Kaskada energii

Zawartość zimna → zamarzanie wody w pokrywie → topnienie. Do tego sublimacja i kondensacja ze
strumienia utajonego oraz zatrzymywanie wody ciekłej (maks. 10 % SWE, nadmiar odpływa).

### 5.5 Albedo

Wariant VIC: starzenie się śniegu osobno dla fazy zimnej i topniejącej, odświeżenie po
świeżym opadzie (próg 0,01 m sprawdzany na liczniku skumulowanym, bo próg dla jednego kroku
byłby bez sensu przy `dt` rzędu sekund), zanik ku albedu gruntu (0,25) przy cienkiej pokrywie.
Albedo maksymalne 0,85.

### 5.6 Lód z marznącego deszczu

Osobny, prosty kanał: gdy na szynie nie ma śniegu, pada deszcz, a HRT ≤ 0 °C, warstwa lodu
rośnie o wielkość opadu. Topi się przewodzeniem od szyny, gdy HRT > 0 °C. PySnowClim nie
modeluje oblodzenia obiektów, dlatego to rozszerzenie własne.

### 5.7 Stałe modelu

| Stała | Wartość |
|---|---|
| Emisyjność śniegu | 0,98 |
| Albedo gruntu / maksymalne | 0,25 / 0,85 |
| Wysokość pomiaru wiatru / temperatury | 10 m / 2 m |
| Szorstkość aerodynamiczna z0 / termiczna zh | 1e-5 m / 1e-6 m |
| Domyślna gęstość śniegu | 250 kg/m³ |
| Maks. udział wody ciekłej | 0,10 |
| Współczynnik kontaktu szyna–śnieg h | 0,01 kJ/m²/s/°C (**do kalibracji w terenie**) |
| Ciśnienie (stałe) | 1009 hPa |
| Szerokość geograficzna (stała) | 54,1° (Suwałki) |

---

## 6. Co widzi sterownik

W każdym kroku algorytm dostaje wiersz z polami (nazwy jak w realnym sterowniku):

| Pole | Skąd |
|---|---|
| `HRT_temp_grzana` | HRT z symulacji (CRT + składowa grzania) |
| `CRT_temp_niegrzana` | składowa pogodowa |
| `AT_temp_powietrza` | z danych pogodowych |
| `RH_wilgotnosc_wzgledna` | `100 − 5·(AT − Td)`, obcięta do 0–100 % (uproszczenie) |
| `PRECIP_opad` | opad, gdy AT > 0 °C (deszcz) |
| `SNOW_snieg` | opad, gdy AT ≤ 0 °C (śnieg) |
| `PRES_cisnienie` | stałe 1009 hPa |
| `PWR_L1`, `PWR_L2` | 0 (moc mierzona nie jest symulowana) |
| `SNIEG_GRUBOSC_MM` | grubość śniegu z modelu, z kroku **poprzedniego** |
| `PUNKT_ROSY_C`, `WIATR_M_S` | z danych pogodowych |

**Uwaga:** sterownik dostaje twardy podział opadu (próg 0 °C), a sam model śniegu używa
podziału logistycznego (5.1). To celowe: sterownik działa na prostej regule jak realny czujnik,
a fizyka liczy to, co naprawdę spada.

Sterownik może dodatkowo dostać **zafałszowane** odczyty (`fault_injector`: bias, szum,
rozłączenie czujnika), a fizyka nadal liczy z prawdziwych wartości. To tak jak w realnej
awarii czujnika: rzeczywistość dalej się dzieje, sterownik o niej nie wie.

Moc na wyjściu jest przeliczana na energię: `E = (moc_% / 100) · 14 kW · dt / 3600` [kWh],
przy znamionowej mocy grzałki 14 kW.

---

## 7. Bezpiecznik parytetu względem normy

Aby porównanie algorytmów nie premiowało niebezpiecznego „oszczędzania" na śniegu, większość
algorytmów pracuje pod **bezpiecznikiem** (`bezpiecznik: True` w `rejestr_algorytmow.py`):

1. Najpierw liczony jest przebieg **algorytmu z normy** (`algorytm_z_normy`, wg LET-1 PKP PLK).
   Zapisujemy jego grubość śniegu i moc w każdym kroku jako referencję.
2. W każdym kroku, w którym leży śnieg (u nas **lub** u normy), wymuszamy
   `moc = max(moc_algorytmu, moc_normy)`.
3. Ochrona zaczyna się **z wyprzedzeniem** o czas opóźnienia obiektu (`round(L/dt)` kroków),
   bo znamy całą przyszłą trajektorię normy. Bez tego stan cieplny wchodziłby w zdarzenie
   śniegowe z innym zapasem ciepła niż norma.

Przy identycznej pogodzie i liniowym, monotonicznym obiekcie (nieujemna odpowiedź impulsowa
SOPDT) gwarantuje to, że grubość śniegu nie wyprzedzi normy. Oszczędności zostają poza
śniegiem (suchy mróz, ochrona przed −10 °C). Liczba użyć bezpiecznika jest raportowana
(`zabezpieczen_normy_uzytych`). Sama norma i algorytmy bez flagi tego nie mają.

---

## 8. Metryki wyjściowe

Liczone w tej samej pętli, z prawdziwych (nie zafałszowanych) wartości:

- **Energia** [kWh], średnia moc [%], liczba przełączeń.
- **Śnieg i lód**: maksymalna grubość [mm], godziny ze śniegiem.
- **Temperatura szyny**: minimum i maksimum HRT.
- **IAE / ISE / ITAE**: jakość regulacji względem własnego celu algorytmu, tylko przy
  `need_heat=True` (ITAE liczone od początku każdego epizodu grzania).
- **Kara bezpieczeństwa** [°C·s], suma trzech składowych całkowanych w czasie:
  1. zalegający śnieg powyżej 5 mm (waga 0,05 °C/mm),
  2. marznący deszcz przy HRT < +2 °C (deficyt do 2 °C),
  3. HRT poniżej dolnego limitu −10 °C (deficyt).
  Do tego liczba **epizodów** spadku poniżej −10 °C. Wagi mają scenariusze wrażliwości ±50 %
  (`KARA_WAGI_SCENARIUSZE`), liczone równolegle, bez ponownej symulacji.
- **FLOPs** rzeczywiste liczone przez sam kontroler oraz budżet przełączeń przekaźnika
  (całkowity budżet życiowy 500 000, dzienny limit przełączeń 100).

Szczegóły: `notatki/kara_bezpieczenstwa.md`, `notatki/IAE_ISE_ITAE.md`, `notatki/FLOPs.md`.

---

## 9. Organizacja przebiegów

- Każde zadanie (lokalizacja × algorytm) jest **niezależne**: samo wczytuje pogodę, samo liczy
  normę jako referencję bezpiecznika i samo symuluje. To niewielki narzut, ale nie ma
  współdzielonej pamięci i skaluje się do dowolnej liczby procesów (`ProcessPoolExecutor`,
  liczba wątków z `SLURM_CPUS_PER_TASK`).
- Wyniki zbiorcze idą do `PRZEGLAD_ZBIORCZY.csv` i Excela, a trajektorie per zadanie do CSV
  (zapisywane co 600 s, ale statystyki są liczone z pełnej rozdzielczości obliczeń).
- **Wznawianie**: przerwany przebieg (limit czasu, awaria węzła) można uruchomić ponownie,
  bo policzone pary (lokalizacja, algorytm) są pomijane (`SZYNA_WZNOW=1`).
- **Powtarzalność**: dane pogodowe są stałymi plikami, obiekt jest deterministyczny. Jedyna
  losowość to szum w testach szumu czujników i losowanie lokalizacji, oba z ustalonym ziarnem
  (`SZYNA_SEED_LOKALIZACJI_SZUM`, ziarno bazowe szumu).
- Rozgrzewka kompilacji numba w procesie głównym przed startem puli.

---

## 10. Ograniczenia i uproszczenia (do opisania w pracy)

1. **Dane to reanaliza ERA5-Land**, nie pomiary ze stacji. Dla odległych lokalizacji błąd
   jest większy. Wrocław pochodzi z innego źródła (Historical Forecast) i z innego sezonu.
2. **Stała szerokość geograficzna 54,1° w modelu śniegu** dla wszystkich lokalizacji. Wpływa
   na geometrię słoneczną i promieniowanie krótkofalowe (dla Sodankylä czy Quebecu jest to
   przybliżenie).
3. **Współczynnik kontaktu szyna–śnieg h = 0,01 nie jest skalibrowany** do obserwacji zaniku
   śniegu na szynie – kod sam to zaznacza.
4. **Stałe ciśnienie 1009 hPa** i **uproszczona wilgotność** dla sterownika
   (`100 − 5·(AT − Td)`).
5. **Wiatr nie wchodzi do transmitancji szyny** – wpływa tylko na bilans energii śniegu.
   Podobnie nasłonecznienie: nie jest wejściem transmitancji.
6. **Opad stały w oknie źródłowym** (godzina) – nie ma ciągłej krzywej intensywności ani
   ulewy o krótszej skali czasu.
7. **Krok symulacji 10 s** zamiast 1 s w przeglądach – zmierzony wpływ ok. 0,02 % w energii.
8. **Transmitancje stałe w czasie** (jeden obiekt, parametry niezmienne – brak zależności od
   temperatury, wiatru czy zalegającego śniegu). Test wrażliwości sprawdza zaburzenia
   ±procentowe, ale nie zmienność w czasie.
9. **Śnieg nie wpływa zwrotnie na temperaturę szyny** (brak izolacji cieplnej pokrywy) –
   sprzężenie jest jednokierunkowe: szyna → śnieg.
10. **Bezpiecznik parytetu jest artefaktem porównania**, nie elementem realnego sterownika –
    służy do uczciwego porównania energii przy tym samym poziomie bezpieczeństwa śnieżnego.
