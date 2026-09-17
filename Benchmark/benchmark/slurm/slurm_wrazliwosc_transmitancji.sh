#!/bin/bash
# slurm_wrazliwosc_transmitancji.sh
#
# ANALIZA WRAŻLIWOŚCI na niepewność modelu obiektu (transmitancja GRZANIA,
# SOPDT K/T1/T2/L - patrz symulacja_fizyczna.przygotuj_modele_stanowe): PEŁNY
# przegląd (4 lokalizacje x 45 algorytmów, pełny zakres dat - lokalizacje
# ograniczone 2026-09-15, patrz SZYNA_LOKALIZACJE niżej) powtórzony dla 8
# scenariuszy, w których PRAWDZIWY symulowany obiekt (nie założenia żadnego
# algorytmu) ma zaburzone parametry względem nominalnych. Adaptacyjne algorytmy
# same identyfikują zaburzony obiekt przez autotest (cyfrowy bliźniak) -
# NIE wymaga to żadnej specjalnej obsługi przy mniejszej liczbie lokalizacji,
# autotest liczy się osobno dla każdej lokalizacji niezależnie od tego, ile
# ich jest w danym przebiegu:
#
#   0) nominal        - bez zaburzenia (referencja/baseline)
#   1) K+5%           - wzmocnienie grzałki +5%
#   2) K+10%
#   3) K+15%
#   4) T1+5%          - pierwsza stała czasowa +5%
#   5) T1+10%
#   6) T1+15%
#   7) K+10% i T1+10% JEDNOCZEŚNIE (mieszanie parametrów)
#
# Sens: algorytmy ADAPTACYJNE (autotest + cyfrowy bliźniak) same identyfikują
# PRAWDZIWY (zaburzony) obiekt z pomiarów, więc powinny się do niego
# dostroić - algorytmy NIEADAPTACYJNE (np. norma_pid, ze stałymi SIMC
# policzonymi OFFLINE z nominalnych parametrów) NIE wiedzą o zaburzeniu i będą
# działać na niedopasowanych nastawach. To jest właśnie to, co ta analiza ma
# pokazać: która strategia (adaptacyjna vs nie) jest odporniejsza na
# niepewność/dryf parametrów rzeczywistego obiektu.
#
# KOSZT: to jest 8x pełny przegląd (patrz slurm_pelny_przeglad.sh) - KAŻDY z 8
# elementów tablicy (--array=0-7) to OSOBNE zadanie SLURM z WŁASNĄ rezerwacją
# cpus x czas (nie dzielą jednej puli) - przy --cpus-per-task=64/--time=01:00:00
# to 64 CPU-h ceiling NA ELEMENT (ZMNIEJSZONE 2026-09-15 razem z ograniczeniem
# lokalizacji do 4 - poprzednio 768h/element przy 44 lokalizacjach), razem do
# 512 CPU-h dla całej tablicy, jeśli wszystkie 8 ruszyłoby jednocześnie -
# realny koszt szacunkowo ~170-340 CPU-h razem (patrz przelicznik przy --time
# wyżej). W praktyce QOS i tak dopuści tylko tyle jednocześnie, ile pozwala
# dostępny budżet (service-balance) - reszta poczeka w kolejce (status PD,
# powód QOSGrpCPUMinutesLimit) i wystartuje automatycznie, gdy wcześniejsze
# się skończą i zwolnią rezerwację - to NORMALNE, nie błąd, nie trzeba nic
# ręcznie robić.
#
# Wyniki każdego scenariusza lądują w OSOBNYM podfolderze
# wyniki/wrazliwosc_transmitancji/<scenariusz>/ (własny PRZEGLAD_ZBIORCZY.csv +
# Podsumowanie_wynikow.xlsx) - kolumna 'scenariusz'/'perturb_*_pct' w każdym
# CSV pozwala je później bezpiecznie scalić w jedną analizę porównawczą.
#
# UWAGA: SZYNA_ZAPISZ_CSV_SZCZEGOLOWE=0 (ustawione niżej) - przy 8 scenariuszach
# x 4 lokalizacje x 45 algorytmów szczegółowe CSV per (lokalizacja, algorytm)
# to tysiące zbędnych plików (nieużywanych przez żaden z dwóch generatorów
# Excela - patrz komentarz w test_wszystkie_rownolegle.py). Liczy się tylko
# PRZEGLAD_ZBIORCZY.csv -> Podsumowanie_wynikow.xlsx per scenariusz, potem
# generuj_excel_wrazliwosc_transmitancji.py scala 8 takich Exceli w jeden.
#
# WAŻNE: zlecaj TYLKO przez `sbatch` (kolejka SLURM), NIGDY przez `sh`/`bash`
# bezpośrednio w terminalu.
#
# Uruchomienie (z katalogu Benchmark/benchmark na klastrze):
#   sbatch slurm/slurm_wrazliwosc_transmitancji.sh
# Podgląd wybranego scenariusza osobno (np. tylko K+10%, indeks 2):
#   sbatch --array=2 slurm/slurm_wrazliwosc_transmitancji.sh

