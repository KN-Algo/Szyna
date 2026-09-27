# Podsumowanie_prognozy_opadow.xlsx

Generator: `test_skutecznosc_prognozy_opadow.py` (funkcja `zapisz_excel`). Ocenia
SKUTECZNOŚĆ modułu `przewidywanie_opadow.py` - dokładnie tej samej klasy, której realnie
używają kontrolery `*_opad` (`funkcja_ryzyka_wspolne.KontrolerRyzykaOpadBazowy.
_prognoza_intensywnosci_opadu`) - na WSZYSTKICH 43 plikach pogodowych, licząc "na ślepo"
prognozę i porównując z tym, co NAPRAWDĘ się wydarzyło.

## Jak liczona jest "prawda" (ground truth) i prognoza

- **Ground truth** (`wylicz_ground_truth`): dla każdej próbki poziom opadu 0-3 wyliczony
  z SUROWYCH danych pogodowych (`opad_mm`/`temperatura_powietrza_C`/`wiatr_m_s`) wg
  progów: 0=brak, 1=słaby (opad zimowy ≤0.35mm/krok), 2=średni (0.35-1.0mm/krok, wiatr
  <6m/s), 3=mocny (>1.0mm/krok LUB średni opad przy wietrze ≥6m/s) - identyczne progi jak
  w module produkcyjnym, patrz zakładka "Definicje_poziomow".
- **Prognoza**: `PrzewidywanieOpadow.predict_winter_precipitation()` wywoływana W KAŻDYM
  kroku, patrząc TYLKO na dane sprzed danego momentu (4 kroki wstecz opadu, 8 kroków
  naprzód prognozy temperatury z modelu, punkt rosy i wiatr TERAZ) - dokładnie tak, jak
  widziałby to kontroler w czasie rzeczywistym, bez podglądania przyszłości.

## Zakładka "Wyniki_lokalizacje"

Jeden wiersz na plik pogodowy (43 wiersze). Kluczowe kolumny:
- **Skuteczność osłony (%)** = `godziny_wykryte / godziny_opadu × 100` - z WSZYSTKICH
  godzin z realnym opadem zimowym, ile algorytm faktycznie wykrył (podniósł alarm na krok
  +1) - to jest "recall"/czułość.
- **Trafność alarmu (%)** = `tp / wszystkie_alarmy × 100` - z WSZYSTKICH podniesionych
  alarmów, ile było trafnych - to jest "precision"/precyzja. `wszystkie_alarmy = tp +
  za_wcześnie + za_późno + czysto_fałszywe`.
- **Dokładność poziomu 0-3 (%)** - jak często przewidziany POZIOM (nie tylko
  tak/nie) zgadzał się dokładnie z ground truth na krok +1.
- **Za wcześnie / Za późno / Czysto fałszywe** - rozbicie fałszywych alarmów: "za
  wcześnie" = alarm podniesiony, ale opad realnie wystąpił w ciągu następnych 8 kroków
  (algorytm "przewidział za wcześnie"); "za późno" = opad był w POPRZEDNICH 8 krokach
  (alarm spóźniony, opad już się skończył); "czysto fałszywe" = brak opadu w promieniu ±8
  kroków w ogóle.
- **Dokł. horyzont krok 1-8 (%)** - jak dokładność (dokładny poziom, nie tylko tak/nie)
  spada w miarę jak prognoza sięga dalej w przyszłość (krok 1 = najbliższy, krok 8 =
  najdalszy z 8-krokowego horyzontu).

Skala kolorów (czerwony=źle → żółty=środek percentyla → zielony=dobrze) na kolumnach
Skuteczność/Trafność/Dokładność poziomów.

## Zakładka "Podsumowanie_ogolne"

Dwa różne sposoby uśredniania - WAŻNE, żeby nie pomylić:
- **"globalna" (pooled)** - wszystkie godziny ze WSZYSTKICH 43 plików wrzucone razem
  przed policzeniem procentu - lokalizacje z DŁUGIMI opadami dominują wynik.
- **"macro-avg" (średnia po lokalizacjach)** - każda z 43 lokalizacji liczy się TYLE
  SAMO, niezależnie od tego, ile miała godzin opadu - pokazuje SPÓJNOŚĆ skuteczności
  między lokalizacjami, nie tylko zagregowany wynik. Duża różnica między globalną a
  macro-avg oznacza, że wynik jest niesiony przez kilka lokalizacji z dużą ilością opadu,
  a nie jednolicie dobry wszędzie.

Zawiera też wykres liniowy "Dokładność wg horyzontu" (globalny, pooled, 8 punktów) oraz
tekstowe "Najlepsza/najgorsza lokalizacja" (po skuteczności osłony).

Zmierzone globalnie (patrz `../../AGENTS.md`): 80.1% skuteczność osłony, 81.3% trafność
alarmu (z dużym rozrzutem między lokalizacjami, np. `wroclaw_2024` tylko ~62% trafności).

## Zakładka "Definicje_poziomow"

Statyczna tabela progów (0-3) użytych do wyliczenia ground truth - kopia z nagłówka
skryptu, żadnych obliczeń.
