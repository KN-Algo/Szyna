# generuj_excel_wrazliwosc_transmitancji.py
#
# Konsoliduje 8 osobnych plików Podsumowanie_wynikow.xlsx (nominal + 7 scenariuszy
# perturbacji K/T1 - wyniki test_wszystkie_rownolegle.py uruchomionego 8x z różnymi
# SZYNA_PERTURB_K_PCT/SZYNA_PERTURB_T1_PCT) w JEDEN plik Excela, żeby nie trzeba było
# otwierać 8 osobnych plików po kolei, żeby porównać wpływ zaburzenia transmitancji.
#
# Źródło: wyniki/wrazliwosc_transmitancji/<scenariusz>/Podsumowanie_wynikow.xlsx
# (zakładka "Dane" - literalne wartości, nie formuły, patrz notatki/wyniki_excel/
# README.md) - DOKŁADNIE ta ścieżka, do której slurm_wrazliwosc_transmitancji.sh
# zapisuje wyniki KAŻDEGO z 8 elementów tablicy (SZYNA_FOLDER_WYNIKOW="wyniki/
# wrazliwosc_transmitancji/$SZYNA_SCENARIUSZ"). Jeśli w przyszłości doda się nowy
# scenariusz/nowy plik, wystarczy dopisać go do SCENARIUSZE niżej.
#
# Uruchomienie (z katalogu Benchmark/benchmark): python generatory_excel/generuj_excel_wrazliwosc_transmitancji.py

import os
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmark/ (rodzic generatory_excel/)
FOLDER_EXCELA = os.path.join(BASE_DIR, "wyniki", "wrazliwosc_transmitancji")
SCIEZKA_WYJSCIOWA = os.path.join(FOLDER_EXCELA, "Podsumowanie_wrazliwosc_transmitancji_WSZYSTKIE.xlsx")

# (folder, etykieta, perturbacja_K_pct, perturbacja_T1_pct) - kolejność wyświetlania.
SCENARIUSZE = [
    ("nominal", "nominal (0%)", 0.0, 0.0),
    ("K_plus5", "K +5%", 5.0, 0.0),
    ("K_plus10", "K +10%", 10.0, 0.0),
    ("K_plus15", "K +15%", 15.0, 0.0),
    ("T1_plus5", "T1 +5%", 0.0, 5.0),
    ("T1_plus10", "T1 +10%", 0.0, 10.0),
    ("T1_plus15", "T1 +15%", 0.0, 15.0),
    ("K10_T1_10", "K +10% i T1 +10% (łącznie)", 10.0, 10.0),
]

FONT_NAZWA = 'Arial'
FONT_NAGLOWEK = Font(name=FONT_NAZWA, bold=True, color='FFFFFF', size=11)
FILL_NAGLOWEK = PatternFill('solid', fgColor='1F4E78')
FONT_ZWYKLY = Font(name=FONT_NAZWA, size=10)
FONT_POGRUBIONY = Font(name=FONT_NAZWA, bold=True, size=10)
WYROWNANIE_SRODEK = Alignment(horizontal='center', vertical='center')
OBRAMOWANIE_CIENKIE = Border(*(Side(style='thin', color='B7B7B7') for _ in range(4)))


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


def wczytaj_wszystkie_scenariusze():
    ramki = []
    brakujace = []
    for folder, etykieta, perturb_k, perturb_t1 in SCENARIUSZE:
        sciezka = os.path.join(FOLDER_EXCELA, folder, "Podsumowanie_wynikow.xlsx")
        if not os.path.exists(sciezka):
            brakujace.append(folder)
            continue
        df = pd.read_excel(sciezka, sheet_name='Dane', engine='openpyxl')
        df.insert(0, 'Scenariusz', etykieta)
        df.insert(1, 'Perturbacja_K_pct', perturb_k)
        df.insert(2, 'Perturbacja_T1_pct', perturb_t1)
        ramki.append(df)
    if not ramki:
        raise FileNotFoundError(
            f"Nie znaleziono żadnego z 8 plików scenariuszy w {FOLDER_EXCELA}/<scenariusz>/Podsumowanie_wynikow.xlsx")
    if brakujace:
        print(f"UWAGA: brakuje {len(brakujace)}/8 scenariuszy (pominięte): {', '.join(brakujace)}")
    return pd.concat(ramki, ignore_index=True)


