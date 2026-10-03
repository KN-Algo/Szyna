# Algorytmy/funkcja_fuzzy_ryzyko_2v2_opad_wagi_adaptacyjne.py
#
# Jak funkcja_fuzzy_ryzyko_2v2_opad.py (ten sam setpoint z KontrolerRyzykaOpadBazowy,
# ten sam silnik FL2v2) - JEDYNA różnica to SKĄD bierze się wejście `ryzyko` silnika.
# Oryginał woła histereza_let1.wylicz_poziom_ryzyka(row_data), które ma 10 SZTYWNYCH
# poziomów (1-10) przypisanych do 10 rozłącznych warunków pogodowych (tabela LET-1 +
# własne progi projektu). Tutaj każdy z tych 10 warunków dostaje WŁASNĄ, ADAPTACYJNĄ
# wagę zamiast stałej - i ta waga POWOLI maleje, jeśli w tym REGIONIE (tej lokalizacji)
# dany warunek historycznie okazuje się "fałszywym alarmem": szyna CRT wraca sama nad
# bezpieczny próg, zanim faktyczne zagrożenie (marznący deszcz/śnieg/floor - patrz niżej)
# zdąży się zmaterializować. Pomysł użytkownika (2026-09-30): np. głęboki mróz bywa w
# niektórych regionach normalny i zawsze po nim przychodzi ocieplenie - taki region nie
# powinien być tak samo "przestraszony" spadkiem temperatury jak region, gdzie mróz
# faktycznie zapowiada kłopoty.
#
# MECHANIZM (opóźniona nagroda, patrz _ZdarzenieOczekujace/_rozlicz_zdarzenia niżej):
#   1) Gdy dany warunek (kategoria) staje się aktywny PO RAZ PIERWSZY (zbocze narastające,
#      nie każdy krok symulacji z osobna - jeden epizod = jedno zdarzenie), rejestrujemy
#      "zdarzenie oczekujące" z terminem rozliczenia PROGNOZA_OKNO_H godzin później.
#   2) W KAŻDYM kroku aż do rozliczenia sprawdzamy, czy WYSTĄPIŁO realne zagrożenie -
#      przybliżenie PRAWDZIWEJ kary bezpieczeństwa liczonej w symulacja_fizyczna.py
#      (kara_bezpieczenstwa_crt: marznący deszcz przy CRT<2°C, CRT poniżej bezwzględnego
#      floora -10°C, zalegający śnieg > RISK_SNOW_LINGER_THRESHOLD_MM) - progi importowane
#      WPROST z funkcja_ryzyka_wspolne.py, żeby nie rozjeżdżały się z prawdziwą karą.
#   3) W chwili rozliczenia: jeśli PRZEZ CAŁE okno nie było realnego zagrożenia I CRT
#      zdążyło wrócić nad PROG_BEZPIECZNY_CRT_C (0°C) - to był fałszywy alarm, waga tej
#      kategorii maleje o mały krok (KROK_SPADKU). W przeciwnym razie waga wraca w stronę
#      wartości bazowej, SZYBCIEJ niż maleje (KROK_WZROSTU > KROK_SPADKU) - celowa
#      asymetria: ostrożność ma rosnąć szybko, a maleć powoli, żeby jeden zły sezon od
#      razu przywracał czujność. Waga nigdy nie przekracza wartości bazowej z normy (to
#      i tak już maksymalny/"pełny" poziom ryzyka z LET-1) i nigdy nie spada poniżej
#      PODLOGA_WZGLEDNA=50% bazy (dalej KARZEMY zawsze, tylko mniej - użytkownik był
#      wyraźny, że to nie ma znosić bezpieczeństwa, tylko je delikatnie różnicować).
#
# Wagi startują OD WARTOŚCI BAZOWYCH (identycznych z wylicz_poziom_ryzyka) i adaptują się
# WYŁĄCZNIE w obrębie jednego przebiegu (jak cała rodzina *_nauka_kary* w tym projekcie) -
# nie ma zapisu między uruchomieniami. Przy 5-dniowym oknie testowym to tylko kilka-kilkanaście
# epizodów na kategorię, więc efekt będzie subtelny - to pierwsza wersja do przetestowania,
# nie docelowe strojenie (patrz testy/strojenie_fuzzy_2v2.py jako wzorzec, gdyby trzeba było
# dograć KROK_SPADKU/KROK_WZROSTU/PODLOGA_WZGLEDNA/PROGNOZA_OKNO_H później).

from collections import deque
from datetime import timedelta

