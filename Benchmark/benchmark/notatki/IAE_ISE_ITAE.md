# Jak liczymy IAE, ISE i ITAE

Klasyczne wskaźniki jakości regulacji — mierzą, jak dobrze RZECZYWISTA temperatura szyny ogrzewanej
(HRT) nadąża za temperaturą ZADANĄ (`target_temperature`) wyliczaną przez algorytm. Liczone bezpośrednio
w **głównej pętli symulacji** (`symulacja_fizyczna.uruchom_kontroler`), automatycznie dla WSZYSTKICH
30 algorytmów, tym samym mechanizmem — nie ma osobnej ścieżki liczenia per algorytm.

## Definicje

Dla błędu `e(t) = target_temperature(t) − HRT_rzeczywista(t)`, scałkowanego po czasie `dt`:

| Skrót | Wzór | Jednostka w tym projekcie | Co mówi |
|---|---|---|---|
| **IAE** (Integral of Absolute Error) | `Σ \|e(t)\| · dt` | °C·s | Łączna "powierzchnia" błędu — im mniej, tym ciaśniej regulator trzyma się celu |
| **ISE** (Integral of Squared Error) | `Σ e(t)² · dt` | °C²·s | Jak IAE, ale kwadrat błędu — mocniej karze DUŻE, pojedyncze odchylenia niż wiele małych |
| **ITAE** (Integral of Time-weighted Absolute Error) | `Σ t_epizodu(t) · \|e(t)\| · dt` | °C·s² | Jak IAE, ale z wagą rosnącą w czasie OD POCZĄTKU epizodu grzania — karze WOLNE dochodzenie do celu bardziej niż chwilowe, szybko skorygowane odchylenie |

## Gdzie dokładnie w kodzie

`symulacja_fizyczna.uruchom_kontroler`, w pętli głównej (krok po kroku), zaraz po policzeniu
`current_hrt` (prawdziwej, fizycznej temperatury szyny):

```python
if diagnostics is not None and diagnostics.get('need_heat'):
    episode_time_s = episode_time_s + dt if need_heat_poprzednio else dt
    need_heat_poprzednio = True
    target_temperature = diagnostics.get('target_temperature')
    if target_temperature is not None:
        error = float(target_temperature) - current_hrt
        iae_suma += abs(error) * dt
        ise_suma += (error * error) * dt
        itae_suma += episode_time_s * abs(error) * dt
        iae_liczba_krokow += 1
else:
    need_heat_poprzednio = False
    episode_time_s = 0.0
```

`diagnostics` to drugi element krotki `(moc_procent, diagnostics)`, którą **każdy** z 30 algorytmów
teraz zwraca (`_get_power` w `symulacja_fizyczna.py` obsługuje to jednolicie). Wynik trafia do
`stats['iae']`/`stats['ise']`/`stats['itae']` na końcu funkcji, stamtąd do `PRZEGLAD_ZBIORCZY.csv`
(główny przegląd), `AWARIE_ZBIORCZY.csv` (test awarii czujników) i kolumn `IAE`/`ISE`/`ITAE` w Excelu
(zakładki "Dane" i "Podsumowanie_algorytmy" w `Podsumowanie_wynikow.xlsx`).

## Dwie ważne decyzje projektowe

**1. Liczone TYLKO gdy `need_heat=True`.** Gdy algorytm nie widzi zagrożenia, ustawia
`target_temperature = HRT_bieżące` (czyli "cel = to, co jest teraz") — błąd byłby wtedy ZERO z
definicji, nie dlatego, że regulacja jest dobra, tylko dlatego, że nie ma czego regulować. Wliczanie
takich kroków rozwadniałoby IAE/ISE/ITAE fikcyjnymi zerami i utrudniało porównanie algorytmów, które
różnią się tym, JAK CZĘSTO w ogóle uznają, że trzeba grzać.

**2. ITAE liczone względem czasu OD POCZĄTKU BIEŻĄCEGO EPIZODU grzania**, nie względem
bezwzględnego czasu symulacji. `episode_time_s` resetuje się do zera przy każdym przejściu
`need_heat: False → True` i rośnie tylko, dopóki `need_heat` zostaje `True`. Gdyby liczyć względem
czasu symulacji, miesięczny/roczny przebieg byłby zdominowany samą swoją długością (błąd w
tysięcznym kroku ważyłby tysiąc razy więcej niż identyczny błąd w pierwszym) — a chodzi o to, żeby
ITAE karało WOLNE dochodzenie do celu W KAŻDYM epizodzie z osobna, nie o wagę wynikającą z tego, kiedy
w symulacji epizod akurat wypadł.

