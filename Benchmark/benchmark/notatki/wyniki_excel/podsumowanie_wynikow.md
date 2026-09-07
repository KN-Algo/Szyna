# Podsumowanie_wynikow.xlsx

Generator: `generuj_excel_podsumowanie.py` (funkcja `main()`), wołany automatycznie na
końcu `test_wszystkie_rownolegle.py` i `test_wszystkie_algorytmy_wszystkie_lokalizacje.py`.
Źródło danych: `PRZEGLAD_ZBIORCZY.csv` w tym samym folderze (jeden wiersz = jedna
kombinacja lokalizacja+algorytm, ewentualnie x scenariusz transmitancji, jeśli to wynik z
`test_wszystkie_rownolegle.py` uruchomionego ze zmiennymi `SZYNA_PERTURB_*`).

**To jest plik generowany przez WSZYSTKIE scenariusze "pełnego przeglądu"** - główny
wynik (`wyniki/przeglad_wielu_lokalizacji/`) i wszystkie 7 scenariuszy wrażliwości
transmitancji (`nominal`/`K_plus5`/.../`K10_T1_10`) mają IDENTYCZNĄ strukturę pliku,
różnią się tylko treścią (jaki zestaw uruchomień trafił do `PRZEGLAD_ZBIORCZY.csv`).

## Zakładka "Dane"

Jeden wiersz = jeden przebieg symulacji (lokalizacja x algorytm). Kolumny (litera w
arkuszu → skąd):

| Kolumna | Skąd | Jak liczona |
|---|---|---|
| A Lokalizacja | `parsuj_lokalizacje(df['lokalizacja'])` | nazwa miasta wyciągnięta regexem z nazwy pliku pogodowego (np. `abisko_60min_2021` → `Abisko`) |
| B Interwał | j.w. | `60min`/`15min` - natywny krok źródłowego pliku pogodowego |
| C Rok | j.w. | rok z nazwy pliku |
| D Algorytm | `NAZWY_ALGORYTMOW[df['name']]` | czytelna nazwa algorytmu (mapowanie klucz→etykieta z `Algorytmy/rejestr_algorytmow.py`) |
| E Energia (kWh) | `stats['energia_kwh']` z `symulacja_fizyczna.uruchom_kontroler` | `Σ (moc_% / 100) × 14 kW × (dt / 3600)` po WSZYSTKICH krokach symulacji (`Energia_kWh_1s` zsumowana) |
| F Przełączenia | `stats['przelaczenia']` | licznik zmian znaku mocy (0↔>0) między kolejnymi krokami - detekcja zbocza, NIE suma kroków w stanie ON |
| G Max śnieg (mm) | `stats['max_snieg_mm']` | maksimum PRAWDZIWEJ (fizycznej) grubości śniegu w całym przebiegu (`SnowClimPhysicalModel`), niezależnie od tego, co widział kontroler |
| H Max HRT (°C) | `stats['max_hrt']` | maksimum rzeczywistej temperatury szyny ogrzewanej |
| I FLOPs (zmierzone) | `stats['flops_rzeczywiste']` | rzeczywisty licznik operacji z `rdzen_kontrolera.KontrolerBazowy._dodaj_flopy`, wołany w KAŻDYM miejscu logiki decyzyjnej - patrz `../FLOPs.md` |
| J IAE (°C·s) | `stats['iae']` | patrz `../IAE_ISE_ITAE.md` |
| K ISE (°C²·s) | `stats['ise']` | j.w. |
| L ITAE (°C·s²) | `stats['itae']` | j.w. |
| M Min HRT (°C) | `stats['min_hrt']` | minimum rzeczywistej HRT w całym przebiegu |
| N Kara bezpieczeństwa (°C·s) | `stats['kara_bezpieczenstwa']` | patrz `../kara_bezpieczenstwa.md` |
| O Epizody HRT<-10°C | `stats['epizody_ponizej_floor']` | j.w. - licznik ZDARZEŃ (detekcja zbocza), nie kroków |
| P/Q/R IAE/ISE/ITAE % vs norma LET-1 | policzone w `generuj_excel_podsumowanie.py` (NIE formuła Excela - literalna wartość) | `(wartość − wartość_algorytm_z_normy) / wartość_algorytm_z_normy × 100`, baseline osobny DLA KAŻDEJ (Lokalizacja, Interwał, Rok) - patrz `../IAE_ISE_ITAE.md` |
| S Kara bezp. % vs norma LET-1 | j.w. | j.w., dla kolumny N - patrz `../kara_bezpieczenstwa.md` |