from funkcja_ryzyka_wspolne import (
    KontrolerRyzykaOpadBazowy,
    RISK_HRT_ABSOLUTE_FLOOR_C,
    RISK_SNOW_LINGER_THRESHOLD_MM,
)
from silniki_fuzzy import wnioskowanie_fl2v2, binaryzuj

# --- 10 kategorii ryzyka, w TEJ SAMEJ kolejności sprawdzania i z TYMI SAMYMI wartościami
# bazowymi co histereza_let1.wylicz_poziom_ryzyka - musi zostać z nim zsynchronizowane
# ręcznie, jeśli oryginał się kiedyś zmieni (duplikacja jest celowa: potrzebujemy TOŻSAMOŚCI
# kategorii, nie tylko liczby, żeby móc trzymać osobną wagę na każdą z nich). ---
KATEGORIE_RYZYKA_BAZA = {
    'deszcz_mocny': 10.0,
    'deszcz_slaby': 9.0,
    'snieg_mocny': 8.0,
    'snieg_slaby': 7.0,
    'wilgotno_bardzo': 6.0,
    'wilgotno': 5.0,
    'mroz_gleboki': 4.0,
    'chlodno': 3.0,
    'opad_chlodno': 2.0,
    'chlodne_powietrze': 1.0,
}

PROGNOZA_OKNO_H = 10.0          # Ile godzin do przodu czekamy, zanim rozliczymy epizod.
PROG_BEZPIECZNY_CRT_C = 0.0     # CRT musi wrócić NAD ten próg przy rozliczeniu, żeby uznać "fałszywy alarm".
KROK_SPADKU = 0.01              # O tyle maleje waga przy fałszywym alarmie (powoli).
KROK_WZROSTU = 0.05             # O tyle rośnie waga z powrotem, gdy zagrożenie było realne (szybciej - asymetria celowa).
PODLOGA_WZGLEDNA = 0.5          # Waga nie spada poniżej tego ułamka wartości bazowej.


def _kategoria_ryzyka(row_data):
    """Jak histereza_let1.wylicz_poziom_ryzyka, ale zwraca NAZWĘ kategorii (albo None
    dla poziomu 0/brak ryzyka) zamiast liczby - potrzebne do adresowania wag."""
    precip = float(row_data['PRECIP_opad'])
    snow = float(row_data['SNOW_snieg'])
    crt_temp = float(row_data['CRT_temp_niegrzana'])
    at_temp = float(row_data['AT_temp_powietrza'])
    humidity = float(row_data['RH_wilgotnosc_wzgledna'])
    is_raining = precip > 0.0001
    is_snowing = snow > 0.0001

    if is_raining and (crt_temp <= 1.0 or at_temp <= 1.0):
        return 'deszcz_mocny' if precip > 0.001 else 'deszcz_slaby'
    if is_snowing and crt_temp <= 2.0:
        return 'snieg_mocny' if snow > 0.001 else 'snieg_slaby'
    if crt_temp <= 0.5 and humidity > 85.0:
        return 'wilgotno_bardzo' if humidity > 95.0 else 'wilgotno'
    if crt_temp <= -3.0:
        return 'mroz_gleboki'
    if crt_temp <= 0.0:
        return 'chlodno'
    if (is_raining or is_snowing) and crt_temp <= 3.0:
        return 'opad_chlodno'
    if at_temp <= 3.0:
        return 'chlodne_powietrze'
    return None


def _niebezpiecznie_teraz(row_data):
    """Przybliżenie kara_bezpieczenstwa_crt z symulacja_fizyczna.py (te same 3 progi:
    marznący deszcz przy CRT<2°C, CRT poniżej floora, nadmiar zalegającego śniegu) -
    zbinaryzowane (sama obecność zagrożenia, bez wagi/magnitudy - to wystarcza do
    decyzji "czy ten epizod był fałszywym alarmem")."""
    crt_temp = float(row_data['CRT_temp_niegrzana'])
    at_temp = float(row_data['AT_temp_powietrza'])
    precip = float(row_data['PRECIP_opad'])
    snow_depth_mm = float(row_data.get('SNIEG_GRUBOSC_MM', 0.0))

    is_raining = precip > 0.0001
    marznacy_deszcz = is_raining and (crt_temp <= 1.0 or at_temp <= 1.0) and crt_temp < 2.0
    ponizej_floor = crt_temp < RISK_HRT_ABSOLUTE_FLOOR_C
    nadmiar_sniegu = snow_depth_mm > RISK_SNOW_LINGER_THRESHOLD_MM
    return marznacy_deszcz or ponizej_floor or nadmiar_sniegu


