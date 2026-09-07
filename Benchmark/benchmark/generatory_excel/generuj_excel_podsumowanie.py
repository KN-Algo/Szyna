# generuj_excel_podsumowanie.py
#
# Buduje plik Excel (.xlsx) podsumowujący wyniki dużego przeglądu
# (test_wszystkie_algorytmy_wszystkie_lokalizacje.py -> PRZEGLAD_ZBIORCZY.csv):
#   - "Dane"                    - surowa tabela, jeden wiersz na (lokalizacja, rok, algorytm)
#   - "Podsumowanie_algorytmy"  - porównanie wszystkich algorytmów globalnie (formuły)
#   - "Podsumowanie_lokalizacje"- średnia energia per lokalizacja x algorytm (formuły)
#   - "Opisy_algorytmow"        - ściąga: typ regulatora / cel (setpoint) / czy adaptacyjny
#                                  (autotest) / opis - wprost z Algorytmy/rejestr_algorytmow.py
#   - "Zlozonosc_obliczeniowa"  - szacunkowa złożoność czasowa/pamięciowa i FLOPs/krok każdego
#                                  algorytmu (analiza kodu, nie profiler) - wprost z rejestru
#   - "Uczenie_adaptacyjne"     - krzywa uczenia (czynnik_nauczony w czasie) rodziny
#                                  nauka_kary_* - wczytywana z osobnych plików
#                                  <lokalizacja>_<algorytm>_uczenie.csv (patrz
#                                  test_wszystkie_rownolegle.py), nie z PRZEGLAD_ZBIORCZY.csv
#   - "Wnioski"                 - tekstowe podsumowanie z konkretnymi liczbami
#
# Wartości w zakładkach "Podsumowanie_*" są formułami Excela odwołującymi się
# do zakładki "Dane" - podmiana/dopisanie wierszy w "Dane" automatycznie
# przeliczy resztę (poza "Wnioski", która jest tekstem opisowym).

import os
import re
import sys
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule, ColorScaleRule
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference
import glob

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmark/ (rodzic generatory_excel/)
sys.path.insert(0, os.path.join(BASE_DIR, 'Algorytmy'))
from rejestr_algorytmow import ALGORYTMY  # noqa: E402 - opisy/typ/cel/adaptacyjny dla zakładki "Opisy_algorytmow"
# SZYNA_FOLDER_WYNIKOW pozwala przekierować wejście/wyjście do innego folderu
# (patrz ten sam mechanizm w test_wszystkie_rownolegle.py) - bez tego wywołanie
# generuj_excel_podsumowanie.main() po przebiegu zapisanym gdzie indziej niż
# domyślny folder szukałoby CSV w złym miejscu.
FOLDER_WYNIKOW = os.environ.get(
    'SZYNA_FOLDER_WYNIKOW', os.path.join(BASE_DIR, "wyniki", "przeglad_wielu_lokalizacji"))
SCIEZKA_CSV = os.path.join(FOLDER_WYNIKOW, "PRZEGLAD_ZBIORCZY.csv")
SCIEZKA_XLSX = os.path.join(FOLDER_WYNIKOW, "Podsumowanie_wynikow.xlsx")

# Życiowy budżet przełączeń przekaźnika/styku - patrz uzasadnienie przy
# MAX_SWITCHES_PER_DAY w test_wszystkie_rownolegle.py (ta sama zmienna
# środowiskowa, żeby oba skrypty zawsze zgadzały się co do tej liczby).
BUDZET_PRZELACZEN_CALKOWITY = int(os.environ.get('SZYNA_BUDZET_PRZELACZEN', '500000'))

# UWAGA: przy każdym dodaniu nowej lokalizacji (nowy plik w Pogoda_pomiary_15_minut/)
# trzeba dopisać tu jej poprawną nazwę wyświetlaną (z diakrytykami/dywizami, gdzie
# trzeba) - inaczej parsuj_lokalizacje() cicho spadnie na fallback
# klucz.replace('_',' ').title(), który: 1) gubi diakrytyki (np. "Wladywostok"
# zamiast "Władywostok"), 2) źle kapitalizuje partykuły typu "de" w nazwach
# wieloczłonowych (np. "San Carlos De Bariloche" zamiast "...de Bariloche").
NAZWY_MIAST = {
    # --- Pierwotne 10 lokalizacji ---
    'abisko': 'Abisko', 'fairbanks': 'Fairbanks', 'jakuck': 'Jakuck',
    'krakow': 'Kraków', 'ojmiakon': 'Ojmiakon', 'old_crow': 'Old Crow',
    'oslo': 'Oslo', 'puszcza_bialowieska': 'Puszcza Białowieska',
    'suwalki': 'Suwałki', 'wroclaw': 'Wrocław',
    # --- 34 nowe lokalizacje (2026-09-03) ---
    'ushuaia': 'Ushuaia', 'san_carlos_de_bariloche': 'San Carlos de Bariloche',
    'punta_arenas': 'Punta Arenas', 'coyhaique': 'Coyhaique',
    'harbin': 'Harbin', 'mohe': 'Mohe', 'urumczi': 'Urumczi', 'lhasa': 'Lhasa',
    'norylsk': 'Norylsk', 'wladywostok': 'Władywostok', 'murmansk': 'Murmańsk',
    'rovaniemi': 'Rovaniemi', 'sodankyla': 'Sodankylä',
    'kiruna': 'Kiruna', 'ostersund': 'Östersund',
    'tromso': 'Tromsø', 'roros': 'Røros',
    'reykjavik': 'Reykjavík', 'akureyri': 'Akureyri',
    'banff': 'Banff', 'yellowknife': 'Yellowknife', 'quebec_city': 'Quebec City',
    'anchorage': 'Anchorage', 'duluth': 'Duluth',
    'garmisch_partenkirchen': 'Garmisch-Partenkirchen', 'oberstdorf': 'Oberstdorf',
    'aviemore': 'Aviemore', 'braemar': 'Braemar',
    'sapporo': 'Sapporo', 'nagano': 'Nagano',
    'manali': 'Manali', 'gulmarg': 'Gulmarg',
    'sutherland': 'Sutherland', 'mount_hotham': 'Mount Hotham',
}

# Kolejność = norma jako baza odniesienia, potem pozostałe algorytmy w kolejności
# rejestru (Algorytmy/rejestr_algorytmow.py).
NAZWY_ALGORYTMOW = {
    'algorytm_z_normy': 'Automat z normy (bazowy)',
    'compute_control': 'Histereza LET-1',
    'compute_control_gorski': 'Histereza LET-1 (rejon górski)',
    'risk_function': 'Funkcja ryzyka (binarna)',
    'risk_function_pid': 'Funkcja ryzyka (PID)',
    'risk_function_pid_auto': 'Funkcja ryzyka (PID, auto-strojenie)',
    'norma_pid': 'PID z normą',
    'fuzzy_logic_1': 'Fuzzy Logic 1 (ciągły)',
    'fuzzy_logic_2': 'Fuzzy Logic 2 (binarny)',
    'fuzzy_logic_2v2': 'Fuzzy Logic 2v2 (binarny)',
    'fuzzy_logic_3': 'Fuzzy Logic 3 (PWM)',
    'fuzzy_ryzyko_1': 'Fuzzy + ryzyko (FL1, ciągły)',
    'fuzzy_ryzyko_2': 'Fuzzy + ryzyko (FL2, binarny)',
    'fuzzy_ryzyko_2v2': 'Fuzzy + ryzyko (FL2v2, binarny)',
    'fuzzy_ryzyko_3': 'Fuzzy + ryzyko (FL3, PWM)',
    'fuzzy_normy_1': 'Fuzzy + norma (FL1, ciągły)',
    'fuzzy_normy_2': 'Fuzzy + norma (FL2, binarny)',
    'fuzzy_normy_2v2': 'Fuzzy + norma (FL2v2, binarny)',
    'fuzzy_normy_3': 'Fuzzy + norma (FL3, PWM)',
    'risk_function_opad': 'Funkcja ryzyka (binarna) + opad',
    'risk_function_pid_opad': 'Funkcja ryzyka (PID) + opad',
    'fuzzy_ryzyko_1_opad': 'Fuzzy + ryzyko + opad (FL1, ciągły)',
    'fuzzy_ryzyko_2_opad': 'Fuzzy + ryzyko + opad (FL2, binarny)',
    'fuzzy_ryzyko_2v2_opad': 'Fuzzy + ryzyko + opad (FL2v2, binarny)',
    'fuzzy_ryzyko_3_opad': 'Fuzzy + ryzyko + opad (FL3, PWM)',
    'nauka_kary': 'Uczenie z kar (bazowy)',
    'nauka_kary_temp': 'Uczenie z kar + prognoza temp.',
    'nauka_kary_opad': 'Uczenie z kar + prognoza opadu',
    'nauka_kary_blizniak': 'Uczenie z kar + cyfrowy bliźniak',
    'nauka_kary_ryzyko': 'Uczenie z kar + pełne ryzyko',
    'mpc_liniowy': 'MPC (bez prognozy pogody)',
    'mpc_prognoza_pogody': 'MPC (z prognozą pogody)',
    'mpc_miekkie_ograniczenia': 'MPC (bariera wykładnicza)',
    'histereza_pamiec_rosy': 'Histereza + punkt rosy (pamięć)',
    'predykcja_wygladzanie_prosta': 'Predykcja (wygładzanie Holta)',
    'risk_function_ladrc': 'ADRC (liniowy, LADRC)',
    'risk_function_nadrc': 'ADRC (nieliniowy, NADRC)',
}
ALGORYTM_BAZOWY = 'Automat z normy (bazowy)'

