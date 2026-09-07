# Podsumowanie_MASTER.xlsx

Generator: `generuj_excel_master.py`, wołany na końcu `uruchom_wszystkie_testy.py` (albo
osobno, w dowolnym momencie). **Nie liczy niczego nowego** - konsoliduje NAGŁÓWKOWE wyniki
z plików innych testów w JEDEN skoroszyt, jedna zakładka na test, żeby nie trzeba było
otwierać 7 osobnych plików Excela po kolei. Każda zakładka jest POMIJANA BEZ BŁĘDU, jeśli
dany test jeszcze nie był uruchomiony (brak pliku CSV źródłowego) - stąd "Podsumowanie
MASTER" zbudowane wcześnie w trakcie pełnego przebiegu testów może mieć mniej zakładek
niż finalne.

## Zakładka "Indeks" (zawsze pierwsza)

Tabela: która zakładka odpowiada któremu testowi, status ("dostępne" / "brak danych -
test nieuruchomiony", kolor czerwony dla brakujących), i ścieżka do folderu ze SUROWYMI
(pełnymi) danymi tego testu - MASTER pokazuje tylko podsumowanie, pełne dane zawsze
zostają w oryginalnym pliku. Osobna lista na dole: ścieżki do plików
`Diagnostyka_*.xlsx` (mają WŁASNY format, nie pasują do wspólnej struktury reszty, patrz
`diagnostyka_funkcji_ryzyka.md` - MASTER tylko je WYLICZA, nie kopiuje zawartości).

## Pozostałe zakładki - każda to `groupby(...).agg(...)` z surowego CSV danego testu

Wszystkie wartości są LITERALNE (policzone w Pythonie przez pandas), nie formuły Excela.

| Zakładka | Źródło CSV | Agregacja |
|---|---|---|
| Glowny_przeglad | `przeglad_wielu_lokalizacji/PRZEGLAD_ZBIORCZY.csv` | `groupby('name')`: średnia energia, średnie przełączenia, MAX (nie średnia) śniegu globalnie, średnie IAE, liczba unikalnych lokalizacji - posortowane rosnąco wg energii |
| Wrazliwosc_transmitancji | `wrazliwosc_2lokalizacje/WRAZLIWOSC_ZBIORCZY.csv` | odchylenie energii vs `nominal` bez szumu (jak w `podsumowanie_wrazliwosc.md`), uśrednione WARTOŚCIĄ BEZWZGLĘDNĄ per algorytm, + % udanych autotestów (`autotest_fit_ok`), + średni bezwzględny błąd identyfikacji K |
| Krok_sterowania | `wrazliwosc_kroku/WRAZLIWOSC_KROKU_ZBIORCZY.csv` | `groupby(['name','krok_s'])`: średnia energia i IAE - to ta sama agregacja co zakładka "Srednie_wg_kroku" w `Podsumowanie_kroku_sterowania.xlsx`, tylko skopiowana tutaj bez wykresu |
| Awarie_czujnikow | `awarie_czujnikow/AWARIE_ZBIORCZY.csv` | odchylenie energii vs `brak_awarii` (jak w `podsumowanie_awarii.md`), uśrednione i zmaksymalizowane WARTOŚCIĄ BEZWZGLĘDNĄ per algorytm (kolumny `odchylenie_sredni_abs_pct`/`odchylenie_max_abs_pct`) |
| Szum_wielu_czujnikow | `szum_wielu_czujnikow/SZUM_ZBIORCZY.csv` | analogicznie do Awarie_czujnikow + liczba unikalnych scenariuszy szumu na algorytm |
| Prognoza_opadow | `Podsumowanie_prognozy_opadow.xlsx` (zakładka `Wyniki_lokalizacje`, PIERWSZE 9 kolumn) | **UWAGA: to jedyna zakładka MASTER, która NIE liczy nic sama, tylko KOPIUJE komórki** z innego już-gotowego pliku Excela (`load_workbook(..., data_only=True)`), więc jeśli źródłowy `Podsumowanie_prognozy_opadow.xlsx` nigdy nie był otworzony w prawdziwym Excelu (patrz uwaga o cache'owanych formułach w `README.md`), ta zakładka w MASTER może wyjść PUSTA nawet gdy plik źródłowy istnieje - w tym konkretnym pliku wszystkie kolumny są jednak literalne (nie formuły), więc problem praktycznie nie występuje |

## Jak czytać - główny cel tego pliku

To NIE jest zamiennik pełnej analizy - to szybki "czy w ogóle wszystko się policzyło i
jak z grubsza wygląda ranking" przegląd. Do dokładnych liczb per scenariusz/lokalizację
zawsze wróć do oryginalnego pliku danego testu (ścieżka podana w zakładce "Indeks" i na
górze każdej zakładki danych, komórka "Pełne dane: ...").
