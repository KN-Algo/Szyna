# Podsumowanie_kroku_sterowania.xlsx

Generator: funkcja `zbuduj_excel()` wewnątrz `test_wrazliwosc_kroku_sterowania.py` (nie
osobny plik `generuj_excel_*.py`, w odróżnieniu od większości innych testów). Sprawdza,
jak bardzo wynik zależy od częstotliwości przeliczania sterowania (`dt` = krok
symulacji), przy STAŁEJ fizyce - domyślnie 3 algorytmy (`fuzzy_normy_2v2`,
`fuzzy_ryzyko_2v2_opad`, `nauka_kary_opad` - zwycięzcy wstępnego rankingu, patrz
`../../AGENTS.md`) x 5 kroków (1/10/60/300/600 sekund) x wszystkie 43 lokalizacje.

## Zakładka "Wyniki" - surowa tabela

Jeden wiersz na (lokalizacja, algorytm, krok_s). Kolumny: `lokalizacja`, `name`
(algorytm), `krok_s`, `energia_kwh`, `przelaczenia`, `max_snieg_mm`, `max_hrt`, `min_hrt`,
`iae`, `ise`, `itae` - wprost ze `stats` zwróconego przez `symulacja_fizyczna.
uruchom_kontroler` dla TEGO konkretnego kroku symulacji (im mniejszy krok, tym więcej
punktów całkowania w IAE/ISE/ITAE i więcej okazji do przełączenia - to jest DOKŁADNIE to,
co ta zakładka bada: czy wynik się stabilizuje, czy zależy od kroku).

## Zakładka "Srednie_wg_kroku"

Agregacja `df.groupby(['name', 'krok_s']).agg(mean)` policzona w Pythonie (literalne
wartości, nie formuły Excela) - kolumny "Średnia energia (kWh)" i "Średnie IAE (°C·s)",
uśrednione po WSZYSTKICH 43 lokalizacjach dla danej pary (algorytm, krok). Zawiera
wbudowany wykres liniowy ("Średnia energia vs krok sterowania") - jedna linia na
algorytm, oś X = krok w sekundach, zbudowany z pomocniczej tabelki zapisanej niżej w tym
samym arkuszu (kolumny E/F, poza widocznym obszarem danych).

**Jak czytać**: jeśli linia dla danego algorytmu jest prawie płaska, krok sterowania nie
ma dla niego znaczenia energetycznie - patrz realny wynik klastra w
`../../wyniki/_analiza_klastra.md` (rozstęp energii tylko 1.4-4.5% między najlepszym a
najgorszym krokiem dla wszystkich 3 testowanych algorytmów, ale IAE degraduje się
wyraźniej przy grubszym kroku, do +14.6% dla `nauka_kary_opad` między 60s a 300s) - czyli
sam wykres energii może wyglądać "spokojnie", mimo że jakość śledzenia (IAE, NIE
pokazane na tym konkretnym wykresie, tylko w tabeli) już wyraźnie się pogarsza.