# Algorytmy z rodziny "uczenia z kar" - dostają WŁASNĄ zakładkę
# "Uczenie_adaptacyjne" pokazującą jak _czynnik_nauczony (i kary) zmieniają się
# W CZASIE trwania symulacji (krzywa uczenia) - patrz KLUCZE_UCZENIA_KARY niżej
# i sekcja budująca tę zakładkę w main().
KLUCZE_UCZENIA_KARY = ['nauka_kary', 'nauka_kary_temp', 'nauka_kary_opad',
                        'nauka_kary_blizniak', 'nauka_kary_ryzyko']

FONT_NAZWA = 'Arial'
KOLOR_NAGLOWEK_BG = '1F4E78'
KOLOR_NAGLOWEK_FG = 'FFFFFF'
KOLOR_ANOMALIA = 'FFC7CE'
KOLOR_ANOMALIA_TEKST = '9C0006'

FONT_NAGLOWEK = Font(name=FONT_NAZWA, bold=True, color=KOLOR_NAGLOWEK_FG, size=11)
FILL_NAGLOWEK = PatternFill('solid', fgColor=KOLOR_NAGLOWEK_BG)
FONT_ZWYKLY = Font(name=FONT_NAZWA, size=10)
FONT_POGRUBIONY = Font(name=FONT_NAZWA, bold=True, size=10)
WYROWNANIE_SRODEK = Alignment(horizontal='center', vertical='center')
OBRAMOWANIE_CIENKIE = Border(*(Side(style='thin', color='B7B7B7') for _ in range(4)))


def parsuj_lokalizacje(lokalizacja):
    """'krakow_60min_2021' -> ('Kraków', '60min', 2021). Działa też dla 'suwalki_15min_2023'."""
    dopasowanie = re.match(r'^(.+)_(\d+min)_(\d{4})$', lokalizacja)
    if not dopasowanie:
        raise ValueError(f"Nie rozpoznano formatu nazwy lokalizacji: {lokalizacja}")
    klucz_miasta, interwal, rok = dopasowanie.groups()
    miasto = NAZWY_MIAST.get(klucz_miasta, klucz_miasta.replace('_', ' ').title())
    return miasto, interwal, int(rok)


def ustaw_naglowek(ws, wiersz, kolumny):
    for i, nazwa in enumerate(kolumny, start=1):
        komorka = ws.cell(row=wiersz, column=i, value=nazwa)
        komorka.font = FONT_NAGLOWEK
        komorka.fill = FILL_NAGLOWEK
        komorka.alignment = WYROWNANIE_SRODEK
        komorka.border = OBRAMOWANIE_CIENKIE


def autoszerokosc(ws, min_szer=10, max_szer=42):
    for kolumna_komorki in ws.columns:
        dlugosc = 0
        litera = None
        for komorka in kolumna_komorki:
            if litera is None:
                litera = getattr(komorka, 'column_letter', None)
            if litera is None:
                continue
            if komorka.value is not None:
                dlugosc = max(dlugosc, len(str(komorka.value)))
        if litera:
            ws.column_dimensions[litera].width = max(min_szer, min(max_szer, dlugosc + 3))


