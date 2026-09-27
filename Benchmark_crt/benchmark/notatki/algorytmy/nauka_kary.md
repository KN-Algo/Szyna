# nauka_kary

- **Plik / klasa / metoda:** `Algorytmy/funkcja_nauka_kary_pid.py` / `KontrolerNaukaKaryPID` / `nauka_kary`
- **Typ:** PID (PI, uczący się z kar) · **Cel:** Progi normy LET-1 + nauczony czynnik ·
  **Adaptacyjny:** nie · **Bezpiecznik:** tak

## Jak działa

**Bazowy wariant rodziny "uczenie z kar"** (`funkcja_nauka_kary_wspolna.KontrolerNaukaKaryBazowy`) —
zamiast statycznych progów/kar (jak `funkcja_ryzyka_wspolne.py`) kontroler trzyma JEDNĄ liczbę,
`_czynnik_nauczony` (start=0), która z czasem adaptuje się do lokalnych warunków:

- **ROŚNIE**, gdy zaobserwowano zbyt dużo zalegającego śniegu (>5mm) lub lodu (>2mm, proxy: śnieg przy
  HRT≤0°C) — trzeba było grzać MOCNIEJ.
- **MALEJE**, gdy zaobserwowano przegrzanie (HRT>35°C) — trzeba było grzać SŁABIEJ.

Kary są ZLICZANE na bieżąco (co krok), ale aktualizacja czynnika następuje **raz na dobę**
(`OKRES_UCZENIA_S=86400s`) na podstawie zsumowanych kar z minionego okresu:
`_czynnik_nauczony += 0.5 * (kary_snieg + kary_lod - kary_przegrzanie)`, obcięte do zakresu [-5, +15]°C.
To prosty, jednowymiarowy integrator kar — bez formalnego gradientu/RL, świadomie zaakceptowany jako
wystarczający.

Efektywny cel grzania = próg normy LET-1 + `_czynnik_nauczony`. Ten wariant BAZOWY jest **czysto
reaktywny** — uczy się WYŁĄCZNIE z kar zaobserwowanych już PO fakcie, bez żadnej prognozy (w
odróżnieniu od `_temp`/`_opad`/`_blizniak`/`_ryzyko` niżej). Regulator wykonawczy: PI(D) identyczny
jak `norma_pid`/`risk_function_pid` (Kc=2.9262, Ti=3571.88, nastawy fabryczne — brak autotestu, więc
nigdy nie przeliczane).

Historia uczenia (`self.historia_uczenia`) zapisywana po każdej aktualizacji — trafia do osobnego CSV
(`<lokalizacja>_<algorytm>_uczenie.csv`) i zakładki "Uczenie_adaptacyjne" w Excelu z wykresem krzywej
uczenia.

## FLOPs

Szacunek: **30/krok** (progi normy 10 + PI(D) 15, rejestracja kar to proste porównania nieliczne
osobno + amortyzowana aktualizacja raz/dobę). Patrz [../FLOPs.md](../FLOPs.md).

## Powiązania

Dziedziczy `funkcja_nauka_kary_wspolna.KontrolerNaukaKaryBazowy` ← `funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy`.
Warianty z prognozą: [nauka_kary_temp.md](nauka_kary_temp.md), [nauka_kary_opad.md](nauka_kary_opad.md),
[nauka_kary_blizniak.md](nauka_kary_blizniak.md), [nauka_kary_ryzyko.md](nauka_kary_ryzyko.md) (łączy
wszystkie trzy).
