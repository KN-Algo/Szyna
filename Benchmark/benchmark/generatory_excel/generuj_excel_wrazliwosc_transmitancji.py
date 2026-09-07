# generuj_excel_wrazliwosc_transmitancji.py
#
# Konsoliduje 8 osobnych plików Podsumowanie_wynikow.xlsx (nominal + 7 scenariuszy
# perturbacji K/T1 - wyniki test_wszystkie_rownolegle.py uruchomionego 8x z różnymi
# SZYNA_PERTURB_K_PCT/SZYNA_PERTURB_T1_PCT) w JEDEN plik Excela, żeby nie trzeba było
# otwierać 8 osobnych plików po kolei, żeby porównać wpływ zaburzenia transmitancji.
#
# Źródło: wyniki/wyniki_excela/<scenariusz>/Podsumowanie_wynikow.xlsx (zakładka "Dane" -
# literalne wartości, nie formuły, patrz notatki/wyniki_excel/README.md) - czyli pliki
# już wyekstrahowane z zipów przesłanych przez użytkownika z klastra. Jeśli w przyszłości
# doda się nowy scenariusz/nowy plik, wystarczy dopisać go do SCENARIUSZE niżej.
#
# Uruchomienie (z katalogu Benchmark/benchmark): python generatory_excel/generuj_excel_wrazliwosc_transmitancji.py

import os
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmark/ (rodzic generatory_excel/)
FOLDER_EXCELA = os.path.join(BASE_DIR, "wyniki", "wyniki_excela")
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
