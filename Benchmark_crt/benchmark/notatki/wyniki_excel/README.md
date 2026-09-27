# Jak czytać wyniki - indeks

Ten folder tłumaczy, DLA KAŻDEGO pliku Excela generowanego przez ten projekt: jakie ma
zakładki, co oznacza każda kolumna, i - najważniejsze - **JAK dokładnie policzona jest
każda wartość** (z jakich danych źródłowych, jakim wzorem/agregacją). Jeden plik notatki
= jeden generator Excela.

| Plik Excela | Generuje go | Notatka |
|---|---|---|
| `Podsumowanie_wynikow.xlsx` | `generuj_excel_podsumowanie.py` (wołany z `test_wszystkie_rownolegle.py` / `test_wszystkie_algorytmy_wszystkie_lokalizacje.py`) | [podsumowanie_wynikow.md](podsumowanie_wynikow.md) |
| `Podsumowanie_wrazliwosc.xlsx` | `generuj_excel_wrazliwosc.py` (wołany z `test_wrazliwosc_dwie_lokalizacje.py`) | [podsumowanie_wrazliwosc.md](podsumowanie_wrazliwosc.md) |
| `Podsumowanie_kroku_sterowania.xlsx` | `test_wrazliwosc_kroku_sterowania.py` (funkcja `zbuduj_excel`) | [podsumowanie_kroku_sterowania.md](podsumowanie_kroku_sterowania.md) |
| `Podsumowanie_szumu.xlsx` | `test_szum_wielu_czujnikow.py` (funkcja `zbuduj_excel`) | [podsumowanie_szumu.md](podsumowanie_szumu.md) |
| `Podsumowanie_awarii.xlsx` | `generuj_excel_awarie.py` (wołany z `test_awarie_czujnikow.py`) | [podsumowanie_awarii.md](podsumowanie_awarii.md) |
| `Podsumowanie_prognozy_opadow.xlsx` | `test_skutecznosc_prognozy_opadow.py` (funkcja `zapisz_excel`) | [podsumowanie_prognozy_opadow.md](podsumowanie_prognozy_opadow.md) |
| `Diagnostyka_<lokalizacja>.xlsx` | `test_diagnostyka_funkcji_ryzyka.py` | [diagnostyka_funkcji_ryzyka.md](diagnostyka_funkcji_ryzyka.md) |
| `Podsumowanie_MASTER.xlsx` | `generuj_excel_master.py` | [podsumowanie_master.md](podsumowanie_master.md) |

## Jedna rzecz wspólna dla WSZYSTKICH plików - ważne przy czytaniu cudzych kopii

Niektóre zakładki (głównie w `Podsumowanie_wynikow.xlsx`, zakładki
"Podsumowanie_algorytmy"/"Podsumowanie_lokalizacje") zawierają **formuły Excela**
(`=AVERAGEIF(...)`, `=MAXIFS(...)` itd.), nie gotowe liczby. Jeśli plik był tylko
zapisany przez skrypt Pythona (openpyxl) i NIGDY nie otworzony w prawdziwym Excelu/
LibreOffice, te komórki nie mają jeszcze wyliczonej (scache'owanej) wartości - program
typu `pandas.read_excel()` odczyta wtedy formułę jako tekst albo `None`, NIE liczbę.
**Rozwiązanie**: otwórz plik raz w Excelu/LibreOffice i zapisz (Ctrl+S) - od tej pory
wartości są scache'owane i każdy program je odczyta poprawnie. Zakładki bez formuł
("Dane", "Wyniki", "Wyniki_surowe" itp. - surowe tabele źródłowe) tego problemu nie mają,
bo są zapisywane jako gotowe liczby/tekst wprost z Pythona.

## Skróty pojawiające się w wielu plikach

- **HRT** = temperatura szyny ogrzewanej (Heated Rail Temperature) - główny sygnał
  sterowany, to jej dotyczą progi bezpieczeństwa normy.
- **CRT** = temperatura szyny NIEogrzewanej (Cold Rail Temperature) - "co by było, gdyby
  nikt nie grzał" - referencja pogodowa.
- **AT** = temperatura powietrza.
- **IAE/ISE/ITAE** = wskaźniki jakości regulacji, patrz [`../IAE_ISE_ITAE.md`](../IAE_ISE_ITAE.md).
- **kara bezpieczeństwa / epizody HRT<-10°C** = wskaźnik naruszeń bezwzględnych progów
  bezpieczeństwa, patrz [`../kara_bezpieczenstwa.md`](../kara_bezpieczenstwa.md).
- **`autotest_fit_ok`/`autotest_K`/`autotest_T1`/`autotest_L`** = wynik autotestu SOPDT
  (`rdzen_kontrolera.KontrolerBazowy.autotest`) - identyfikacja modelu obiektu ze skoku
  0%→100% mocy na starcie symulacji, tylko dla algorytmów adaptacyjnych.
