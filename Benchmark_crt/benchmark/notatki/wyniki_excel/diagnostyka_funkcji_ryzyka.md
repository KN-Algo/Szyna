# Diagnostyka_<lokalizacja>.xlsx

Generator: `test_diagnostyka_funkcji_ryzyka.py`. W ODRÓŻNIENIU od wszystkich pozostałych
plików w tym folderze (które agregują WIELE przebiegów w tabele/statystyki), ten plik
pokazuje pojedynczy przebieg **KROK PO KROKU** - do wizualnej weryfikacji "na oko", czy
kaskada priorytetów funkcji ryzyka (`Algorytmy/funkcja_ryzyka_wspolne.py`) reaguje
sensownie na prawdziwą pogodę, a nie tylko ufania liczbom zbiorczym. Domyślnie:
`risk_function_pid` na Abisko (najbardziej zróżnicowana pogoda - dobra szansa zobaczyć
wszystkie 4 priorytety kaskady w akcji), okno 14 dni (najzimniejszy wycinek). Można podać
kilka algorytmów naraz (`SZYNA_ALGORYTMY_DIAG`) - każdy dostaje własną zakładkę.

## Zakładka "Podsumowanie" (pierwsza, indeks 0)

Jeden wiersz na algorytm z listy `SZYNA_ALGORYTMY_DIAG`. Kolumny: Energia (kWh), IAE,
ISE, ITAE (wprost ze `stats`, jak w każdym innym pliku), i "Ma jawny cel ciągły" (Tak/Nie
- czy diagnostyka zwróciła `target_temperature` dla tego algorytmu, patrz
`../IAE_ISE_ITAE.md`).

## Zakładki per algorytm (nazwa = pierwsze 31 znaków nazwy algorytmu, limit Excela)

Surowy przebieg PO ZMNIEJSZENIU rozdzielczości do 15 minut (`przygotuj_do_zapisu(...,
900)` - uśrednianie w oknach 15-min, TYLKO do zapisu/wykresu, statystyki w zakładce
"Podsumowanie" są liczone WCZEŚNIEJ z pełnej rozdzielczości symulacji, więc nie tracą
dokładności). Kolumny: `Timestamp`, `AT`, `CRT`, `HRT`, `Target_temperature`, `Need_heat`,
`Moc_procent`, `Snieg_mm` - dokładnie te same pola co `df_hist` z
`symulacja_fizyczna.uruchom_kontroler` (patrz `../IAE_ISE_ITAE.md` po to, skąd
`Target_temperature`/`Need_heat` się biorą dla każdej rodziny algorytmów).

Dwa wbudowane wykresy liniowe per zakładka:
1. **"[algorytm] - temperatury i cel"** - AT/CRT/HRT/Target_temperature na jednym
   wykresie (oś Y = °C, oś X = krok co 15 min). To jest GŁÓWNY wykres diagnostyczny -
   pozwala zobaczyć, kiedy Target_temperature "skacze" (zmiana priorytetu w kaskadzie
   funkcji ryzyka) i czy rzeczywista HRT za nim nadąża.
2. **"[algorytm] - moc grzania (%)"** - sama moc grzania w czasie, osobny wykres pod
   pierwszym.

## Jak czytać - typowe wzorce w wykresie temperatur

- `Target_temperature` skacze w GÓRĘ przy nadejściu opadu/mrozu (kaskada przechodzi na
  wyższy priorytet ochrony) i WRACA do poziomu bazowego, gdy zagrożenie mija.
- Jeśli `HRT` wyraźnie "goni" `Target_temperature` z opóźnieniem i przeregulowaniem - to
  jest DOKŁADNIE to, co IAE/ISE/ITAE (zakładka "Podsumowanie") mierzą liczbowo; ten
  wykres pozwala zobaczyć TO SAMO zjawisko wizualnie, epizod po epizodzie.
- Jeśli `Need_heat` (nie ma własnego wykresu, ale jest w danych kolumnowych) jest `NaN` -
  dany algorytm nie zwrócił diagnostyki na tym kroku (nie powinno się zdarzać dla żadnego
  z 32 algorytmów w normalnej pracy, patrz `../IAE_ISE_ITAE.md`).
