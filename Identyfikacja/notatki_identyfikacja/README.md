# Identyfikacja MISO — notatki

Folder dotyczy WYŁĄCZNIE dodatkowego skryptu `Identyfikacja/Identyfikacja/identyfikacja_miso.py`
(2026-09-16) — rozszerzenia dwóch referencyjnych skryptów identyfikacyjnych o dodatkowe parametry
pogodowe i wspólny model wielowejściowy (MISO). **Referencyjne skrypty
(`idetyfikacja_modele.py`, `idetyfikacja_modelu_temperatrua_poweitrza.py`) NIE są i nie będą
modyfikowane** — są "tablicą prawdy" na życzenie użytkownika. `identyfikacja_miso.py` jest w pełni
samodzielny (powiela tę samą matematykę: `apply_delay`/`get_sim`/`build_poly`/`compute_metrics`,
zamiast importować z referencyjnych plików), żeby nigdy nie było pokusy ich dotykać.

## Źródło danych

`algo (4).log` — surowy log urządzenia (linie `ALGOp1`/`ALGOp2`/`ALGOp3` + zmiany trybu sterowania
obwodu 7), ~3 tygodnie (2026-04-15 → 2026-05-06), 200 791 próbek CRT/HRT/AT/DPT/RH/PRESS/PRECIP/SNOW
+ 8746 próbek mocy (PWRL1/PWRL2, logowane WYŁĄCZNIE w oknach ręcznego testu skokowego — tryb
`IndOn`). To bogatsze źródło niż `csv-skok-1.csv`/`csv-skok-2.csv` (te dwa to tylko wycinki
odpowiadające dwóm oknom testu skokowego znalezionym w logu: 2026-04-22 i 2026-04-30).

**Znaczenie kolumn** (potwierdzone wprost przez użytkownika, dopasowanie 1:1 z nazwami pól
urządzenia): `CRT` — temperatura odcinka NIEgrzanego szyny [°C], `HRT` — temperatura odcinka
GRZANEGO szyny [°C] (wyjście modelu), `AT` — temperatura powietrza [°C], `DPT` — punkt rosy [°C],
`RH` — wilgotność względna [%], `PRESS` — ciśnienie [hPa], `PRECIP`/`SNOW` — flagi detekcji
opadu/śniegu (0/1), `PWRL1`/`PWRL2` — moc czynna [W] z dwóch faz JEDNEGO obwodu grzejnego (sumowane
w skrypcie, jak w oryginalnym `idetyfikacja_modele.py`).

**WAŻNE — czego w tych danych NIE MA**: użytkownik pierwotnie prosił o sprawdzenie wpływu
nasłonecznienia i wiatru. Po przeanalizowaniu surowego logu i oficjalnego opisu pól urządzenia
potwierdzono, że **żadna z 13 kolumn nie odpowiada wiatrowi ani nasłonecznieniu** — urządzenie
fizycznie tych wielkości nie mierzy. Sprawdzane są więc WSZYSTKIE parametry, które faktycznie
występują w danych: AT, DPT, RH, PRESS, PRECIP (SNOW wykluczony automatycznie — stały 0 przez cały
okres, brak wariancji, spring/brak śniegu w tym oknie).

## Metodologia

1. **Kanał MOCY** (PWRL1+PWRL2 → HRT): identyfikacja na oknie testu skokowego (2026-04-22,
   06:40→08:00), TA SAMA biblioteka postaci transmitancji co `idetyfikacja_modele.py` (FOLP, FOLP_Z,
   SOSP, SOSP_Z, TOSP, FOSP + warianty z iteracyjnie szukanym opóźnieniem L) — wyniki bezpośrednio
   porównywalne z referencyjnym skryptem.
2. **Kanały POGODOWE** (AT, DPT, RH, PRESS, PRECIP → HRT): identyfikacja na PEŁNYM logu, z
   WYŁĄCZENIEM dni testu skokowego (żeby nieznana/niezalogowana moc poza oknami testu nie
   zniekształcała wyniku — patrz "Ograniczenia" niżej). Biblioteka: I (integrator), FO, FO_Z, SO,
   SO_Z, TO + FOD/SOD z iteracyjnym L (jak w `idetyfikacja_modelu_temperatrua_poweitrza.py`).
3. **Model MISO**: suma transmitancji per-kanał (`HRT = y0 + Σ Gᵢ(kanałᵢ)`), dopasowana WSPÓLNIE
   (jedno wywołanie `curve_fit`, wszystkie parametry naraz) na oknie testu skokowego. Do modelu
   wchodzi kanał MOCY zawsze + każdy kanał pogodowy, którego SAMODZIELNE (SISO) adj R² > 0.05.
   Opóźnienia L per kanał są USTALONE na wartości znalezionej w etapie przesiewania (nie
   re-optymalizowane wspólnie — uproszczenie dla stabilności/czasu obliczeń, udokumentowane wprost
   w kodzie).
4. **Analiza wpływu (ablacja)**: dla gotowego modelu MISO, dla każdego kanału osobno — dopasowanie
   BEZ NIEGO, różnica R² (`ΔR²`) = miara wpływu tego parametru na całościową skuteczność modelu.

## Ograniczenia (ważne przy interpretacji wyników)

- **Moc poza oknami testu skokowego jest NIEZNANA** (urządzenie nie loguje PWRL poza trybem
  ręcznym `IndOn`) — mogła być niezerowa w trybie automatycznym. Identyfikacja kanałów pogodowych
  na dniach BEZ testu skokowego zakłada, że efekt mocy tam jest pomijalny/nieskorelowany z
  badanymi oknami czasowymi — to założenie, nie zmierzony fakt.
- Model MISO dopasowany jest TYLKO na oknie testu skokowego (jedyne miejsce, gdzie moc i pogoda są
  obserwowane JEDNOCZEŚNIE) — ekstrapolacja na warunki spoza tego okna (inne pory roku, dużo
  zimniej) nie jest zweryfikowana.
- Opóźnienia L ustalone z etapu przesiewania, nie re-optymalizowane w dopasowaniu wspólnym MISO.

## Uruchomienie

```
cd Identyfikacja/Identyfikacja
python identyfikacja_miso.py
```

Zajmuje ok. 2-4 minuty lokalnie (pasek postępu w konsoli). `QUICK_MODE_DZIELNIK` na górze pliku
kontroluje gęstość siatki przeszukiwania opóźnienia L (1 = najdokładniej/najwolniej, więcej =
szybciej kosztem gęstości siatki) — jedyny "pokrętło" na czas obliczeń.

## Wyniki

Wszystkie wyniki (wykresy PNG w stylu referencyjnych skryptów + tabela CSV/Excel) lądują w
OSOBNYM folderze `Identyfikacja/wyniki_identyfikacja/` (nie miesza się z `Wyniki/` referencyjnych
skryptów) — patrz [wyniki.md](wyniki.md) po interpretację konkretnych liczb z ostatniego przebiegu.