## Skąd `target_temperature` bierze się dla KAŻDEGO algorytmu

Nie wszystkie algorytmy miały pierwotnie jawny, ciągły cel w swojej diagnostyce — dopisane
2026-09-02, na życzenie użytkownika ("dla każdego algorytmu, w głównej pętli"):

| Rodzina | `target_temperature` = | `need_heat` = |
|---|---|---|
| `risk_function*`, `fuzzy_ryzyko_*`, `norma_pid`, `fuzzy_normy_*`, `nauka_kary*` | jawny setpoint z kaskady/progów (już istniał) | jawna flaga z kaskady/progów (już istniała) |
| `compute_control`, `compute_control_gorski`, `algorytm_z_normy` (histereza) | próg WYŁĄCZENIA aktywnej gałęzi (opady/suchy mróz) — to ten próg kończy epizod grzania, więc jest naturalnym "celem" | `heating_on` (aktualny stan przekaźnika) |
| `fuzzy_logic_1/2/2v2/3` (silnik rozmyty, stały cel) | ich własny stały `T_ZADANA` (domyślnie 3.0°C) | zawsze `True` (silnik dąży do celu bez przerwy, brak stanu zał./wył.) |

Patrz `notatki/algorytmy/*.md` (sekcja "Diagnostyka (IAE/ISE/ITAE)" w każdym pliku) po szczegóły per
algorytm.

## % względem normy LET-1 (punkt odniesienia)

Dopisane 2026-09-03, na życzenie użytkownika ("niech norma będzie naszym punktem
odniesienia do całości"). W zakładce "Dane" (`Podsumowanie_wynikow.xlsx`), obok surowych
IAE/ISE/ITAE, trzy dodatkowe kolumny: **"IAE/ISE/ITAE % vs norma LET-1"** =
`(wartość_algorytmu − wartość_algorytm_z_normy) / wartość_algorytm_z_normy × 100`, gdzie
`algorytm_z_normy` (etykieta w Excelu: "Automat z normy [bazowy]") to WŁASNY baseline DLA
KAŻDEJ (Lokalizacja, Interwał, Rok) z osobna — nie jeden globalny numer — bo jakość
regulacji zależy silnie od konkretnej pogody danego przebiegu, nie tylko od algorytmu.
Dla wiersza SAMEJ normy wynik to zawsze dokładnie 0%. Puste (brak wartości), gdy baseline
tej lokalizacji/roku wynosi 0 lub jest nieobecny (dzielenie przez zero nie ma sensu).

Przykład realny (smoke test, Ojmiakon): `Fuzzy Logic 1` ma IAE 206.8% WYŻSZE niż norma w
tej samej lokalizacji — norma (regulacja progowa/kalendarzowa) i tak "wygrywa" jakością
śledzenia z algorytmem o stałym celu 3°C, bo norma nie próbuje trzymać jednej stałej
temperatury przez cały czas grzania.

## Jak czytać wyniki — jedna pułapka

IAE/ISE/ITAE są sumami (nie średnimi) po WSZYSTKICH krokach z `need_heat=True` w danym przebiegu —
algorytm, który grzeje CZĘŚCIEJ (dłuższy łączny czas `need_heat=True`), będzie miał WIĘKSZE surowe IAE
nawet przy identycznej JAKOŚCI regulacji na krok, po prostu dlatego, że sumuje po większej liczbie
kroków. Przy porównywaniu algorytmów o różnej "agresywności" włączania grzania (np. wariant `_opad`
z furtką ucieczki vs. bez niej) sensowniejsze bywa IAE/liczba_kroków (błąd średni na krok) niż surowe
IAE — żadna z zakładek Excela tego jeszcze nie liczy automatycznie, trzeba by dorobić kolumnę dzielącą
przez `godziny_ze_sniegiem`/czas trwania need_heat, gdyby to było potrzebne.
