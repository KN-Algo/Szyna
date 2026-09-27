# histereza_pamiec_rosy

- **Plik / klasa / metoda:** `Algorytmy/histereza_pamiec_rosy.py` / `KontrolerHisterezaPamiecRosy` / `compute_control`
- **Typ:** Histereza (próg + punkt rosy, z pamięcią) · **Cel:** Punkt rosy + próg referencyjny T_thr (fallback
  na sam próg przy zawieszonym odczycie) · **Adaptacyjny:** nie (brak autotestu) · **Bezpiecznik:** tak

## Skąd to się wzięło

Zaimplementowany na życzenie użytkownika wprost z pracy: S. Chiaradonna, G. Masetti, F. Di Giandomenico,
F. Righetti, C. Vallati, *"Enhancing sustainability of the railway infrastructure: Trading energy saving
and unavailability through efficient switch heating policies"*, Sustainable Computing: Informatics and
Systems 30 (2021) 100519 - polityka **P_mem** (sekcja 4.2.2) połączona z progiem "koordynatora" (sekcja 4.1).

## Jak działa

**To jedyny algorytm w całym projekcie, który faktycznie CZYTA `PUNKT_ROSY_C`** w logice decyzyjnej -
potwierdzone empirycznie (`wyniki/_analiza_klastra.md`/test szumu wielu czujników): szum na tym czujniku
miał dotąd 0.00% wpływu na WSZYSTKIE pozostałe 33 algorytmy, bo żaden go nie używał.

Reguła progowa (wg pracy, "koordynator" z pełnym dostępem do stacji pogodowej):
```
załącz, gdy HRT <= punkt_rosy + T_thr  ORAZ  HRT <= T_thr
wyłącz, gdy HRT >  punkt_rosy + T_thr  LUB   HRT >  T_thr
```
`T_thr = 3.0°C` w tej implementacji (praca testowała 0°C i 5°C jako skrajne wartości analizy wrażliwości,
bez jednoznacznej rekomendacji - 3.0°C wybrane dla spójności z progiem "na sucho" `histereza_let1.hrt_off_dry`).

**Mechanizm "pamięci" (P_mem).** W oryginale: gdy łącze PLC między koordynatorem a lokalnym kontrolerem
się psuje, kontroler używa OSTATNIEJ znanej wartości punktu rosy przez `Δm` kroków, potem przechodzi na
politykę bazową (sam próg temperatury, bez punktu rosy). Tu NIE MA osobnego modelu awarii sieci - zamiast
tego odczyt punktu rosy jest uznawany za "zawieszony", jeśli `PUNKT_ROSY_C` nie zmienia się przez
`DELTA_M_KROKOW=20` kolejnych kroków - dokładnie ten sam objaw, jaki daje realna awaria/rozłączenie
czujnika (`test_awarie_czujnikow._zrob_rozlaczenie` też "zamraża" ostatnią wartość), więc mechanizm
działa organicznie na PRAWDZIWYCH danych wejściowych, bez potrzeby symulowania osobnej sieci PLC.

## Zaobserwowane zachowanie (smoke test, Abisko + Ojmiakon, 5 dni)

Niska energia (354/459 kWh, wyraźnie poniżej normy), ale **bardzo wysoka kara bezpieczeństwa**
(2.7-14.4 mln °C·s) i skrajnie niski `min_hrt` (do -60°C w Ojmiakonie!) - dokładnie ten typ kompromisu
energia/bezpieczeństwo, który praca źródłowa sama opisuje jako ryzyko polityk P_mem/P_pre (patrz jej
Rys. 8-10: niższa energia bywa "opłacona" wyższą niedostępnością). Ten algorytm NIE MA (podobnie jak
oryginalna polityka w pracy) osobnego priorytetu "bezwzględna ochrona przed głębokim mrozem" - w
odróżnieniu od kaskady `funkcja_ryzyka_wspolne._evaluate_risk_setpoint` (priorytet #3) - świadoma
wierność źródłu, nie błąd implementacji. Patrz `../kara_bezpieczenstwa.md`.

## FLOPs

Szacunek analityczny: ~12/krok (proste porównania progowe + licznik niezmienności punktu rosy).

## Powiązania

Dziedziczy `rdzen_kontrolera.KontrolerBazowy` (pamięć czujników, choć bufor Kalmana tu nieużywany do
prognozy). Odpowiednik idei w tym projekcie bez punktu rosy: [histereza_let1.md](histereza_let1.md).
Siostrzany algorytm z tej samej pracy (polityka P_pre): [predykcja_wygladzanie_prosta.md](predykcja_wygladzanie_prosta.md).
