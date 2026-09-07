# Jak liczymy karę bezpieczeństwa

Nowy wskaźnik (dopisany 2026-09-03, na życzenie użytkownika), UZUPEŁNIAJĄCY IAE/ISE/ITAE
(patrz [IAE_ISE_ITAE.md](IAE_ISE_ITAE.md)), nie zastępujący ich. Kluczowa różnica:

| | IAE/ISE/ITAE | Kara bezpieczeństwa |
|---|---|---|
| Mierzy | jak DOBRZE algorytm trzyma się WŁASNEGO, wyznaczonego celu | jak BEZPIECZNY jest fizyczny WYNIK, wobec BEZWZGLĘDNYCH progów normy |
| Cel odniesienia | `target_temperature` z diagnostyki KAŻDEGO algorytmu (różny dla każdego) | te same 3 progi normy dla WSZYSTKICH algorytmów |
| Liczone gdy | TYLKO `need_heat=True` | ZAWSZE, na każdym kroku, niezależnie od diagnostyki |
| Źródło odczytów | `row_data` przekazane kontrolerowi (może być zafałszowane fault_injectorem) | PRAWDZIWE, fizyczne wartości symulacji (jak `min_hrt`/`max_snieg_mm`) |

Liczona w **tej samej głównej pętli** (`symulacja_fizyczna.uruchom_kontroler`), automatycznie dla
WSZYSTKICH 32 algorytmów, tym samym mechanizmem - jak IAE/ISE/ITAE, nie ma osobnej ścieżki per algorytm.

## Trzy składowe (na życzenie użytkownika)

Każda aktywna TYLKO gdy przekroczony jest odpowiedni próg, przeliczona na **°C-ekwiwalent** i
**CAŁKOWANA po czasie** (`× dt`, jak IAE) - dłuższe i głębsze naruszenie waży więcej niż krótkie/płytkie:

1. **Zalegający śnieg powyżej bezpiecznego progu.** Próg = `RISK_SNOW_LINGER_THRESHOLD_MM` (5 mm) -
   TA SAMA stała, której `funkcja_ryzyka_wspolne._evaluate_risk_setpoint` już używa jako granicy
   "trzeba aktywnie topić". Nadmiar w mm przeliczony na °C-ekwiwalent przez `RISK_SNOW_PENALTY_PER_MM_C`
   (0.05 °C/mm) - TA SAMA konwersja, której funkcja ryzyka już używa do własnej kary za zalegający
   śnieg (nie wymyślony nowy współczynnik - jedno źródło prawdy).
