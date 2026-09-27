# fuzzy_ryzyko_adaptacyjny

- **Plik / klasa / metoda:** `Algorytmy/funkcja_fuzzy_ryzyko_adaptacyjny.py` / `KontrolerFuzzyRyzykoAdaptacyjny` /
  `fuzzy_ryzyko_adaptacyjny`
- **Typ:** Fuzzy logic (FL1, adaptacyjne progi) · **Cel:** Funkcja ryzyka (Kalman) · **Adaptacyjny:** tak ·
  **Bezpiecznik:** tak

## Jak działa

Jak [fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md) (cel z kaskady funkcji ryzyka, wykonawczo silnik rozmyty
FL1), ale dokłada dokładnie to, co `fuzzy_ryzyko_1` wprost zaznacza jako brak: "silnik rozmyty sam w
sobie nie jest przestrajany - nie ma odpowiednika SIMC dla progów rozmytych". Ten algorytm JEST tym
odpowiednikiem.

**Stosowana metoda**: identyczne "perturb-and-observe" (proste wspinanie po zboczu bez gradientu) co
[risk_function_pid_auto.md](risk_function_pid_auto.md) - tylko zastosowane do progów funkcji
przynależności silnika rozmytego (`silniki_fuzzy.wnioskowanie_fl_parametryzowane`, wydzielone z
`wnioskowanie_fl_podstawowe` żeby dało się je parametryzować BEZ zmiany zachowania FL1/FL2/FL3) zamiast
do progów setpointu funkcji ryzyka.

**Strojone progi** (4, każdy z własnym krokiem/granicami - patrz `KROK_STROJENIA`/`GRANICE_STROJENIA`):
- `prog_chlodno` - granica OK↔chłodno (`blad_T`, domyślnie 3.0°C)
- `prog_mrozno` - granica chłodno↔mroźno (`blad_T`, domyślnie 6.0°C)
- `prog_lodowato_dolny` - dolny koniec rampy "lodowato" (HRT, domyślnie -15.0°C)
- `prog_lodowato_gorny` - górny koniec rampy "lodowato" (HRT, domyślnie -12.0°C)

**Mechanizm**: co `OKRES_STROJENIA_S`=7 dni liczy koszt minionego okresu = zużyta moc (całka %·h) +
`WAGA_KARA_H`=50 × godziny z przekroczonym progiem śniegu/lodu/przegrzania (te same progi `KARA_*` co
`funkcja_nauka_kary_wspolna.py`). Spadek kosztu względem poprzedniego okresu → kontynuacja kierunku
zmiany KAŻDEGO progu; wzrost → odwrócenie kierunku wszystkich naraz. Historia logowana do
`self.historia_strojenia` (aliasowane na `historia_uczenia` - `test_wszystkie_rownolegle.py` zapisuje to
automatycznie do `*_uczenie.csv`, bez zmian w skrypcie testowym).

**Ograniczenia** (te same jak w `risk_function_pid_auto`): może utknąć w lokalnym minimum (brak losowej
eksploracji), potrzebuje kilku okresów żeby się ustabilizować, `WAGA_KARA_H` jest ręcznie dobraną stałą.

Zmierzone (smoke test, abisko, 8 dni - zbyt krótko na więcej niż ~1 aktualizację progów):
`fuzzy_ryzyko_adaptacyjny` energia=732.0 kWh vs `fuzzy_ryzyko_1` energia=730.8 kWh na tym samym oknie -
w tak krótkim oknie strojenie nie miało jeszcze czasu się objawić, potrzebny dłuższy przebieg (tygodnie),
żeby ocenić realną wartość dodaną.

## FLOPs

Szacunek: **45/krok** (silnik FL1 40 + rejestracja kar/całki strojenia ~5, amortyzowane jak w
`risk_function_pid_auto`). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_ryzyka_wspolne.KontrolerRyzykaBazowy` (setpoint) + silnik `silniki_fuzzy`
(`wnioskowanie_fl_parametryzowane`). Nieadaptacyjny punkt odniesienia:
[fuzzy_ryzyko_1.md](fuzzy_ryzyko_1.md). Ta sama metoda strojenia, inny obiekt strojenia:
[risk_function_pid_auto.md](risk_function_pid_auto.md).