class _ZdarzenieOczekujace:
    __slots__ = ('kategoria', 'termin', 'bylo_niebezpiecznie')

    def __init__(self, kategoria, termin):
        self.kategoria = kategoria
        self.termin = termin
        self.bylo_niebezpiecznie = False


class KontrolerFuzzyRyzyko2v2OpadWagiAdaptacyjne(KontrolerRyzykaOpadBazowy):

    def _autotest_startowy(self, row_data):
        return False  # Wymusza natychmiastowe przejście do logiki rozmytej.

    def __init__(self, max_switches_per_day=20):
        super().__init__()
        self.max_switches_per_day = max_switches_per_day

        self._wagi = dict(KATEGORIE_RYZYKA_BAZA)
        self._kategoria_poprzednia = None
        self._zdarzenia_oczekujace = deque()

    def _zaktualizuj_wagi_adaptacyjne(self, row_data, kategoria_teraz):
        timestamp = row_data['Timestamp']

        # Zbocze narastające (nowy epizod albo zmiana kategorii) - jedno zdarzenie na epizod,
        # nie jedno na krok symulacji (inaczej kolejka pęczniałaby bez sensu).
        if kategoria_teraz is not None and kategoria_teraz != self._kategoria_poprzednia:
            self._zdarzenia_oczekujace.append(
                _ZdarzenieOczekujace(kategoria_teraz, timestamp + timedelta(hours=PROGNOZA_OKNO_H)))
        self._kategoria_poprzednia = kategoria_teraz

        if not self._zdarzenia_oczekujace:
            return

        niebezpiecznie = _niebezpiecznie_teraz(row_data)
        if niebezpiecznie:
            for zdarzenie in self._zdarzenia_oczekujace:
                zdarzenie.bylo_niebezpiecznie = True

        crt_teraz = float(row_data['CRT_temp_niegrzana'])
        while self._zdarzenia_oczekujace and self._zdarzenia_oczekujace[0].termin <= timestamp:
            zdarzenie = self._zdarzenia_oczekujace.popleft()
            baza = KATEGORIE_RYZYKA_BAZA[zdarzenie.kategoria]
            podloga = baza * PODLOGA_WZGLEDNA
            if not zdarzenie.bylo_niebezpiecznie and crt_teraz > PROG_BEZPIECZNY_CRT_C:
                # Fałszywy alarm - ryzyko minęło samo, zanim się zmaterializowało.
                self._wagi[zdarzenie.kategoria] = max(podloga, self._wagi[zdarzenie.kategoria] - KROK_SPADKU)
            else:
                # Realne zagrożenie (albo CRT dalej nie wróciło) - przywracamy czujność.
                self._wagi[zdarzenie.kategoria] = min(baza, self._wagi[zdarzenie.kategoria] + KROK_WZROSTU)

    def fuzzy_ryzyko_opad_wagi_adaptacyjne(self, row_data):
        if self._autotest_startowy(row_data):
            return self._ostatnia_moc_autotestu, {'faza': 'autotest', 'autotest_wynik': self.autotest_result}

        hrt_temp = float(row_data['CRT_temp_niegrzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        at_temp = float(row_data['AT_temp_powietrza'])
        target_temperature, need_heat, reason, forecast_min_c, warmup_soon = \
            self._evaluate_risk_setpoint_z_opadem(row_data)

        kategoria = _kategoria_ryzyka(row_data)
        self._zaktualizuj_wagi_adaptacyjne(row_data, kategoria)

        if hrt_temp < -10.0:
            power_percent = 100.0
        else:
            jest_snieg = snow > 0.0
            jest_deszcz = precip > 0.2
            blad_T = target_temperature - hrt_temp
            ryzyko = self._wagi[kategoria] if kategoria is not None else 0.0
            wynik = wnioskowanie_fl2v2(blad_T, hrt_temp, ryzyko, jest_snieg, jest_deszcz, at_temp)
            power_percent = binaryzuj(wynik)
            self._dodaj_flopy(48 + 6)  # Silnik FL2v2 (7 reguł) + narzut adaptacyjnych wag.

        self._krok_modelu(power_percent)

        diagnostics = {
            'target_temperature': target_temperature,
            'need_heat': need_heat,
            'reason': reason,
            'forecast_min_c': forecast_min_c,
            'warmup_soon': warmup_soon,
            'kategoria_ryzyka': kategoria,
            'wagi_ryzyka': dict(self._wagi),
        }
        return power_percent, diagnostics