def main():
    df = pd.read_csv(SCIEZKA_CSV)
    df[['Lokalizacja', 'Interwal', 'Rok']] = df['lokalizacja'].apply(lambda x: pd.Series(parsuj_lokalizacje(x)))
    df['Algorytm'] = df['name'].map(NAZWY_ALGORYTMOW)

    wb = Workbook()

    # ==========================================================================
    # ZAKŁADKA "Dane"
    # ==========================================================================
    ws_dane = wb.active
    ws_dane.title = 'Dane'
    # IAE/ISE/ITAE (patrz symulacja_fizyczna.uruchom_kontroler) - mierzą jak
    # dobrze RZECZYWISTA HRT nadąża za temperaturą zadaną (target_temperature)
    # wyliczaną przez kontroler, scałkowane po czasie przez okresy, w których
    # kontroler faktycznie chciał grzać (need_heat=True). Puste dla algorytmów
    # bez jawnego, ciągłego celu (compute_control*, algorytm_z_normy,
    # fuzzy_logic_*) - te sterują progami/regułami wprost, bez pośredniego
    # "celu" do porównania.
    ma_iae = 'iae' in df.columns
    # 'kara_bezpieczenstwa'/'epizody_ponizej_floor'/'min_hrt' (patrz
    # symulacja_fizyczna.uruchom_kontroler i notatki/kara_bezpieczenstwa.md) -
    # W ODRÓŻNIENIU od IAE/ISE/ITAE (jak DOBRZE algorytm trzyma się WŁASNEGO
    # celu) to miara WYNIKU fizycznego wobec BEZWZGLĘDNYCH progów
    # bezpieczeństwa normy, ta sama dla WSZYSTKICH algorytmów niezależnie od
    # tego, jaki cel sobie wyznaczają.
    ma_kara = 'kara_bezpieczenstwa' in df.columns
    ma_min_hrt = 'min_hrt' in df.columns
    naglowki_dane = ['Lokalizacja', 'Interwał', 'Rok', 'Algorytm', 'Energia (kWh)',
                      'Przełączenia', 'Max śnieg (mm)', 'Max HRT (°C)', 'FLOPs (zmierzone)',
                      'IAE (°C·s)', 'ISE (°C²·s)', 'ITAE (°C·s²)',
                      'Min HRT (°C)', 'Kara bezpieczeństwa (°C·s)', 'Epizody HRT<-10°C',
                      'IAE % vs norma LET-1', 'ISE % vs norma LET-1', 'ITAE % vs norma LET-1',
                      'Kara bezp. % vs norma LET-1']
    ustaw_naglowek(ws_dane, 1, naglowki_dane)

    # --- % WZGLĘDEM NORMY LET-1 (algorytm_z_normy = ALGORYTM_BAZOWY) - na życzenie
    # użytkownika: "niech on będzie naszym punktem odniesienia do całości". Osobny
    # baseline DLA KAŻDEJ (Lokalizacja, Interwał, Rok) - nie jeden globalny numer -
    # bo IAE/kara zależą silnie od konkretnej pogody tego przebiegu, a nie tylko
    # algorytmu. ---
    baseline_lookup = {}
    if ma_iae or ma_kara:
        baza_df = df[df['Algorytm'] == ALGORYTM_BAZOWY].set_index(['Lokalizacja', 'Interwal', 'Rok'])
        for klucz, wiersz_bazowy in baza_df.iterrows():
            baseline_lookup[klucz] = {
                'iae': wiersz_bazowy.get('iae'),
                'ise': wiersz_bazowy.get('ise'),
                'itae': wiersz_bazowy.get('itae'),
                'kara_bezpieczenstwa': wiersz_bazowy.get('kara_bezpieczenstwa'),
            }

    def _pct_vs_norma(wartosc, klucz_baseline, pole):
        if pd.isna(wartosc):
            return None
        baza = baseline_lookup.get(klucz_baseline, {}).get(pole)
        if baza is None or pd.isna(baza) or baza == 0:
            return None
        return (float(wartosc) - float(baza)) / float(baza) * 100.0

    ma_flopy = 'flops_rzeczywiste' in df.columns
    for i, wiersz in enumerate(df.itertuples(index=False), start=2):
        flopy = getattr(wiersz, 'flops_rzeczywiste', None) if ma_flopy else None
        iae = getattr(wiersz, 'iae', None) if ma_iae else None
        ise = getattr(wiersz, 'ise', None) if ma_iae else None
        itae = getattr(wiersz, 'itae', None) if ma_iae else None
        min_hrt = getattr(wiersz, 'min_hrt', None) if ma_min_hrt else None
        kara = getattr(wiersz, 'kara_bezpieczenstwa', None) if ma_kara else None
        epizody_floor = getattr(wiersz, 'epizody_ponizej_floor', None) if ma_kara else None
        klucz_baseline = (wiersz.Lokalizacja, wiersz.Interwal, wiersz.Rok)
        iae_pct = _pct_vs_norma(iae, klucz_baseline, 'iae')
        ise_pct = _pct_vs_norma(ise, klucz_baseline, 'ise')
        itae_pct = _pct_vs_norma(itae, klucz_baseline, 'itae')
        kara_pct = _pct_vs_norma(kara, klucz_baseline, 'kara_bezpieczenstwa')
        wartosci = [wiersz.Lokalizacja, wiersz.Interwal, wiersz.Rok, wiersz.Algorytm,
                    round(wiersz.energia_kwh, 2), int(wiersz.przelaczenia),
                    round(wiersz.max_snieg_mm, 2), round(wiersz.max_hrt, 2),
                    int(flopy) if pd.notna(flopy) else None,
                    round(iae, 1) if pd.notna(iae) else None,
                    round(ise, 1) if pd.notna(ise) else None,
                    round(itae, 1) if pd.notna(itae) else None,
                    round(min_hrt, 2) if pd.notna(min_hrt) else None,
                    round(kara, 1) if pd.notna(kara) else None,
                    int(epizody_floor) if pd.notna(epizody_floor) else None,
                    round(iae_pct, 1) if iae_pct is not None else None,
                    round(ise_pct, 1) if ise_pct is not None else None,
                    round(itae_pct, 1) if itae_pct is not None else None,
                    round(kara_pct, 1) if kara_pct is not None else None]
        for j, wartosc in enumerate(wartosci, start=1):
            komorka = ws_dane.cell(row=i, column=j, value=wartosc)
            komorka.font = FONT_ZWYKLY
            komorka.border = OBRAMOWANIE_CIENKIE
            if j == 3:
                komorka.alignment = WYROWNANIE_SRODEK
            if j == 9:
                komorka.number_format = '0.00E+00'
            if j in (16, 17, 18, 19):
                komorka.number_format = '+0.0"%";-0.0"%"'

    ostatni_wiersz_dane = len(df) + 1
    ws_dane.freeze_panes = 'A2'
    ws_dane.auto_filter.ref = f'A1:S{ostatni_wiersz_dane}'
    if ma_iae or ma_kara:
        for litera in ('P', 'Q', 'R', 'S'):
            skala = ColorScaleRule(start_type='min', start_color='63BE7B', mid_type='num', mid_value=0, mid_color='FFEB84',
                                    end_type='max', end_color='F8696B')
            ws_dane.conditional_formatting.add(f'{litera}2:{litera}{ostatni_wiersz_dane}', skala)

    # Podświetlenie wierszy z podejrzanym przegrzaniem (Max HRT > 35°C) LUB
    # jakąkolwiek karą bezpieczeństwa > 0 (śnieg/marznący deszcz/mróz poza
    # bezpiecznym zakresem - patrz notatki/kara_bezpieczenstwa.md).
    fill_anomalia = PatternFill('solid', fgColor=KOLOR_ANOMALIA)
    font_anomalia = Font(name=FONT_NAZWA, size=10, color=KOLOR_ANOMALIA_TEKST)
    ws_dane.conditional_formatting.add(
        f'A2:S{ostatni_wiersz_dane}',
        FormulaRule(formula=['$H2>35'], fill=fill_anomalia, font=font_anomalia),
    )
    if ma_kara:
        ws_dane.conditional_formatting.add(
            f'A2:S{ostatni_wiersz_dane}',
            FormulaRule(formula=['$N2>0'], fill=fill_anomalia, font=font_anomalia),
        )

    autoszerokosc(ws_dane)

    # ==========================================================================
    # ZAKŁADKA "Podsumowanie_algorytmy"
    # ==========================================================================
    ws_alg = wb.create_sheet('Podsumowanie_algorytmy')
    naglowki_alg = ['Algorytm', 'Średnia energia (kWh)', 'Min energia (kWh)', 'Max energia (kWh)',
                     'Średnie przełączenia', 'Średni max śnieg (mm)', 'Średni max HRT (°C)',
                     'Liczba przypadków przegrzania (HRT>35°C)',
                     'Przełączenia/dzień (śr.)', 'Przewidywane przełączenia/rok',
                     f'% budżetu życiowego ({BUDZET_PRZELACZEN_CALKOWITY:,}) zużyty/rok'.replace(',', ' '),
                     'Max śnieg GLOBALNIE (mm, najgorszy przypadek ze wszystkich pogód)',
                     'Średnie IAE (°C·s)', 'Średnie ISE (°C²·s)', 'Średnie ITAE (°C·s²)',
                     'Średnia kara bezpieczeństwa (°C·s)', 'Min HRT GLOBALNIE (°C, najgorszy przypadek)',
                     'Lokalizacja najgorszego przypadku (min HRT)', 'Suma epizodów HRT<-10°C']
    ustaw_naglowek(ws_alg, 1, naglowki_alg)

    # Budżet przełączeń dotyczy WYŁĄCZNIE algorytmów o wyjściu binarnym/dyskretnym
    # (histereza, FL2/FL2v2/FL3) - dla ciągłych (PID, FL1) liczba przełączeń nie
    # mówi nic o zużyciu mechanicznym styku, więc kolumny 9-11 zostają puste
    # (patrz uzasadnienie w test_wszystkie_rownolegle.py przy MAX_SWITCHES_PER_DAY).
    def _czy_dyskretny(typ):
        return not (typ.startswith('PID') or 'FL1' in typ)

    dyskretnosc_per_alg = {k: _czy_dyskretny(ALGORYTMY.get(k, {}).get('typ', '')) for k in NAZWY_ALGORYTMOW}
    sr_dni_per_alg = df.groupby('name')['dni'].mean() if 'dni' in df.columns else None
    sr_przelaczen_per_alg = df.groupby('name')['przelaczenia'].mean() if 'przelaczenia' in df.columns else None

    lista_algorytmow = list(NAZWY_ALGORYTMOW.values())
    for i, (klucz, algorytm) in enumerate(NAZWY_ALGORYTMOW.items(), start=2):
        ws_alg.cell(row=i, column=1, value=algorytm).font = FONT_POGRUBIONY
        ws_alg.cell(row=i, column=2, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$E$2:$E${ostatni_wiersz_dane})'
        ))
        ws_alg.cell(row=i, column=3, value=(
            f'=_xlfn.MINIFS(Dane!$E$2:$E${ostatni_wiersz_dane}, Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i})'
        ))
        ws_alg.cell(row=i, column=4, value=(
            f'=_xlfn.MAXIFS(Dane!$E$2:$E${ostatni_wiersz_dane}, Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i})'
        ))
        ws_alg.cell(row=i, column=5, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$F$2:$F${ostatni_wiersz_dane})'
        ))
        ws_alg.cell(row=i, column=6, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$G$2:$G${ostatni_wiersz_dane})'
        ))
        ws_alg.cell(row=i, column=7, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$H$2:$H${ostatni_wiersz_dane})'
        ))
        ws_alg.cell(row=i, column=8, value=(
            f'=COUNTIFS(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$H$2:$H${ostatni_wiersz_dane}, ">35")'
        ))
        ws_alg.cell(row=i, column=12, value=(
            f'=_xlfn.MAXIFS(Dane!$G$2:$G${ostatni_wiersz_dane}, Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i})'
        ))
        ws_alg.cell(row=i, column=13, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$J$2:$J${ostatni_wiersz_dane})'
        ))
        ws_alg.cell(row=i, column=14, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$K$2:$K${ostatni_wiersz_dane})'
        ))
        ws_alg.cell(row=i, column=15, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$L$2:$L${ostatni_wiersz_dane})'
        ))
        # Kara bezpieczeństwa / min HRT / lokalizacja najgorszego przypadku / suma epizodów <-10°C -
        # patrz notatki/kara_bezpieczenstwa.md. Kolumny Dane: M=Min HRT, N=Kara bezpieczeństwa, O=Epizody.
        ws_alg.cell(row=i, column=16, value=(
            f'=AVERAGEIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$N$2:$N${ostatni_wiersz_dane})'
        ))
        ws_alg.cell(row=i, column=17, value=(
            f'=_xlfn.MINIFS(Dane!$M$2:$M${ostatni_wiersz_dane}, Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i})'
        ))
        # "Podwójny INDEX" zamiast formuły tablicowej (CSE) - działa jako zwykła formuła w Excelu,
        # zwraca lokalizację z Dane!A odpowiadającą wierszowi, gdzie ZARÓWNO algorytm (D), JAK I
        # min HRT (M) pasują do wartości z kolumny Q tego samego wiersza.
        ws_alg.cell(row=i, column=18, value=(
            f'=IFERROR(INDEX(Dane!$A$2:$A${ostatni_wiersz_dane}, MATCH(1, '
            f'INDEX((Dane!$D$2:$D${ostatni_wiersz_dane}=$A{i})*(Dane!$M$2:$M${ostatni_wiersz_dane}=$Q{i}), 0), 0)), "")'
        ))
        ws_alg.cell(row=i, column=19, value=(
            f'=SUMIF(Dane!$D$2:$D${ostatni_wiersz_dane}, $A{i}, Dane!$O$2:$O${ostatni_wiersz_dane})'
        ))

        if dyskretnosc_per_alg.get(klucz) and sr_przelaczen_per_alg is not None and sr_dni_per_alg is not None:
            sr_dni = sr_dni_per_alg.get(klucz)
            sr_przel = sr_przelaczen_per_alg.get(klucz)
            if sr_dni is not None and pd.notna(sr_dni) and sr_dni > 0 and sr_przel is not None and pd.notna(sr_przel):
                przel_dzien = sr_przel / sr_dni
                przel_rok = przel_dzien * 365.0
                proc_budzetu_rok = przel_rok / BUDZET_PRZELACZEN_CALKOWITY * 100.0
                ws_alg.cell(row=i, column=9, value=przel_dzien)
                ws_alg.cell(row=i, column=10, value=przel_rok)
                ws_alg.cell(row=i, column=11, value=proc_budzetu_rok)

        FORMATY_KOLUMN_ALG = {8: '0', 10: '0', 11: '0.00"%"', 13: '0.0', 14: '0.0', 15: '0.0',
                               16: '0.0', 17: '0.00', 19: '0'}
        for kol in range(2, 20):
            if kol == 18:
                ws_alg.cell(row=i, column=kol).border = OBRAMOWANIE_CIENKIE
                continue  # kolumna tekstowa (lokalizacja) - bez formatu liczbowego.
            komorka = ws_alg.cell(row=i, column=kol)
            komorka.font = FONT_ZWYKLY
            komorka.number_format = FORMATY_KOLUMN_ALG.get(kol, '0.00')
            komorka.border = OBRAMOWANIE_CIENKIE

    ostatni_wiersz_alg = len(lista_algorytmow) + 1
    for litera, odwrocona in [('B', True), ('E', True), ('F', True), ('G', True), ('H', True),
                               ('L', True), ('M', True), ('N', True), ('O', True),
                               ('P', True), ('Q', False), ('S', True)]:
        if odwrocona:
            skala = ColorScaleRule(start_type='min', start_color='63BE7B',
                                    end_type='max', end_color='F8696B')
        else:
            skala = ColorScaleRule(start_type='min', start_color='F8696B',
                                    end_type='max', end_color='63BE7B')
        ws_alg.conditional_formatting.add(f'{litera}2:{litera}{ostatni_wiersz_alg}', skala)

    autoszerokosc(ws_alg)

    # ==========================================================================
    # ZAKŁADKA "Wrazliwosc_wag_kary" - CZY RANKING algorytmów wg kary
    # bezpieczeństwa jest stabilny niezależnie od (z natury nieco arbitralnego)
    # doboru wag trzech składowych (śnieg/marznący deszcz/floor -10°C)? Kolumny
    # 'kara_bezpieczenstwa__<scenariusz>' (patrz KARA_WAGI_SCENARIUSZE w
    # funkcja_ryzyka_wspolne.py) liczone RÓWNOLEGLE z wariantem nominalnym w
    # TYM SAMYM przebiegu symulacji - pomijana bez błędu, jeśli dane pochodzą
    # sprzed dodania tej analizy (kolumny jeszcze nie istnieją).
    # ==========================================================================
    kolumny_scenariuszy_kary = sorted(c for c in df.columns if c.startswith('kara_bezpieczenstwa__'))
    if ma_kara and kolumny_scenariuszy_kary:
        ws_waga = wb.create_sheet('Wrazliwosc_wag_kary')
        ws_waga.cell(row=1, column=1, value=(
            'Każdy scenariusz zaburza JEDNĄ z trzech wag kary bezpieczeństwa o +/-50% względem '
            'nominalnej (pozostałe dwie bez zmian) - patrz KARA_WAGI_SCENARIUSZE w '
            'funkcja_ryzyka_wspolne.py i notatki/kara_bezpieczenstwa.md. Cel: sprawdzić, czy RANKING '
            'algorytmów wg kary bezpieczeństwa (1 = najbezpieczniejszy) jest stabilny niezależnie od '
            'dokładnego doboru tych wag. "Δ ranga" = zmiana pozycji względem rankingu nominalnego '
            '(0 = bez zmian, dodatnie = spadł w rankingu czyli wypadł GORZEJ pod tą wagą).'
        ))
        ws_waga.cell(row=1, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')
        ostatnia_kolumna_waga = 2 + 2 * len(kolumny_scenariuszy_kary)
        ws_waga.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ostatnia_kolumna_waga)

        agregaty_scen = df.groupby('Algorytm')[['kara_bezpieczenstwa'] + kolumny_scenariuszy_kary].mean().reindex(lista_algorytmow)
        # Tylko algorytmy FAKTYCZNIE obecne w tym przebiegu (reindex wyżej wstawia
        # NaN dla brakujących - np. przy filtrowanym/testowym przebiegu) - inaczej
        # .rank()/int() na samych NaN wysypałoby zapis.
        lista_algorytmow_waga = [a for a in lista_algorytmow if pd.notna(agregaty_scen.loc[a, 'kara_bezpieczenstwa'])]
        agregaty_scen = agregaty_scen.loc[lista_algorytmow_waga]
        ranga_nominalna = agregaty_scen['kara_bezpieczenstwa'].rank(method='min')

        WIERSZ_NAGLOWKA_WAGA = 2
        naglowki_waga = ['Algorytm', 'Kara nominalna (śr.)', 'Ranga nominalna']
        for kol in kolumny_scenariuszy_kary:
            etykieta = kol.replace('kara_bezpieczenstwa__', '')
            naglowki_waga += [f'Kara {etykieta} (śr.)', f'Δ ranga {etykieta}']
        ustaw_naglowek(ws_waga, WIERSZ_NAGLOWKA_WAGA, naglowki_waga)

        korelacje_spearman = {}
        for wiersz_i, alg in enumerate(lista_algorytmow_waga, start=WIERSZ_NAGLOWKA_WAGA + 1):
            ws_waga.cell(row=wiersz_i, column=1, value=alg).font = FONT_ZWYKLY
            ws_waga.cell(row=wiersz_i, column=2, value=round(agregaty_scen.loc[alg, 'kara_bezpieczenstwa'], 2)).font = FONT_ZWYKLY
            ws_waga.cell(row=wiersz_i, column=3, value=int(ranga_nominalna.loc[alg])).font = FONT_ZWYKLY
            kolumna = 4
            for kol in kolumny_scenariuszy_kary:
                ranga_scen = agregaty_scen[kol].rank(method='min')
                delta = int(ranga_scen.loc[alg] - ranga_nominalna.loc[alg])
                ws_waga.cell(row=wiersz_i, column=kolumna,
                              value=round(agregaty_scen.loc[alg, kol], 2)).font = FONT_ZWYKLY
                komorka_delta = ws_waga.cell(row=wiersz_i, column=kolumna + 1, value=delta)
                komorka_delta.font = FONT_ZWYKLY
                korelacje_spearman.setdefault(kol, ranga_scen)
                kolumna += 2
        for wiersz_komorki in ws_waga.iter_rows(min_row=WIERSZ_NAGLOWKA_WAGA + 1, max_row=WIERSZ_NAGLOWKA_WAGA + len(lista_algorytmow_waga)):
            for komorka in wiersz_komorki:
                komorka.border = OBRAMOWANIE_CIENKIE

        wiersz_korelacja = WIERSZ_NAGLOWKA_WAGA + len(lista_algorytmow_waga) + 2
        ws_waga.cell(row=wiersz_korelacja, column=1, value='Korelacja rang Spearmana vs nominalna:').font = FONT_POGRUBIONY
        kolumna = 4
        for kol in kolumny_scenariuszy_kary:
            r = ranga_nominalna.corr(korelacje_spearman[kol], method='spearman')
            ws_waga.cell(row=wiersz_korelacja, column=kolumna,
                          value=round(r, 3) if pd.notna(r) else None).font = FONT_POGRUBIONY
            kolumna += 2
        ws_waga.cell(row=wiersz_korelacja + 1, column=1, value=(
            'Blisko 1.0 = ranking praktycznie niezależny od doboru tej wagi (odporny). '
            'Znacząco poniżej 1.0 = ranking wrażliwy na tę konkretną wagę.'
        )).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')

        autoszerokosc(ws_waga)

    # ==========================================================================
    # ZAKŁADKA "Podsumowanie_lokalizacje"
    # ==========================================================================
    ws_lok = wb.create_sheet('Podsumowanie_lokalizacje')

    # Wiersz 1: opisowa notka (rozpięta nad tabelą) - nagłówki w wierszu 2 muszą
    # zawierać SUROWE nazwy algorytmów (identyczne jak w Dane!Algorytm), bo służą
    # jako kryterium w AVERAGEIFS poniżej - stąd nie mogą być "ozdobione" opisem.
    ws_lok.cell(row=1, column=1, value='Średnia energia (kWh) per algorytm, uśredniona po latach dla każdej lokalizacji.')
    ws_lok.cell(row=1, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')
    ws_lok.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(lista_algorytmow) + 3)

    WIERSZ_NAGLOWKA_LOK = 2
    naglowki_lok = ['Lokalizacja'] + lista_algorytmow + ['Najlepszy algorytm', 'Oszczędność vs. bazowy (%)']
    ustaw_naglowek(ws_lok, WIERSZ_NAGLOWKA_LOK, naglowki_lok)

    lokalizacje_unikalne = sorted(df['Lokalizacja'].unique())
    kolumna_bazowa_litera = get_column_letter(2 + lista_algorytmow.index(ALGORYTM_BAZOWY))
    pierwsza_kol_alg = get_column_letter(2)
    ostatnia_kol_alg = get_column_letter(1 + len(lista_algorytmow))
    wiersz_naglowka = WIERSZ_NAGLOWKA_LOK

    for i, miasto in enumerate(lokalizacje_unikalne, start=WIERSZ_NAGLOWKA_LOK + 1):
        ws_lok.cell(row=i, column=1, value=miasto).font = FONT_POGRUBIONY
        for j, algorytm in enumerate(lista_algorytmow, start=2):
            litera = get_column_letter(j)
            komorka = ws_lok.cell(row=i, column=j, value=(
                f'=AVERAGEIFS(Dane!$E$2:$E${ostatni_wiersz_dane}, '
                f'Dane!$A$2:$A${ostatni_wiersz_dane}, $A{i}, '
                f'Dane!$D$2:$D${ostatni_wiersz_dane}, {litera}${wiersz_naglowka})'
            ))
            komorka.font = FONT_ZWYKLY
            komorka.number_format = '0.00'
            komorka.border = OBRAMOWANIE_CIENKIE

        kol_najlepszy = len(lista_algorytmow) + 2
        kol_oszczednosc = kol_najlepszy + 1

        komorka_najlepszy = ws_lok.cell(row=i, column=kol_najlepszy, value=(
            f'=INDEX($B${wiersz_naglowka}:${ostatnia_kol_alg}${wiersz_naglowka}, '
            f'MATCH(MIN({pierwsza_kol_alg}{i}:{ostatnia_kol_alg}{i}), '
            f'{pierwsza_kol_alg}{i}:{ostatnia_kol_alg}{i}, 0))'
        ))
        komorka_najlepszy.font = FONT_POGRUBIONY
        komorka_najlepszy.border = OBRAMOWANIE_CIENKIE

        komorka_oszczednosc = ws_lok.cell(row=i, column=kol_oszczednosc, value=(
            f'=({kolumna_bazowa_litera}{i}-MIN({pierwsza_kol_alg}{i}:{ostatnia_kol_alg}{i}))/{kolumna_bazowa_litera}{i}'
        ))
        komorka_oszczednosc.font = FONT_ZWYKLY
        komorka_oszczednosc.number_format = '0.0%'
        komorka_oszczednosc.border = OBRAMOWANIE_CIENKIE

    ostatni_wiersz_lok = len(lokalizacje_unikalne) + WIERSZ_NAGLOWKA_LOK
    for j in range(2, 2 + len(lista_algorytmow)):
        litera = get_column_letter(j)
        skala = ColorScaleRule(start_type='min', start_color='63BE7B',
                                end_type='max', end_color='F8696B')
        ws_lok.conditional_formatting.add(f'{litera}{WIERSZ_NAGLOWKA_LOK + 1}:{litera}{ostatni_wiersz_lok}', skala)

    ws_lok.freeze_panes = f'B{WIERSZ_NAGLOWKA_LOK + 1}'
    autoszerokosc(ws_lok)

    # ==========================================================================
    # ZAKŁADKA "Opisy_algorytmow" - krótka ściąga: co jest czym (PID/fuzzy logic/
    # histereza), na czym oparty jest cel grzania i czy kontroler jest adaptacyjny
    # (autotest startowy + przestrajanie/cyfrowy bliźniak na żywo) - wprost z
    # Algorytmy/rejestr_algorytmow.py, więc nie może się rozjechać z kodem.
    # ==========================================================================
    ws_opis = wb.create_sheet('Opisy_algorytmow')
    naglowki_opis = ['Algorytm', 'Typ regulatora', 'Cel (setpoint)', 'Adaptacyjny (autotest)', 'Opis']
    ustaw_naglowek(ws_opis, 1, naglowki_opis)

    for i, klucz in enumerate(NAZWY_ALGORYTMOW, start=2):
        wpis = ALGORYTMY.get(klucz, {})
        wartosci = [
            NAZWY_ALGORYTMOW[klucz],
            wpis.get('typ', ''),
            wpis.get('cel', ''),
            'Tak' if wpis.get('adaptacyjny') else 'Nie',
            wpis.get('opis', ''),
        ]
        for j, wartosc in enumerate(wartosci, start=1):
            komorka = ws_opis.cell(row=i, column=j, value=wartosc)
            komorka.font = FONT_POGRUBIONY if j == 1 else FONT_ZWYKLY
            komorka.border = OBRAMOWANIE_CIENKIE
            komorka.alignment = Alignment(vertical='center', wrap_text=(j == 5))
            if j == 4:
                komorka.alignment = WYROWNANIE_SRODEK

    ostatni_wiersz_opis = len(NAZWY_ALGORYTMOW) + 1
    fill_adaptacyjny = PatternFill('solid', fgColor='D9EAD3')
    ws_opis.conditional_formatting.add(
        f'A2:E{ostatni_wiersz_opis}',
        FormulaRule(formula=['$D2="Tak"'], fill=fill_adaptacyjny),
    )
    ws_opis.freeze_panes = 'A2'
    autoszerokosc(ws_opis, max_szer=45)
    ws_opis.column_dimensions['E'].width = 80  # opis jest długi - autoszerokosc przycięłaby go do max_szer

    # ==========================================================================
    # ZAKŁADKA "Zlozonosc_obliczeniowa" - szacunkowa złożoność czasowa/pamięciowa
    # i FLOPs/krok każdego algorytmu, wprost z Algorytmy/rejestr_algorytmow.py
    # (patrz komentarz przy tych polach tam - wyliczone analizą kodu, NIE
    # zmierzone profilerem, traktuj jako rząd wielkości).
    # ==========================================================================
    ws_zloz = wb.create_sheet('Zlozonosc_obliczeniowa')
    ws_zloz.cell(row=1, column=1, value=(
        'FLOPs/krok dotyczy WYŁĄCZNIE logiki decyzyjnej algorytmu (bez współdzielonej fizyki obiektu/śniegu, '
        'identycznej dla wszystkich) - rzędu dziesiątek/setek FLOPs, więc realny czas symulacji wynika z narzutu '
        'interpretera Pythona/pandas na krok, NIE z limitu przepustowości FLOPs procesora.'
    ))
    ws_zloz.cell(row=1, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')
    ws_zloz.merge_cells(start_row=1, start_column=1, end_row=1, end_column=9)
    ws_zloz.cell(row=2, column=1, value=(
        'Kolumny "zmierzone" pochodzą z rzeczywistego licznika operacji w kodzie (rdzen_kontrolera.'
        'KontrolerBazowy._dodaj_flopy - patrz kolumna "FLOPs (zmierzone)" w zakładce Dane), uśrednione '
        'po wszystkich przebiegach danego algorytmu w tym przeglądzie - to NIE jest to samo co "Łączne FLOPs" '
        '(które ekstrapoluje stały szacunek/krok na medianę długości okna).'
    ))
    ws_zloz.cell(row=2, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')
    ws_zloz.merge_cells(start_row=2, start_column=1, end_row=2, end_column=9)

    WIERSZ_NAGLOWKA_ZLOZ = 3
    naglowki_zloz = ['Algorytm', 'Złożoność czasowa (na krok)', 'FLOPs/krok (przybliżone)',
                      'Złożoność pamięciowa', 'Pamięć - stan ustalony (MB)',
                      'Kroki w oknie testowym', 'Łączne FLOPs (szacunek x kroki)',
                      'Śr. FLOPs/krok (zmierzone)', 'Śr. łączne FLOPs (zmierzone)']
    ustaw_naglowek(ws_zloz, WIERSZ_NAGLOWKA_ZLOZ, naglowki_zloz)

    # "Kroki w oknie testowym" i "Łączne FLOPs (szacunek x kroki)" liczone z rzeczywistej
    # mediany liczby dni w danych (kolumna 'dni' w Dane, jeśli obecna) x 86400 s/dobę -
    # to ekstrapolacja stałego szacunku/krok, NIE FLOPs całej symulacji (fizyka obiektu/
    # śniegu pominięta, patrz wyżej). Kolumny "zmierzone" obok to NIEZALEŻNA, rzeczywista
    # miara z liczników w kodzie - średnia po wszystkich przebiegach danego algorytmu.
    mediana_dni = df['dni'].median() if 'dni' in df.columns else None
    kroki_okna = int(round(mediana_dni * 86400)) if mediana_dni is not None else None

    sr_flopy_zmierzone = (df.groupby('name')['flops_rzeczywiste'].mean()
                          if 'flops_rzeczywiste' in df.columns else None)
    sr_dni_per_alg = df.groupby('name')['dni'].mean() if 'dni' in df.columns else None

    for i, klucz in enumerate(NAZWY_ALGORYTMOW, start=WIERSZ_NAGLOWKA_ZLOZ + 1):
        wpis = ALGORYTMY.get(klucz, {})
        flops_krok = wpis.get('flops_na_krok')
        laczne_flops = flops_krok * kroki_okna if (flops_krok is not None and kroki_okna is not None) else None
        flops_zmierzone = (sr_flopy_zmierzone.get(klucz) if sr_flopy_zmierzone is not None else None)
        flops_zmierzone_na_krok = None
        if flops_zmierzone is not None and pd.notna(flops_zmierzone) and sr_dni_per_alg is not None:
            dni_alg = sr_dni_per_alg.get(klucz)
            if dni_alg is not None and pd.notna(dni_alg) and dni_alg > 0:
                flops_zmierzone_na_krok = flops_zmierzone / (dni_alg * 86400.0)
        wartosci = [
            NAZWY_ALGORYTMOW[klucz],
            wpis.get('zlozonosc_czasowa', ''),
            flops_krok,
            wpis.get('zlozonosc_pamieciowa', ''),
            wpis.get('pamiec_przyblizona_mb'),
            kroki_okna,
            laczne_flops,
            flops_zmierzone_na_krok,
            flops_zmierzone if (flops_zmierzone is not None and pd.notna(flops_zmierzone)) else None,
        ]
        for j, wartosc in enumerate(wartosci, start=1):
            komorka = ws_zloz.cell(row=i, column=j, value=wartosc)
            komorka.font = FONT_POGRUBIONY if j == 1 else FONT_ZWYKLY
            komorka.border = OBRAMOWANIE_CIENKIE
            komorka.alignment = Alignment(vertical='center', wrap_text=(j in (2, 4)))
            if j in (3, 5, 6, 8):
                komorka.number_format = '0.000' if j == 5 else ('0.0' if j == 8 else '0')
            if j in (7, 9) and wartosc is not None:
                komorka.number_format = '0.00E+00'

    ostatni_wiersz_zloz = len(NAZWY_ALGORYTMOW) + WIERSZ_NAGLOWKA_ZLOZ
    skala_flops = ColorScaleRule(start_type='min', start_color='63BE7B', end_type='max', end_color='F8696B')
    ws_zloz.conditional_formatting.add(f'C{WIERSZ_NAGLOWKA_ZLOZ + 1}:C{ostatni_wiersz_zloz}', skala_flops)
    ws_zloz.conditional_formatting.add(f'H{WIERSZ_NAGLOWKA_ZLOZ + 1}:H{ostatni_wiersz_zloz}', skala_flops)
    ws_zloz.freeze_panes = f'A{WIERSZ_NAGLOWKA_ZLOZ + 1}'
    ws_zloz.column_dimensions['B'].width = 55
    autoszerokosc(ws_zloz, max_szer=40)
    ws_zloz.column_dimensions['B'].width = 55  # opis złożoności jest długi - autoszerokosc przycięłaby go

    # ==========================================================================
    # ZAKŁADKA "Uczenie_adaptacyjne" - krzywa uczenia rodziny nauka_kary_* -
    # WCZYTYWANA Z OSOBNYCH PLIKÓW <lokalizacja>_<algorytm>_uczenie.csv (jedna
    # aktualizacja _czynnik_nauczony na dobę - patrz
    # funkcja_nauka_kary_wspolna.py/test_wszystkie_rownolegle.py), NIE z
    # PRZEGLAD_ZBIORCZY.csv (który ma jedną wartość na cały przebieg, nie
    # pokazuje ZMIANY w czasie). Pomijana bez błędu, jeśli żadne takie pliki
    # nie istnieją (np. przegląd nie obejmował algorytmów nauka_kary_*).
    # ==========================================================================
    _wszystkie_pliki_uczenia = sorted(glob.glob(os.path.join(FOLDER_WYNIKOW, '*_uczenie.csv')))
    # Tylko rodzina nauka_kary_* (schemat: czynnik_nauczony + 3 liczniki kar) - patrz
    # osobny blok niżej dla risk_function_pid_auto (schemat: koszt + strojone progi,
    # NIEKOMPATYBILNY z kolumnami poniżej - własna zakładka "Strojenie_progow_ryzyka").
    pliki_uczenia = [p for p in _wszystkie_pliki_uczenia
                      if any(os.path.basename(p).endswith(f'_{k}_uczenie.csv') for k in KLUCZE_UCZENIA_KARY)]
    if pliki_uczenia:
        ramki_uczenia = []
        for plik in pliki_uczenia:
            ramka = pd.read_csv(plik)
            ramka['timestamp'] = pd.to_datetime(ramka['timestamp'])
            ramki_uczenia.append(ramka)
        df_uczenie_wszystko = pd.concat(ramki_uczenia, ignore_index=True)
        df_uczenie_wszystko['Algorytm'] = df_uczenie_wszystko['algorytm'].map(NAZWY_ALGORYTMOW)
        df_uczenie_wszystko.sort_values(['lokalizacja', 'algorytm', 'timestamp'], inplace=True)
        df_uczenie_wszystko['nr_aktualizacji'] = df_uczenie_wszystko.groupby(
            ['lokalizacja', 'algorytm']).cumcount() + 1

        ws_ucz = wb.create_sheet('Uczenie_adaptacyjne')
        ws_ucz.cell(row=1, column=1, value=(
            'Jeden wiersz = JEDNA aktualizacja czynnika uczonego (domyślnie raz na dobę symulowanego czasu) - '
            'pokazuje jak _czynnik_nauczony (i kary, które go napędzają) zmienia się W CZASIE trwania symulacji, '
            'w miarę jak algorytm "uczy się" zachowania szyny w danej lokalizacji.'
        ))
        ws_ucz.cell(row=1, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')
        ws_ucz.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)

        WIERSZ_NAGLOWKA_UCZ = 2
        naglowki_ucz = ['Lokalizacja', 'Algorytm', 'Nr aktualizacji', 'Data', 'Czynnik nauczony (°C)',
                        'Kara: przegrzanie', 'Kara: śnieg', 'Kara: lód']
        ustaw_naglowek(ws_ucz, WIERSZ_NAGLOWKA_UCZ, naglowki_ucz)

        for i, wiersz in enumerate(df_uczenie_wszystko.itertuples(index=False), start=WIERSZ_NAGLOWKA_UCZ + 1):
            wartosci = [wiersz.lokalizacja, wiersz.Algorytm, int(wiersz.nr_aktualizacji),
                        wiersz.timestamp.strftime('%Y-%m-%d'), round(wiersz.czynnik_nauczony, 3),
                        int(wiersz.kara_przegrzanie), int(wiersz.kara_snieg), int(wiersz.kara_lod)]
            for j, wartosc in enumerate(wartosci, start=1):
                komorka = ws_ucz.cell(row=i, column=j, value=wartosc)
                komorka.font = FONT_ZWYKLY
                komorka.border = OBRAMOWANIE_CIENKIE

        ostatni_wiersz_ucz = len(df_uczenie_wszystko) + WIERSZ_NAGLOWKA_UCZ
        ws_ucz.freeze_panes = f'A{WIERSZ_NAGLOWKA_UCZ + 1}'
        ws_ucz.auto_filter.ref = f'A{WIERSZ_NAGLOWKA_UCZ}:H{ostatni_wiersz_ucz}'
        autoszerokosc(ws_ucz)

        # Wykres krzywej uczenia (jedna linia na algorytm) dla PIERWSZEJ
        # lokalizacji, dla której mamy dane - reprezentatywny podgląd, żeby nie
        # trzeba było przewijać całej (potencjalnie długiej) tabeli, żeby
        # zobaczyć kształt krzywej. Pełne dane dla WSZYSTKICH lokalizacji są w
        # tabeli powyżej.
        pierwsza_lokalizacja = df_uczenie_wszystko['lokalizacja'].iloc[0]
        wiersz_startowy_wykresu = WIERSZ_NAGLOWKA_UCZ + len(df_uczenie_wszystko) + 3
        ws_ucz.cell(row=wiersz_startowy_wykresu - 1, column=1,
                    value=f'Podgląd krzywej uczenia dla lokalizacji: {pierwsza_lokalizacja}').font = FONT_POGRUBIONY

        chart = LineChart()
        chart.title = f'Krzywa uczenia (czynnik_nauczony) - {pierwsza_lokalizacja}'
        chart.x_axis.title = 'Nr aktualizacji (dni)'
        chart.y_axis.title = 'Czynnik nauczony (°C)'
        chart.width = 24
        chart.height = 12

        kolumna_pomocnicza = wiersz_startowy_wykresu
        for algorytm_klucz in KLUCZE_UCZENIA_KARY:
            podzbior = df_uczenie_wszystko[
                (df_uczenie_wszystko['lokalizacja'] == pierwsza_lokalizacja)
                & (df_uczenie_wszystko['algorytm'] == algorytm_klucz)
            ]
            if podzbior.empty:
                continue
            nazwa_kol = NAZWY_ALGORYTMOW.get(algorytm_klucz, algorytm_klucz)
            ws_ucz.cell(row=kolumna_pomocnicza, column=10, value=nazwa_kol).font = FONT_POGRUBIONY
            for k, wartosc in enumerate(podzbior['czynnik_nauczony'].tolist(), start=1):
                ws_ucz.cell(row=kolumna_pomocnicza + k, column=10, value=round(float(wartosc), 3))
            dane_serii = Reference(ws_ucz, min_col=10, min_row=kolumna_pomocnicza,
                                    max_row=kolumna_pomocnicza + len(podzbior))
            chart.add_data(dane_serii, titles_from_data=True)
            kolumna_pomocnicza += len(podzbior) + 2

        if chart.series:
            ws_ucz.add_chart(chart, f'A{wiersz_startowy_wykresu}')

    # ==========================================================================
    # ZAKŁADKA "Strojenie_progow_ryzyka" - krzywa AUTOMATYCZNEGO STROJENIA
    # (risk_function_pid_auto, patrz funkcja_ryzyka_pid_auto_strojenie.py) -
    # SCHEMAT INNY niż "Uczenie_adaptacyjne" wyżej (koszt + 4 strojone progi,
    # nie czynnik_nauczony + 3 kary), stąd osobna zakładka zamiast mieszania
    # w jednej tabeli. Pomijana bez błędu, jeśli algorytm nie był w przeglądzie.
    # ==========================================================================
    pliki_strojenia = [p for p in _wszystkie_pliki_uczenia
                        if os.path.basename(p).endswith('_risk_function_pid_auto_uczenie.csv')]
    if pliki_strojenia:
        ramki_strojenia = []
        for plik in pliki_strojenia:
            ramka = pd.read_csv(plik)
            ramka['timestamp'] = pd.to_datetime(ramka['timestamp'])
            ramki_strojenia.append(ramka)
        df_strojenie = pd.concat(ramki_strojenia, ignore_index=True)
        df_strojenie.sort_values(['lokalizacja', 'timestamp'], inplace=True)
        df_strojenie['nr_aktualizacji'] = df_strojenie.groupby('lokalizacja').cumcount() + 1

        ws_str = wb.create_sheet('Strojenie_progow_ryzyka')
        ws_str.cell(row=1, column=1, value=(
            'Jeden wiersz = JEDNA aktualizacja progów risk_function_pid_auto (domyślnie raz na 7 dni '
            'symulowanego czasu, "perturb-and-observe" - patrz notatki/propozycja_auto_strojenie.md). '
            '"Koszt" = całka mocy (%·h) + kara za przekroczone progi śniegu/lodu/przegrzania (h x waga) - '
            'gdy koszt ROŚNIE względem poprzedniego okresu, kierunek zmiany KAŻDEGO progu się odwraca.'
        ))
        ws_str.cell(row=1, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')
        ws_str.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)

        WIERSZ_NAGLOWKA_STR = 2
        naglowki_str = ['Lokalizacja', 'Nr aktualizacji', 'Data', 'Koszt', 'Moc-całka (%·h)', 'Kary (h)',
                         'hrt_on_precip', 'at_low_freeze', 'hrt_on_dry', 'risk_snow_penalty_per_mm_c']
        ustaw_naglowek(ws_str, WIERSZ_NAGLOWKA_STR, naglowki_str)

        for i, wiersz in enumerate(df_strojenie.itertuples(index=False), start=WIERSZ_NAGLOWKA_STR + 1):
            wartosci = [wiersz.lokalizacja, int(wiersz.nr_aktualizacji), wiersz.timestamp.strftime('%Y-%m-%d'),
                        round(wiersz.koszt, 2), round(wiersz.moc_calka_pct_h, 2), round(wiersz.kary_h, 3),
                        round(wiersz.hrt_on_precip, 3), round(wiersz.at_low_freeze, 3),
                        round(wiersz.hrt_on_dry, 3), round(wiersz.risk_snow_penalty_per_mm_c, 4)]
            for j, wartosc in enumerate(wartosci, start=1):
                komorka = ws_str.cell(row=i, column=j, value=wartosc)
                komorka.font = FONT_ZWYKLY
                komorka.border = OBRAMOWANIE_CIENKIE

        ostatni_wiersz_str = len(df_strojenie) + WIERSZ_NAGLOWKA_STR
        ws_str.freeze_panes = f'A{WIERSZ_NAGLOWKA_STR + 1}'
        ws_str.auto_filter.ref = f'A{WIERSZ_NAGLOWKA_STR}:J{ostatni_wiersz_str}'
        autoszerokosc(ws_str)

        pierwsza_lokalizacja_str = df_strojenie['lokalizacja'].iloc[0]
        podzbior_str = df_strojenie[df_strojenie['lokalizacja'] == pierwsza_lokalizacja_str]
        wiersz_wykresu_str = ostatni_wiersz_str + 3
        ws_str.cell(row=wiersz_wykresu_str - 1, column=1,
                    value=f'Podgląd krzywej kosztu strojenia - {pierwsza_lokalizacja_str}').font = FONT_POGRUBIONY
        ws_str.cell(row=wiersz_wykresu_str, column=12, value='Koszt').font = FONT_POGRUBIONY
        for k, wartosc in enumerate(podzbior_str['koszt'].tolist(), start=1):
            ws_str.cell(row=wiersz_wykresu_str + k, column=12, value=round(float(wartosc), 2))

        chart_str = LineChart()
        chart_str.title = f'Krzywa kosztu auto-strojenia - {pierwsza_lokalizacja_str}'
        chart_str.x_axis.title = 'Nr aktualizacji (x 7 dni)'
        chart_str.y_axis.title = 'Koszt (%·h-ekwiwalent)'
        chart_str.width = 24
        chart_str.height = 12
        dane_serii_str = Reference(ws_str, min_col=12, min_row=wiersz_wykresu_str,
                                    max_row=wiersz_wykresu_str + len(podzbior_str))
        chart_str.add_data(dane_serii_str, titles_from_data=True)
        if chart_str.series:
            ws_str.add_chart(chart_str, f'A{wiersz_wykresu_str}')

    # ==========================================================================
    # ZAKŁADKA "Wnioski" - tekst z realnie policzonymi liczbami (nie formuły)
    # ==========================================================================
    ws_wn = wb.create_sheet('Wnioski')
    ws_wn.column_dimensions['A'].width = 115

    agregaty = df.groupby('Algorytm').agg(
        energia_srednia=('energia_kwh', 'mean'),
        przelaczenia_srednie=('przelaczenia', 'mean'),
        max_hrt_srednie=('max_hrt', 'mean'),
        max_snieg_srednie=('max_snieg_mm', 'mean'),
    ).reindex(lista_algorytmow)

    anomalie = df[df['max_hrt'] > 35.0].copy()
    anomalie_per_algorytm = anomalie['Algorytm'].value_counts().reindex(lista_algorytmow, fill_value=0)

    zwyciezca_energia = agregaty['energia_srednia'].idxmin()
    zwyciezca_przelaczenia = agregaty['przelaczenia_srednie'].idxmin()
    energia_bazowa = agregaty.loc[ALGORYTM_BAZOWY, 'energia_srednia']
    energia_najlepsza = agregaty.loc[zwyciezca_energia, 'energia_srednia']
    oszczednosc_pct = (energia_bazowa - energia_najlepsza) / energia_bazowa * 100.0

    linie = []
    linie.append('PODSUMOWANIE PRZEGLĄDU - WSZYSTKIE ALGORYTMY, WSZYSTKIE LOKALIZACJE')
    linie.append(f'(dane: {len(df)} wierszy, {df["Lokalizacja"].nunique()} lokalizacji, '
                 f'okno {int(round(df["dni"].median())) if "dni" in df.columns else "?"} dni na lokalizację)')
    linie.append('')
    linie.append('1) ENERGIA')
    linie.append(f'   Najniższą średnią energię ({energia_najlepsza:.1f} kWh) osiągnął algorytm '
                 f'"{zwyciezca_energia}" - to {oszczednosc_pct:.1f}% mniej niż algorytm bazowy '
                 f'"{ALGORYTM_BAZOWY}" ({energia_bazowa:.1f} kWh).')
    for alg in lista_algorytmow:
        linie.append(f'   - {alg}: średnio {agregaty.loc[alg, "energia_srednia"]:.1f} kWh')
    linie.append('')
    linie.append('2) STABILNOŚĆ (LICZBA PRZEŁĄCZEŃ)')
    linie.append(f'   Zdecydowanym zwycięzcą jest "{zwyciezca_przelaczenia}" ze średnio '
                 f'{agregaty.loc[zwyciezca_przelaczenia, "przelaczenia_srednie"]:.1f} przełączeń '
                 f'na lokalizację - {agregaty["przelaczenia_srednie"].max()/agregaty.loc[zwyciezca_przelaczenia, "przelaczenia_srednie"]:.1f}x '
                 f'mniej niż najgorszy pod tym względem wariant '
                 f'({agregaty["przelaczenia_srednie"].idxmax()}, {agregaty["przelaczenia_srednie"].max():.1f}). '
                 f'To spodziewane - reguluje mocą w sposób ciągły zamiast dyskretnie włączać/wyłączać grzanie.')
    linie.append('')
    linie.append('3) ANOMALIE (Max HRT > 35°C - podejrzenie przegrzania)')
    linie.append(f'   Łącznie {len(anomalie)} przypadków na {len(df)} wierszy danych:')
    for alg in lista_algorytmow:
        linie.append(f'   - {alg}: {int(anomalie_per_algorytm[alg])} przypadków')
    linie.append('   HIPOTEZA: wszystkie anomalie występują WYŁĄCZNIE w trzech algorytmach z dyskretnym')
    linie.append('   limitem przełączeń (12/dobę) - zero przypadków w wersji PID, która tego limitu nie')
    linie.append('   używa (reguluje mocą ciągle, 0-100%). Prawdopodobny mechanizm: przy oscylacjach')
    linie.append('   warunków blisko progu załączenia/wyłączenia dobowy budżet przełączeń wyczerpuje się')
    linie.append('   wcześnie, a grzanie "zawiesza się" w stanie włączonym do północy (reset licznika) -')
    linie.append('   przy długim, głębokim mrozie HRT zdąża wtedy dryfować w stronę stanu ustalonego')
    linie.append('   (CRT + ok. 51°C przy 100% mocy), stąd skoki do 37-48°C. To NIE jest błąd wyznaczania')
    linie.append('   temperatury zadanej, tylko efekt uboczny bezpiecznika ograniczającego zużycie styku -')
    linie.append('   przykłady: ' + ', '.join(
        f'{r.Lokalizacja} {r.Rok} ({r.Algorytm}, HRT={r.max_hrt:.1f}°C)'
        for r in anomalie.sort_values('max_hrt', ascending=False).head(4).itertuples()
    ) + '.')
    linie.append('')
    linie.append('4) REKOMENDACJA PRAKTYCZNA')
    linie.append('   Funkcja ryzyka w wersji PID (risk_function_pid) jest jedynym z czterech wariantów,')
    linie.append('   który NIE wygenerował ani jednego przypadku przegrzania powyżej 35°C, przy')
    linie.append(f'   jednoczesnym {agregaty["przelaczenia_srednie"].max()/agregaty.loc["Funkcja ryzyka (PID)", "przelaczenia_srednie"]:.1f}x mniejszym zużyciu styku przełączającego niż pozostałe warianty.')
    linie.append(f'   Pod względem samej energii przegrywa nieznacznie z wersją binarną funkcji ryzyka')
    linie.append(f'   ({agregaty.loc["Funkcja ryzyka (PID)","energia_srednia"]:.1f} kWh vs '
                 f'{agregaty.loc["Funkcja ryzyka (binarna)","energia_srednia"]:.1f} kWh średnio), ale biorąc pod')
    linie.append('   uwagę brak anomalii i dużo mniejsze zużycie mechaniczne przekaźnika, to ona jest')
    linie.append('   rekomendowanym wyborem do dalszego rozwoju/wdrożenia.')

    if 'kara_bezpieczenstwa' in df.columns:
        linie.append('')
        linie.append('5) NARUSZENIA BEZPIECZEŃSTWA (patrz notatki/kara_bezpieczenstwa.md)')
        naruszenia = df[df['kara_bezpieczenstwa'] > 0].copy()
        agregaty_kara = df.groupby('Algorytm').agg(
            kara_suma=('kara_bezpieczenstwa', 'sum'),
            epizody_suma=('epizody_ponizej_floor', 'sum'),
            min_hrt_globalnie=('min_hrt', 'min'),
        ).reindex(lista_algorytmow)
        linie.append(f'   Łącznie {len(naruszenia)} z {len(df)} wierszy danych ma niezerową karę '
                     f'bezpieczeństwa (zalegający śnieg powyżej bezpiecznego progu / marznący deszcz przy '
                     f'HRT wciąż < 2°C / HRT poniżej bezwzględnego floora -10°C):')
        for alg in lista_algorytmow:
            kara_s = agregaty_kara.loc[alg, 'kara_suma']
            epizody_s = agregaty_kara.loc[alg, 'epizody_suma']
            min_hrt_g = agregaty_kara.loc[alg, 'min_hrt_globalnie']
            if pd.notna(kara_s) and pd.notna(min_hrt_g):
                linie.append(f'   - {alg}: suma kary {kara_s:.0f} °C·s, '
                             f'{int(epizody_s) if pd.notna(epizody_s) else 0} epizodów HRT<-10°C, '
                             f'najzimniejszy zaobserwowany HRT={min_hrt_g:.1f}°C')
            else:
                linie.append(f'   - {alg}: brak danych')
        if not naruszenia.empty:
            linie.append('   Najgorsze pojedyncze przypadki (najwyższa kara bezpieczeństwa w danym przebiegu):')
            for r in naruszenia.sort_values('kara_bezpieczenstwa', ascending=False).head(5).itertuples():
                linie.append(f'   - {r.Lokalizacja} {r.Rok} ({r.Algorytm}): kara={r.kara_bezpieczenstwa:.0f} °C·s, '
                             f'min HRT={r.min_hrt:.1f}°C, epizodów HRT<-10°C={int(r.epizody_ponizej_floor)}')

    for i, linia in enumerate(linie, start=1):
        komorka = ws_wn.cell(row=i, column=1, value=linia)
        komorka.font = FONT_POGRUBIONY if (linia.isupper() or re.match(r'^\d\)', linia)) else FONT_ZWYKLY
        komorka.alignment = Alignment(wrap_text=True, vertical='top')

    wb.save(SCIEZKA_XLSX)
    print(f'Zapisano: {SCIEZKA_XLSX}')
    return df, agregaty, anomalie


if __name__ == '__main__':
    main()