2. **Marznący deszcz + szyna wciąż zimna.** Marznący deszcz = opad przy CRT lub AT ≤ 1°C (identyczna
   definicja `is_freezing_rain` jak w `_evaluate_risk_setpoint`, priorytet #1 kaskady ryzyka). Aktywne,
   gdy DODATKOWO rzeczywista HRT wciąż < +2°C (czyli szyna nie zdążyła się jeszcze wygrzać powyżej
   bezpiecznego zapasu nad zamarzaniem) - wysokość kary = deficyt `(2°C − HRT)`.
3. **HRT poniżej bezwzględnego dolnego limitu normy.** Próg = `RISK_HRT_ABSOLUTE_FLOOR_C` (-10°C,
   "Bezwzględny dolny limit temperatury szyny ogrzewanej" - ta sama stała, na której opiera się
   priorytet #3 funkcji ryzyka) - wysokość kary = deficyt `(-10°C − HRT)`.

```python
snow_excess_mm = max(0.0, snow_mm - RISK_SNOW_LINGER_THRESHOLD_MM)
is_freezing_rain_prawdziwy = is_raining_prawdziwy and (current_crt <= 1.0 or at_temp <= 1.0)
marznacy_deszcz_deficyt_c = (2.0 - current_hrt) if (is_freezing_rain_prawdziwy and current_hrt < 2.0) else 0.0
floor_deficyt_c = max(0.0, RISK_HRT_ABSOLUTE_FLOOR_C - current_hrt)

kara_bezpieczenstwa_suma += dt * (
    snow_excess_mm * RISK_SNOW_PENALTY_PER_MM_C + marznacy_deszcz_deficyt_c + floor_deficyt_c
)
```

Wszystkie trzy składowe SUMUJĄ się do JEDNEGO łącznego wskaźnika `kara_bezpieczenstwa` (°C·s) - nie ma
osobnych kolumn per składowa w Excelu (choć każda jest osobno udokumentowana tutaj, żeby dało się
zrekonstruować, co dokładnie wnosi do sumy w danym przebiegu).

## Dodatkowe, osobno liczone kolumny

Na wyraźne życzenie użytkownika ("kolumna wartości minimalnych", "ile razy wypadł poniżej -10 stopni"),
NIEZALEŻNIE od powyższej sumy:

- **`min_hrt`** (°C) - najniższa zaobserwowana RZECZYWISTA temperatura szyny ogrzewanej w CAŁYM
  przebiegu (`df_hist['HRT'].min()`) - kolumna istniała już wcześniej w statystykach, teraz dodana do
  zakładki "Dane" w Excelu (wcześniej liczona, ale nie pokazywana).
- **`epizody_ponizej_floor`** - liczba ODRĘBNYCH ZDARZEŃ (nie kroków symulacji!) przejścia HRT poniżej
  -10°C - licznik z detekcją zbocza (rośnie tylko przy przejściu `>= floor -> < floor`, nie przy każdym
  kroku, w którym HRT POZOSTAJE poniżej floora) - dokładnie tak samo liczone jak istniejący licznik
  `przelaczenia` (detekcja zmiany stanu, nie suma kroków w danym stanie). "Ile razy to się zdarzyło", nie
  "jak długo trwało" - to drugie mierzy już sama składowa (3) kary bezpieczeństwa powyżej.

## Gdzie dokładnie w kodzie

`symulacja_fizyczna.uruchom_kontroler`, zaraz po `ice_model.update()` (potrzebna ŚWIEŻA, prawdziwa
grubość śniegu `snow_mm` na TEN krok) - patrz komentarz "KARA BEZPIECZEŃSTWA" w kodzie. Trafia do
`stats['kara_bezpieczenstwa']`/`stats['epizody_ponizej_floor']`, stamtąd do `PRZEGLAD_ZBIORCZY.csv` i
kolumn "Min HRT (°C)"/"Kara bezpieczeństwa (°C·s)"/"Epizody HRT<-10°C" w zakładce "Dane"
(`Podsumowanie_wynikow.xlsx`).

## W Excelu

- Zakładka **"Dane"**: 3 nowe kolumny (M/N/O) - Min HRT, Kara bezpieczeństwa, Epizody HRT<-10°C. Wiersze
  z niezerową karą bezpieczeństwa podświetlone TYM SAMYM kolorem co anomalie przegrzania (Max HRT>35°C).
- Zakładka **"Podsumowanie_algorytmy"**: 4 nowe kolumny (P/Q/R/S) per algorytm - średnia kara
  bezpieczeństwa, Min HRT GLOBALNIE (najgorszy przypadek ze wszystkich lokalizacji/lat), **lokalizacja
  TEGO najgorszego przypadku** (odpowiedź na "połączenie z miejscem gdzie to nastąpiło" - formuła
  INDEX/MATCH z podwójnym kryterium algorytm+wartość, bez potrzeby formuły tablicowej CSE), i suma
  epizodów HRT<-10°C po wszystkich przebiegach danego algorytmu.
- Zakładka **"Wnioski"**: nowa sekcja "5) NARUSZENIA BEZPIECZEŃSTWA" - tekstowe podsumowanie per
  algorytm (suma kary, suma epizodów, najzimniejszy zaobserwowany HRT) + lista 5 najgorszych
  pojedynczych przypadków (lokalizacja, rok, algorytm, kara, min HRT, liczba epizodów).

## % względem normy LET-1 (punkt odniesienia)

Dopisane 2026-09-03, na życzenie użytkownika. Zakładka "Dane" ma kolumnę "Kara bezp. %
vs norma LET-1" = `(kara_algorytmu − kara_normy) / kara_normy × 100`, gdzie
`algorytm_z_normy` jest baseline'em DLA KAŻDEJ (Lokalizacja, Interwał, Rok) osobno (jak w
`../IAE_ISE_ITAE.md`). Puste, gdy kara normy w danej lokalizacji/roku wynosi dokładnie 0
(często się zdarza - norma jest z definicji zaprojektowana tak, żeby NIGDY nie łamać
własnych progów bezpieczeństwa) - w takim przypadku procent byłby matematycznie
niezdefiniowany (dzielenie przez zero), więc kolumna zostaje pusta zamiast pokazywać
mylące "nieskończenie duże" odchylenie.

Realny przykład (smoke test, Ojmiakon): `Fuzzy Logic 1` ma karę bezpieczeństwa
**46015% WYŻSZĄ** niż norma w tej samej lokalizacji (norma: 14 216.8 °C·s, Fuzzy Logic 1:
6 556 146.7 °C·s) - dokładnie ilustruje, dlaczego norma jest sensownym punktem
odniesienia: z DEFINICJI przestrzega własnych progów bezpieczeństwa niemal zawsze, więc
odchylenie w setkach/tysiącach procent u innych algorytmów jest natychmiast czytelnym
sygnałem "ten algorytm w tej pogodzie realnie łamie bezpieczeństwo normy", nie tylko
abstrakcyjną liczbą °C·s bez punktu odniesienia.

## Analiza wrażliwości wag (czy ranking jest odporny na dobór wag?)

Dopisane 2026-09-07, na życzenie użytkownika (przygotowanie do publikacji - potencjalny zarzut
recenzenta: "dlaczego akurat te wagi?"). Trzy składowe kary wyżej są ważone stałymi
`KARA_WAGA_SNIEG_C_PER_MM`/`KARA_WAGA_MROZ_DESZCZ`/`KARA_WAGA_FLOOR`
(`Algorytmy/funkcja_ryzyka_wspolne.py`) - CELOWO **oddzielnymi** od stałych sterujących funkcją
ryzyka (`RISK_SNOW_PENALTY_PER_MM_C` itd.), mimo nominalnie identycznej wartości dla śniegu. Dzięki
temu zmiana tych wag NIE wpływa na zachowanie żadnego kontrolera (kara bezpieczeństwa to metryka
post-hoc z ground-truth trajektorii - patrz tabela na górze tej notatki) - a to z kolei pozwala policzyć
WSZYSTKIE scenariusze wag w JEDNYM przebiegu symulacji (dodatkowe sumowanie po już policzonych
składowych `snow_excess_mm`/`marznacy_deszcz_deficyt_c`/`floor_deficyt_c`), **bez ponownego odpalania
fizyki/sterowania** - zero dodatkowego kosztu obliczeniowego na klastrze, w odróżnieniu od analizy
wrażliwości transmitancji K/T1 (`notatki/wyniki_excel/`), która faktycznie WYMAGA 8 osobnych przebiegów,
bo tam zaburzenie zmienia zachowanie regulatora.

`KARA_WAGI_SCENARIUSZE` definiuje 6 scenariuszy - każdy zaburza JEDNĄ z trzech wag o ±50% względem
nominalnej (pozostałe dwie bez zmian): `snieg_x0.5`, `snieg_x2`, `mroz_x0.5`, `mroz_x2`, `floor_x0.5`,
`floor_x2`. Wyniki trafiają do `stats['kara_bezpieczenstwa__<etykieta>']` obok wariantu nominalnego.

**W Excelu**: nowa zakładka **"Wrazliwosc_wag_kary"** (pomijana bez błędu, gdy dane pochodzą sprzed tej
zmiany) - tabela: 1 wiersz na algorytm, kolumny = średnia kara + ranga dla wariantu nominalnego, potem
średnia kara + Δ ranga (zmiana pozycji względem rankingu nominalnego) dla każdego z 6 scenariuszy, oraz
na dole korelacja rang Spearmana każdego scenariusza względem rankingu nominalnego (blisko 1.0 = ranking
odporny na dobór tej wagi). To narzędzie WERYFIKACJI odporności, nie samodzielny wynik do publikacji -
surowe wartości wag NIE są celem tej analizy (użytkownik: "nie zamierzałem dawać do wyników za bardzo
tych współczynników, chyba że ktoś naprawdę je chce").

## Zaobserwowany przykład (smoke test, Ojmiakon, 5 dni)

Rodzina `fuzzy_logic_*`/`fuzzy_normy_*` (stały cel 3°C, BEZ priorytetu ochrony przed floorem, jaki ma
kaskada funkcji ryzyka) w Ojmiakonie (najzimniejsza lokalizacja w zbiorze) realnie spada do HRT ≈
-27...-33°C (kara bezpieczeństwa rzędu 3-6 mln °C·s w oknie 5-dniowym) - dokładnie ten typ ryzyka
fizycznego, którego IAE/ISE/ITAE by NIE wykryło (te algorytmy trzymają się SWOJEGO celu 3°C całkiem
nieźle - problem w tym, że sam ten cel nie ma wbudowanej ochrony przed ekstremalnym mrozem, w
odróżnieniu od funkcji ryzyka, gdzie priorytet #3 kaskady istnieje dokładnie po to).
