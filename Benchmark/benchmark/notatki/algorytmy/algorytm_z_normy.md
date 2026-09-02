# algorytm_z_normy

- **Plik / klasa / metoda:** `Algorytmy/algorytm_z_normy.py` / `AutomatPogodowyNorma` / `compute_control`
- **Typ:** Automat pogodowy (histereza) · **Cel:** Progi normy LET-1 · **Adaptacyjny:** nie ·
  **Bezpiecznik:** nie (sam jest wyznacznikiem bezpiecznika dla pozostałych algorytmów)

## Jak działa

**Czysta, referencyjna implementacja normy LET-1** (Załącznik do uchwały Nr 1091/2025, pkt
2.4.12-2.4.19, wariant dwuczujnikowy CRT+HRT) — CELOWO bez żadnej logiki spoza normy: brak pamięci,
prognozy, oceny ryzyka 0-10 czy ciągłego regulatora. Tylko progi załączenia/wyłączenia z Tabeli nr 5
(opady) i Tabeli nr 6 (suchy mróz), identyczne liczbowo jak w `compute_control`, ale bez dodatkowego
licznika ryzyka.

Rola w projekcie: **referencja bezpieczeństwa**. W porównaniach (`test_wszystkie_algorytmy_*`) ten
algorytm dostarcza grubość śniegu/moc jako `snow_reference_mm` — wszystkie pozostałe "inteligentne"
algorytmy (poza `compute_control`) mają zakaz przekroczenia tej referencji w żadnej chwili
(`bezpiecznik: True` w rejestrze). To znaczy: żaden "sprytniejszy" algorytm nie wolno mu pozwolić
zalec więcej śniegu niż zalegałoby przy czystej normie.

Nie dziedziczy `KontrolerBazowy` (brak potrzeby pamięci/prognozy) — ma własną, lekką strukturę
`RowDataNorma` i własny `_flops_licznik`.

## Diagnostyka (IAE/ISE/ITAE)

Zwraca `(moc, diagnostics)` — `target_temperature` to próg WYŁĄCZENIA aktywnej gałęzi (opady/suchy
mróz) gdy `heating_on=True`, `need_heat=heating_on` (jak `compute_control`).

## FLOPs

Szacunek: **18/krok** (porównania progów + logika stanu, stały koszt). Najtańszy obliczeniowo
algorytm w projekcie razem z `fuzzy_normy_1/2` na poziomie 40. Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Samodzielny plik, brak zależności od `rdzen_kontrolera.py`. Punkt odniesienia (progi) dla
`funkcja_normy_wspolne.py` (wersja z ciągłym setpointem dla PID/fuzzy) i pośrednio dla całej rodziny
`nauka_kary_*` (bazowy cel przed dodaniem czynnika nauczonego).