#SBATCH -J szyna_wrazliwosc
#SBATCH --account=hpc-wikjan2416-1787599067
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=1000G
#SBATCH --time=01:00:00
#SBATCH -p lem-cpu
#SBATCH --array=0-7
#SBATCH --output=szyna_wrazliwosc_%A_%a.log
# --time ZMNIEJSZONE 2026-09-15 (lokalizacje ograniczone do 4, patrz
# SZYNA_LOKALIZACJE niżej) - 64 rdzenie x 1h = 64 CPU-h ceiling NA ELEMENT
# tablicy (razem do 512 core-h dla całej tablicy 8 elementów, jeśli wszystkie
# ruszyłyby jednocześnie). Realny koszt per element szacunkowo ~21-43 core-h
# (192-384 core-h oryginalne x 4/44 lok. x 45/37 alg.), razem ~170-340 core-h
# dla całej tablicy - WIELOKROTNIE mniej niż poprzednie 768h/element, dzięki
# czemu ta tablica bezpiecznie mieści się w budżecie konta na raz (nie trzeba
# już zlecać jej osobno/na koniec, jak wcześniej przy 44 lokalizacjach).

set -euo pipefail

SCRIPT_DIR="$SLURM_SUBMIT_DIR"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/szyna_venv" ]; then
    python3 -m venv "$HOME/szyna_venv"
fi
source "$HOME/szyna_venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

# Mapowanie indeksu tablicy SLURM (SLURM_ARRAY_TASK_ID, 0-7) na konkretny
# scenariusz zaburzenia - patrz opis scenariuszy w nagłówku pliku.
case "$SLURM_ARRAY_TASK_ID" in
    0) export SZYNA_SCENARIUSZ="nominal";    export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=0 ;;
    1) export SZYNA_SCENARIUSZ="K_plus5";    export SZYNA_PERTURB_K=5;  export SZYNA_PERTURB_T1=0 ;;
    2) export SZYNA_SCENARIUSZ="K_plus10";   export SZYNA_PERTURB_K=10; export SZYNA_PERTURB_T1=0 ;;
    3) export SZYNA_SCENARIUSZ="K_plus15";   export SZYNA_PERTURB_K=15; export SZYNA_PERTURB_T1=0 ;;
    4) export SZYNA_SCENARIUSZ="T1_plus5";   export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=5 ;;
    5) export SZYNA_SCENARIUSZ="T1_plus10";  export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=10 ;;
    6) export SZYNA_SCENARIUSZ="T1_plus15";  export SZYNA_PERTURB_K=0;  export SZYNA_PERTURB_T1=15 ;;
    7) export SZYNA_SCENARIUSZ="K10_T1_10";  export SZYNA_PERTURB_K=10; export SZYNA_PERTURB_T1=10 ;;
    *) echo "Nieznany SLURM_ARRAY_TASK_ID=$SLURM_ARRAY_TASK_ID"; exit 1 ;;
esac

echo "Scenariusz: $SZYNA_SCENARIUSZ (K${SZYNA_PERTURB_K:+}% T1${SZYNA_PERTURB_T1:+}%)"

# Celowo NIE ustawiamy SZYNA_MAX_DNI/SZYNA_ALGORYTMY - pełny zakres dat,
# wszystkie algorytmy. SZYNA_LOKALIZACJE ograniczone do 4 (2026-09-15, na
# życzenie użytkownika - jak w slurm_pelny_przeglad.sh, patrz tam pełne
# uzasadnienie wyboru tych 4 lokalizacji).
export SZYNA_LOKALIZACJE="sodankyla_60min_2025,murmansk_60min_2025,quebec_city_60min_2025,norylsk_60min_2025"
export SZYNA_FOLDER_WYNIKOW="$SCRIPT_DIR/wyniki/wrazliwosc_transmitancji/$SZYNA_SCENARIUSZ"
export SZYNA_ZAPISZ_CSV_SZCZEGOLOWE=0

python testy/test_wszystkie_rownolegle.py