Wiersze z Max HRT > 35°C LUB kara bezpieczeństwa > 0 są podświetlone na czerwono
(`FormulaRule`, `$H2>35` lub `$N2>0`).

## Zakładka "Podsumowanie_algorytmy"

Jeden wiersz = jeden algorytm (z `NAZWY_ALGORYTMOW`, zawsze WSZYSTKIE, nawet jeśli dany
algorytm nie ma wierszy w "Dane" - wtedy formuły zwrócą błąd/puste). **WSZYSTKIE kolumny
2-19 to FORMUŁY EXCELA** odwołujące się do zakładki "Dane" (patrz uwaga w README o
cache'owanych wartościach formuł) - nie ma tu żadnej wartości policzonej wprost w
Pythonie.

| Kolumna | Formuła | Znaczenie |
|---|---|---|
| B Średnia energia | `AVERAGEIF(Dane!D, algorytm, Dane!E)` | średnia energia tego algorytmu po WSZYSTKICH jego wierszach (lokalizacjach) |
| C/D Min/Max energia | `MINIFS`/`MAXIFS` analogicznie | najlepszy/najgorszy pojedynczy przypadek energetyczny |
| E Średnie przełączenia | `AVERAGEIF(..., Dane!F)` | |
| F Średni max śnieg | `AVERAGEIF(..., Dane!G)` | |
| G Średni max HRT | `AVERAGEIF(..., Dane!H)` | |
| H Liczba przypadków przegrzania | `COUNTIFS(Dane!D=algorytm, Dane!H>35)` | ile wierszy TEGO algorytmu ma Max HRT>35°C |
| I/J/K Przełączenia/dzień, /rok, %budżetu | liczone w Pythonie (NIE formuła), TYLKO dla algorytmów z dyskretnym wyjściem (`_czy_dyskretny` - histereza/FL2/FL2v2/FL3, NIE PID/FL1 ciągłe) | `śr.przełączenia / śr.dni × 365`, podzielone przez `BUDZET_PRZELACZEN_CALKOWITY` (500 000, żywotność mechaniczna przekaźnika) |
| L Max śnieg GLOBALNIE | `MAXIFS(Dane!G, Dane!D=algorytm)` | najgorszy POJEDYNCZY przypadek śniegu tego algorytmu ze WSZYSTKICH lokalizacji (nie średnia!) |
| M/N/O Średnie IAE/ISE/ITAE | `AVERAGEIF(..., Dane!J/K/L)` | |
| P Średnia kara bezpieczeństwa | `AVERAGEIF(..., Dane!N)` | |
| Q Min HRT GLOBALNIE | `MINIFS(Dane!M, Dane!D=algorytm)` | najzimniejszy POJEDYNCZY przypadek tego algorytmu ze wszystkich lokalizacji |
| R Lokalizacja najgorszego przypadku | `INDEX/MATCH` z podwójnym kryterium (algorytm=A{i} ORAZ Dane!M=Q{i}), przez "podwójny INDEX" zamiast formuły tablicowej CSE | KTÓRA lokalizacja/rok odpowiada wartości w kolumnie Q tego wiersza |
| S Suma epizodów HRT<-10°C | `SUMIF(Dane!D=algorytm, Dane!O)` | suma (nie średnia!) po wszystkich lokalizacjach tego algorytmu |

Kolory (skala warunkowa min→max, `ColorScaleRule`): zielony=dobrze, czerwony=źle dla
większości kolumn (B,E,F,G,H,L,M,N,O,P,S - niska wartość = zielona). **Wyjątek: kolumna Q
(Min HRT GLOBALNIE) ma ODWRÓCONĄ skalę** (czerwony=min/zimno=źle, zielony=max/ciepło=OK),
bo tu WIĘKSZA (mniej ujemna) wartość jest lepsza - jedyna taka kolumna w tej zakładce,
łatwo to przeoczyć czytając wykres kolorów.

## Zakładka "Wrazliwosc_wag_kary" (jeśli obecne kolumny `kara_bezpieczenstwa__*`)

Pomijana bez błędu, gdy dane pochodzą sprzed dodania tej analizy (2026-09-07). Sprawdza, czy
RANKING algorytmów wg kary bezpieczeństwa jest odporny na dobór wag trzech składowych
(śnieg/marznący deszcz/floor -10°C) - patrz pełny opis w
[../kara_bezpieczenstwa.md](../kara_bezpieczenstwa.md#analiza-wrażliwości-wag-czy-ranking-jest-odporny-na-dobór-wag).
1 wiersz na algorytm: kara nominalna + ranga, potem kara + Δ ranga dla każdego z 6 scenariuszy
(±50% na jednej wadze na raz), na dole korelacja rang Spearmana per scenariusz (literalne
wartości, liczone tu w Pythonie, NIE formuły Excela w odróżnieniu od "Podsumowanie_algorytmy"
niżej).

## Zakładka "Podsumowanie_lokalizacje"

Macierz: wiersze = lokalizacje (unikalne wartości `Lokalizacja` z "Dane"), kolumny =
algorytmy. Każda komórka to `AVERAGEIFS(Dane!E, Dane!A=lokalizacja, Dane!D=algorytm)` -
średnia energia TEGO algorytmu w TEJ lokalizacji (uśredniona po latach/interwałach, jeśli
lokalizacja ma kilka plików). Dwie dodatkowe kolumny per wiersz:
- **Najlepszy algorytm** - `INDEX/MATCH` znajdujący nazwę algorytmu z minimalną energią w
  danym wierszu.
- **Oszczędność vs. bazowy (%)** - `(energia_bazowa - min_energia) / energia_bazowa`,
  gdzie "bazowy" = `ALGORYTM_BAZOWY` (stała w kodzie, domyślnie `algorytm_z_normy`).

## Zakładka "Opisy_algorytmow"

Statyczny opis KAŻDEGO algorytmu wprost z `Algorytmy/rejestr_algorytmow.py` (pola `typ`/
`cel`/`adaptacyjny`/`opis` ze słownika `ALGORYTMY`) - nie liczy nic, tylko kopiuje
metadane z kodu, więc zawsze spójne z rejestrem. Wiersze z `adaptacyjny=True` (mają
autotest SOPDT) podświetlone na zielono.

## Zakładka "Zlozonosc_obliczeniowa"

Też statyczna kopia pól `zlozonosc_czasowa`/`flops_na_krok`/`zlozonosc_pamieciowa`/
`pamiec_przyblizona_mb` z rejestru - **szacunki analizą kodu, NIE pomiar** (w
odróżnieniu od kolumny "FLOPs (zmierzone)" w zakładce "Dane", która JEST realnym
pomiarem z `_dodaj_flopy`). "Łączne FLOPs" = szacunek/krok × liczba kroków w oknie
testowym (median). Patrz `../FLOPs.md` po pełne wyjaśnienie różnicy analityczne vs
zmierzone.

## Zakładka "Uczenie_adaptacyjne" / "Strojenie_progow_ryzyka" (jeśli obecne)

Osobne zakładki dla algorytmów z historią uczenia/strojenia (`nauka_kary_*` -
"Uczenie_adaptacyjne", `risk_function_pid_auto` - "Strojenie_progow_ryzyka") - budowane
TYLKO jeśli w folderze wyników istnieją odpowiednie pliki `*_historia_*.csv` (zapisywane
przez kontroler przy każdej aktualizacji współczynnika/progu). Zawierają surowy przebieg
uczenia (numer aktualizacji → wartość współczynnika/koszt) + wykres liniowy dla PIERWSZEJ
napotkanej lokalizacji jako podgląd.

## Zakładka "Wnioski"

**Cały tekst to gotowe stringi Pythona (NIE formuły)** - bezpieczne do odczytu przez
dowolny program bez otwierania w Excelu. Sekcje 1-4 (Energia/Stabilność/Anomalie/
Rekomendacja) mają częściowo ZAKODOWANE NA SZTYWNO nazwy algorytmów (np. odwołania do
"Funkcja ryzyka (PID)" wprost w kodzie) - napisane pod wczesną, mniejszą wersję zestawu
algorytmów, więc mogą wymagać ręcznej korekty tekstu przy dużych zmianach w rejestrze
(nie są w pełni dynamiczne jak sekcja 5). **Sekcja "5) NARUSZENIA BEZPIECZEŃSTWA" jest w
pełni dynamiczna** (żadnych nazw na sztywno) - per-algorytm suma kary bezpieczeństwa/
epizodów/najzimniejszy HRT + top-5 najgorszych pojedynczych przypadków, patrz
`../kara_bezpieczenstwa.md`.