def main():
    df = wczytaj_wszystkie_scenariusze()

    wb = Workbook()

    # ================= "Dane_wszystkie" - wszystkie wiersze, wszystkie scenariusze =================
    ws = wb.active
    ws.title = 'Dane_wszystkie'
    ustaw_naglowek(ws, 1, list(df.columns))
    for i, wiersz in enumerate(df.itertuples(index=False), start=2):
        for j, wartosc in enumerate(wiersz, start=1):
            if isinstance(wartosc, float) and pd.notna(wartosc):
                wartosc = round(wartosc, 3)
            elif isinstance(wartosc, float) and pd.isna(wartosc):
                wartosc = None
            komorka = ws.cell(row=i, column=j, value=wartosc)
            komorka.font = FONT_ZWYKLY
            komorka.border = OBRAMOWANIE_CIENKIE
    ostatni_wiersz = len(df) + 1
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f'A1:{get_column_letter(len(df.columns))}{ostatni_wiersz}'
    autoszerokosc(ws)

    # ================= "Podsumowanie_scenariusze" - macierz algorytm x scenariusz =================
    ws2 = wb.create_sheet('Podsumowanie_scenariusze')
    ws2.cell(row=1, column=1, value=(
        'Średnia energia (kWh) per algorytm x scenariusz zaburzenia transmitancji (uśredniona po wszystkich '
        'lokalizacjach/latach). Kolumny "% vs nominal" pokazują względną zmianę wobec scenariusza nominal (0%) '
        'DLA TEGO SAMEGO algorytmu.'
    ))
    ws2.cell(row=1, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')

    piwot_energia = df.pivot_table(index='Algorytm', columns='Scenariusz', values='Energia (kWh)', aggfunc='mean')
    etykiety_scenariuszy = [et for _, et, _, _ in SCENARIUSZE if et in piwot_energia.columns]
    piwot_energia = piwot_energia[etykiety_scenariuszy]

    nominal_etykieta = SCENARIUSZE[0][1]
    WIERSZ_NAGLOWKA_2 = 3
    naglowki_2 = ['Algorytm']
    for et in etykiety_scenariuszy:
        naglowki_2.append(f'{et} (kWh)')
    for et in etykiety_scenariuszy:
        if et == nominal_etykieta:
            continue
        naglowki_2.append(f'{et} (% vs nominal)')
    ustaw_naglowek(ws2, WIERSZ_NAGLOWKA_2, naglowki_2)
    ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(naglowki_2))

    for i, (algorytm, wiersz) in enumerate(piwot_energia.iterrows(), start=WIERSZ_NAGLOWKA_2 + 1):
        ws2.cell(row=i, column=1, value=algorytm).font = FONT_POGRUBIONY
        baza = wiersz.get(nominal_etykieta)
        for j, et in enumerate(etykiety_scenariuszy, start=2):
            wartosc = wiersz.get(et)
            komorka = ws2.cell(row=i, column=j,
                                value=round(float(wartosc), 2) if pd.notna(wartosc) else None)
            komorka.font = FONT_ZWYKLY
            komorka.border = OBRAMOWANIE_CIENKIE
        kol_pct = 2 + len(etykiety_scenariuszy)
        for et in etykiety_scenariuszy:
            if et == nominal_etykieta:
                continue
            wartosc = wiersz.get(et)
            pct = None
            if pd.notna(wartosc) and pd.notna(baza) and baza:
                pct = (float(wartosc) - float(baza)) / float(baza) * 100.0
            komorka = ws2.cell(row=i, column=kol_pct, value=round(pct, 2) if pct is not None else None)
            komorka.font = FONT_ZWYKLY
            komorka.border = OBRAMOWANIE_CIENKIE
            komorka.number_format = '0.00"%"'
            kol_pct += 1

    ostatni_wiersz_2 = WIERSZ_NAGLOWKA_2 + len(piwot_energia)
    kol_start_pct = 2 + len(etykiety_scenariuszy)
    kol_koniec_pct = kol_start_pct + (len(etykiety_scenariuszy) - 1) - 1
    for kol in range(kol_start_pct, kol_koniec_pct + 1):
        litera = get_column_letter(kol)
        skala = ColorScaleRule(start_type='min', start_color='63BE7B', mid_type='num', mid_value=0, mid_color='FFEB84',
                                end_type='max', end_color='F8696B')
        ws2.conditional_formatting.add(f'{litera}{WIERSZ_NAGLOWKA_2 + 1}:{litera}{ostatni_wiersz_2}', skala)

    ws2.freeze_panes = f'B{WIERSZ_NAGLOWKA_2 + 1}'
    autoszerokosc(ws2)

    # ================= "Podsumowanie_algorytmy" - JAK SOBIE PORADZIŁ KAŻDY
    # ALGORYTM W CAŁOŚCI (uśrednione po WSZYSTKICH 8 scenariuszach naraz, nie
    # per scenariusz jak w "Podsumowanie_scenariusze" wyżej) - na życzenie
    # użytkownika (2026-09-07): "na podstawie [transmitancji] porównaj mi w
    # ostatecznym excelu jak sobie poradziły poszczególne algorytmy w
    # całości". Kolumna "Stabilność energii" to WŁAŚCIWY sens testu
    # wrażliwości transmitancji: nie tylko "ile średnio zużywa", ale "jak
    # BARDZO to zużycie się zmienia, gdy prawdziwy obiekt różni się od
    # założeń" - współczynnik zmienności (CV%) średniej energii MIĘDZY 8
    # scenariuszami (niski = odporny na niepewność modelu obiektu, wysoki =
    # wrażliwy). =================
    ws4 = wb.create_sheet('Podsumowanie_algorytmy')
    ws4.cell(row=1, column=1, value=(
        'Jeden wiersz = jeden algorytm, uśredniony po WSZYSTKICH 8 scenariuszach zaburzenia transmitancji '
        '(i po wszystkich lokalizacjach/latach w każdym z nich) - odpowiedź na "jak sobie poradził w całości", '
        'nie tylko w jednym konkretnym scenariuszu. "Stabilność energii (CV%)" = odchylenie standardowe średniej '
        'energii MIĘDZY 8 scenariuszami / średnia tych 8 wartości x100 - niska wartość = zużycie energii tego '
        'algorytmu mało zależy od tego, jaki naprawdę jest obiekt (odporny na niepewność modelu); wysoka = '
        'algorytm silnie reaguje na błąd identyfikacji K/T1. "Ranga" - 1 = najlepszy pod danym kryterium.'
    ))
    ws4.cell(row=1, column=1).font = Font(name=FONT_NAZWA, italic=True, size=9, color='555555')
    ws4.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)

    kolumna_kara = 'Kara bezpieczeństwa (°C·s)' if 'Kara bezpieczeństwa (°C·s)' in df.columns else None
    kolumna_min_hrt = 'Min HRT (°C)' if 'Min HRT (°C)' in df.columns else None

    agregaty_ogolne = df.groupby('Algorytm').agg(
        energia_srednia=('Energia (kWh)', 'mean'),
        przelaczenia_srednie=('Przełączenia', 'mean'),
        **({'kara_srednia': (kolumna_kara, 'mean')} if kolumna_kara else {}),
        **({'min_hrt_najgorszy': (kolumna_min_hrt, 'min')} if kolumna_min_hrt else {}),
    )
    # Stabilność liczona z ŚREDNICH PER SCENARIUSZ (piwot_energia, już policzone
    # wyżej), NIE z surowych wierszy - żeby rozrzut lokalizacji/lat w obrębie
    # JEDNEGO scenariusza (naturalna zmienność pogody) nie mieszał się z
    # rozrzutem MIĘDZY scenariuszami (to, co faktycznie mierzymy tutaj).
    srednia_scenariuszy = piwot_energia.mean(axis=1)
    std_scenariuszy = piwot_energia.std(axis=1)
    cv_pct = (std_scenariuszy / srednia_scenariuszy * 100.0).replace([float('inf'), float('-inf')], None)
    agregaty_ogolne['stabilnosc_cv_pct'] = cv_pct

    agregaty_ogolne['ranga_energia'] = agregaty_ogolne['energia_srednia'].rank(method='min')
    agregaty_ogolne['ranga_stabilnosc'] = agregaty_ogolne['stabilnosc_cv_pct'].rank(method='min')

    WIERSZ_NAGLOWKA_4 = 2
    naglowki_4 = ['Algorytm', 'Energia śr. (kWh)', 'Ranga energia', 'Stabilność energii (CV%)',
                  'Ranga stabilność', 'Przełączenia śr.']
    if kolumna_kara:
        naglowki_4.append('Kara bezp. śr. (°C·s)')
    if kolumna_min_hrt:
        naglowki_4.append('Min HRT najgorszy (°C)')
    ustaw_naglowek(ws4, WIERSZ_NAGLOWKA_4, naglowki_4)

    agregaty_ogolne = agregaty_ogolne.sort_values('energia_srednia')
    for i, (algorytm, wiersz) in enumerate(agregaty_ogolne.iterrows(), start=WIERSZ_NAGLOWKA_4 + 1):
        kolumna = 1
        ws4.cell(row=i, column=kolumna, value=algorytm).font = FONT_POGRUBIONY
        kolumna += 1
        ws4.cell(row=i, column=kolumna, value=round(float(wiersz['energia_srednia']), 2)).font = FONT_ZWYKLY
        kolumna += 1
        ws4.cell(row=i, column=kolumna, value=int(wiersz['ranga_energia'])).font = FONT_ZWYKLY
        kolumna += 1
        cv = wiersz['stabilnosc_cv_pct']
        ws4.cell(row=i, column=kolumna, value=round(float(cv), 2) if pd.notna(cv) else None).font = FONT_ZWYKLY
        kolumna += 1
        ranga_stab = wiersz['ranga_stabilnosc']
        ws4.cell(row=i, column=kolumna, value=int(ranga_stab) if pd.notna(ranga_stab) else None).font = FONT_ZWYKLY
        kolumna += 1
        ws4.cell(row=i, column=kolumna, value=round(float(wiersz['przelaczenia_srednie']), 1)).font = FONT_ZWYKLY
        kolumna += 1
        if kolumna_kara:
            ws4.cell(row=i, column=kolumna, value=round(float(wiersz['kara_srednia']), 1)).font = FONT_ZWYKLY
            kolumna += 1
        if kolumna_min_hrt:
            ws4.cell(row=i, column=kolumna, value=round(float(wiersz['min_hrt_najgorszy']), 2)).font = FONT_ZWYKLY
            kolumna += 1
        for k in range(1, kolumna):
            ws4.cell(row=i, column=k).border = OBRAMOWANIE_CIENKIE

    ostatni_wiersz_4 = WIERSZ_NAGLOWKA_4 + len(agregaty_ogolne)
    for litera in ('B', 'D', 'F') + (('G',) if kolumna_kara else ()):
        skala = ColorScaleRule(start_type='min', start_color='63BE7B',
                                end_type='max', end_color='F8696B')
        ws4.conditional_formatting.add(f'{litera}{WIERSZ_NAGLOWKA_4 + 1}:{litera}{ostatni_wiersz_4}', skala)
    if kolumna_min_hrt:
        litera_hrt = get_column_letter(naglowki_4.index('Min HRT najgorszy (°C)') + 1)
        skala_hrt = ColorScaleRule(start_type='min', start_color='F8696B',
                                    end_type='max', end_color='63BE7B')
        ws4.conditional_formatting.add(f'{litera_hrt}{WIERSZ_NAGLOWKA_4 + 1}:{litera_hrt}{ostatni_wiersz_4}', skala_hrt)

    ws4.freeze_panes = f'B{WIERSZ_NAGLOWKA_4 + 1}'
    autoszerokosc(ws4)

    # ================= "Wnioski" - tekst =================
    ws3 = wb.create_sheet('Wnioski')
    ws3.column_dimensions['A'].width = 115
    linie = []
    linie.append('WRAŻLIWOŚĆ NA ZABURZENIE TRANSMITANCJI (K/T1) - PODSUMOWANIE WSZYSTKICH SCENARIUSZY')
    linie.append(f'({len(df)} wierszy razem, {df["Scenariusz"].nunique()} scenariuszy, '
                 f'{df["Algorytm"].nunique()} algorytmów)')
    linie.append('')

    srednie_wg_scenariusza = df.groupby('Scenariusz')['Energia (kWh)'].mean().reindex(etykiety_scenariuszy)
    baza_globalna = srednie_wg_scenariusza.get(nominal_etykieta)
    linie.append('1) ŚREDNIA ENERGIA WG SCENARIUSZA (uśredniona po wszystkich algorytmach/lokalizacjach)')
    for et in etykiety_scenariuszy:
        wartosc = srednie_wg_scenariusza.get(et)
        if pd.isna(wartosc):
            continue
        if et == nominal_etykieta or not baza_globalna:
            linie.append(f'   - {et}: {wartosc:.1f} kWh')
        else:
            pct = (wartosc - baza_globalna) / baza_globalna * 100.0
            linie.append(f'   - {et}: {wartosc:.1f} kWh ({pct:+.2f}% vs nominal)')
    linie.append('')

    tylko_k = [et for _, et, k, t1 in SCENARIUSZE if k != 0 and t1 == 0]
    tylko_t1 = [et for _, et, k, t1 in SCENARIUSZE if t1 != 0 and k == 0]
    if tylko_k and baza_globalna:
        rozstep_k = max(abs((srednie_wg_scenariusza.get(et) - baza_globalna) / baza_globalna * 100.0)
                         for et in tylko_k if pd.notna(srednie_wg_scenariusza.get(et)))
        linie.append(f'2) K (wzmocnienie grzania) - max. odchylenie energii vs nominal: {rozstep_k:.2f}%')
    if tylko_t1 and baza_globalna:
        rozstep_t1 = max(abs((srednie_wg_scenariusza.get(et) - baza_globalna) / baza_globalna * 100.0)
                          for et in tylko_t1 if pd.notna(srednie_wg_scenariusza.get(et)))
        linie.append(f'   T1 (stała czasowa) - max. odchylenie energii vs nominal: {rozstep_t1:.2f}%')
        if tylko_k and rozstep_k > 0:
            linie.append(f'   -> K ma {rozstep_k / max(rozstep_t1, 1e-9):.0f}x większy wpływ na energię niż T1 '
                         f'w testowanym zakresie zaburzeń.')
    linie.append('')

    linie.append('3) NAJLEPSZY/NAJGORSZY ALGORYTM PER SCENARIUSZ (min. średnia energia)')
    for et in etykiety_scenariuszy:
        podzbior = df[df['Scenariusz'] == et].groupby('Algorytm')['Energia (kWh)'].mean()
        if podzbior.empty:
            continue
        najlepszy = podzbior.idxmin()
        linie.append(f'   - {et}: najlepszy "{najlepszy}" ({podzbior.min():.1f} kWh)')

    for i, linia in enumerate(linie, start=1):
        komorka = ws3.cell(row=i, column=1, value=linia)
        komorka.font = FONT_POGRUBIONY if (linia.isupper() or linia[:2] in ('1)', '2)', '3)')) else FONT_ZWYKLY
        komorka.alignment = Alignment(wrap_text=True, vertical='top')

    wb.save(SCIEZKA_WYJSCIOWA)
    print(f"Zapisano: {SCIEZKA_WYJSCIOWA}")
    return df


if __name__ == '__main__':
    main()
