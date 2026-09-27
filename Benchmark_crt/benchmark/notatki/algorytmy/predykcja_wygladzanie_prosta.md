# predykcja_wygladzanie_prosta

- **Plik / klasa / metoda:** `Algorytmy/predykcja_wygladzanie_prosta.py` / `KontrolerPredykcjaWygladzanie` / `compute_control`
- **Typ:** Regulator progowy (prognoza Holta, margines samokalibrujący) · **Cel:** Prognoza HRT +
  próg bazowy + margines = śledzony błąd własnej prognozy · **Adaptacyjny:** nie (brak autotestu SOPDT) ·
  **Bezpiecznik:** tak

## Skąd to się wzięło

Zaimplementowany na życzenie użytkownika wprost z pracy: S. Chiaradonna, G. Masetti, F. Di Giandomenico,
F. Righetti, C. Vallati, *"Enhancing sustainability of the railway infrastructure: Trading energy saving
and unavailability through efficient switch heating policies"*, Sustainable Computing: Informatics and
Systems 30 (2021) 100519 - polityka **P_pre** (sekcja 4.2.3).

## Jak działa

Zamiast reagować na BIEŻĄCY odczyt HRT (jak histereza) albo na WSPÓLNĄ prognozę Kalmana zbudowaną z
pełnej, scentralizowanej historii AT/CRT (jak `risk_function_pid`/`mpc_*` - patrz `rdzen_kontrolera.
_forecast_attribute`), ten kontroler ma WŁASNĄ, CAŁKOWICIE ODDZIELNĄ, lekką prognozę: wygładzanie
wykładnicze Holta (poziom + trend, O(1)/krok) na własnej historii HRT, binowanej co 15 min (spójnie z
resztą projektu, `NANOS_PER_BIN`) - świadomie uboższa metoda, zgodnie z założeniem pracy "lokalny
kontroler bez dostępu do bogatszych zasobów koordynatora" (w oryginale: Holt-Winters/TBATS).

**Kluczowa idea pracy - próg SAMOKALIBRUJĄCY SIĘ.** Cytat (sekcja 4.2.3): najlepsza wartość progu
`T̃_thr` to WŁASNY, na bieżąco śledzony błąd bezwzględny prognozy `ε_f` - margines dokładnie taki duży,
żeby pokryć typowy błąd prognozy (unikając zamarznięcia), ale nie większy niż trzeba (żeby nie marnować
energii). Implementacja: `prog_efektywny = PROG_BAZOWY_C (3.0°C) + ε_f`, gdzie `ε_f` = średnia z ostatnich
do 50 zaobserwowanych błędów `|prognoza - rzeczywistość|` (aktualizowana przy każdym zamknięciu binu
15-minutowego). **To jedyny algorytm w projekcie, w którym margines bezpieczeństwa NIE jest stałą, tylko
wynika z historii własnej trafności prognozowania** - rośnie, gdy prognoza ostatnio się myliła bardziej,
maleje, gdy jest trafna.

## Zaobserwowane zachowanie (smoke test, Abisko + Ojmiakon, 5 dni)

Energia zbliżona do algorytmu bazowego normy (1110/1666 kWh), umiarkowana kara bezpieczeństwa
(9-16 tys. °C·s - dużo mniejsza niż `histereza_pamiec_rosy` w tych samych warunkach), ale wciąż realne
epizody spadku poniżej -10°C (`min_hrt` do -25°C w Ojmiakonie) - margines samokalibrujący pomaga, ale
(zgodnie z pracą źródłową) nie eliminuje ryzyka całkowicie, zwłaszcza w ekstremalnie zimnych warunkach
wykraczających poza to, co praca oryginalnie testowała. Patrz `../kara_bezpieczenstwa.md`.

## FLOPs

Szacunek analityczny: ~15/krok, z rzadkimi skokami (~900s, przy zamknięciu binu 15-minutowego, gdy
aktualizowany jest stan Holta i liczony błąd prognozy).

## Powiązania

Dziedziczy `rdzen_kontrolera.KontrolerBazowy` (bufor kroczący dziedziczony, ale NIEUŻYWANY do prognozy -
własny, osobny bufor 15-minutowy HRT). Kontrast z prognozą Kalmana z pełnym dostępem do historii:
[risk_function_pid.md](risk_function_pid.md), [mpc_prognoza_pogody.md](mpc_prognoza_pogody.md).
Siostrzany algorytm z tej samej pracy (polityka P_mem): [histereza_pamiec_rosy.md](histereza_pamiec_rosy.md).
