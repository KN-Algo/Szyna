# Algorytmy/funkcja_nauka_kary_wspolna.py
#
# WSPÓLNA logika dla rodziny algorytmów "uczących się z kar"
# (funkcja_nauka_kary_pid*.py) - zamiast statycznych progów/kar (jak
# funkcja_ryzyka_wspolne.py) kontroler trzyma JEDNĄ liczbę - `_czynnik_nauczony`
# (start=0) - która z czasem ADAPTUJE SIĘ do lokalnych warunków (klimat danej
# lokalizacji, charakterystyka obiektu):
#   - ROŚNIE, gdy zaobserwowano zbyt dużo zalegającego śniegu/lodu (trzeba było
#     grzać MOCNIEJ, żeby temu zapobiec),
#   - MALEJE, gdy zaobserwowano przegrzanie (trzeba było grzać SŁABIEJ).
# Efektywny cel grzania = cel bazowy (z progów normy LET-1, patrz
# funkcja_normy_wspolne.KontrolerNormyCiaglaBazowy) + _czynnik_nauczony.
#
# Aktualizacja "nauczonego" czynnika NIE dzieje się co krok (byłoby zbyt
# nerwowe/nieustabilizowane) - kary są ZLICZANE na bieżąco, a raz na
# OKRES_UCZENIA_S (domyślnie 1 doba symulowanego czasu) następuje JEDNA
# aktualizacja na podstawie zsumowanych kar z tego okresu, po czym liczniki
# się zerują. To jest prosty, jednowymiarowy integrator kar (bez formalnego
# gradientu/RL) - zaakceptowany z użytkownikiem jako wystarczający.

from funkcja_normy_wspolne import KontrolerNormyCiaglaBazowy

# --- PROGI KAR - spójne z istniejącymi progami w projekcie (patrz
# funkcja_ryzyka_wspolne.RISK_SNOW_LINGER_THRESHOLD_MM i próg anomalii
# HRT>35°C używany w generuj_excel_podsumowanie.py), poza KARA_LOD_MM (nowy,
# rozsądny próg dla gołoledzi - w projekcie nie było dotąd osobnego progu na
# samą grubość lodu). ---
KARA_PRZEGRZANIE_HRT_C = 35.0   # Powyżej tej HRT - kara za przegrzanie (jak anomalia w Excelu).
KARA_SNIEG_MM = 5.0             # Powyżej tylu mm śniegu - kara za zbyt małą agresywność (RISK_SNOW_LINGER_THRESHOLD_MM).
KARA_LOD_MM = 2.0               # Powyżej tylu mm lodu - kara za zbyt małą agresywność (gołoledź).

# --- PARAMETRY UCZENIA ---
OKRES_UCZENIA_S = 86400.0       # Co ile sekund symulowanego czasu następuje jedna aktualizacja (1 doba).
WSPOLCZYNNIK_UCZENIA_C = 0.5    # O ile °C przesuwa się _czynnik_nauczony za KAŻDĄ "jednostkę" przewagi kar w okresie.
CZYNNIK_NAUCZONY_MIN_C = -5.0   # Dolny limit (nie schodzimy poniżej normy o więcej niż to).
CZYNNIK_NAUCZONY_MAX_C = 15.0   # Górny limit (nie przegrzewamy w nieskończoność, nawet gdy kary się kumulują).


class KontrolerNaukaKaryBazowy(KontrolerNormyCiaglaBazowy):
    """
    Nie jest samodzielnym algorytmem (brak wpisu w rejestr_algorytmow.py) -
    dziedziczą po niej wszystkie warianty funkcja_nauka_kary_pid*.py.
    """

    def __init__(self):
        super().__init__()
        self._czynnik_nauczony = 0.0
        self._kara_przegrzanie_licznik = 0
        self._kara_snieg_licznik = 0
        self._kara_lod_licznik = 0
        self._ostatnia_aktualizacja_uczenia = None
        # Log (czas, czynnik_nauczony, kary_w_okresie) - PO KAŻDEJ aktualizacji
        # uczenia - do zakładki "Uczenie_adaptacyjne" w Excelu (patrz
        # generuj_excel_podsumowanie.py), pokazującej jak czynnik/skuteczność
        # zmieniają się W CZASIE trwania symulacji (krzywa uczenia).
        self.historia_uczenia = []

    def _zarejestruj_kary(self, hrt_temp, snow_depth_mm, ice_mm):
        """Zlicza zdarzenia kar w BIEŻĄCYM okresie uczenia (patrz _aktualizuj_uczenie)."""
        if hrt_temp > KARA_PRZEGRZANIE_HRT_C:
            self._kara_przegrzanie_licznik += 1
        if snow_depth_mm > KARA_SNIEG_MM:
            self._kara_snieg_licznik += 1
        if ice_mm > KARA_LOD_MM:
            self._kara_lod_licznik += 1

    def _aktualizuj_uczenie(self, timestamp, dodatkowa_kara=0.0):
        """
        Raz na OKRES_UCZENIA_S sekund: przelicza _czynnik_nauczony na podstawie
        zsumowanych kar z minionego okresu i zeruje liczniki. `dodatkowa_kara`
        (opcjonalna, dodawana do różnicy kar PRZED przeliczeniem na deltę) -
        pozwala podklasom z prognozą (patrz warianty _temp/_opad/_blizniak/_ryzyko)
        wstrzyknąć WYPRZEDZAJĄCĄ (przewidywaną, nie tylko zaobserwowaną) karę do
        tej samej aktualizacji, bez duplikowania reszty mechanizmu.

        Zwraca True, jeśli w tym wywołaniu nastąpiła aktualizacja (przydatne do
        logowania/diagnostyki), inaczej False.
        """
        if self._ostatnia_aktualizacja_uczenia is None:
            self._ostatnia_aktualizacja_uczenia = timestamp
            return False

        if (timestamp - self._ostatnia_aktualizacja_uczenia).total_seconds() < OKRES_UCZENIA_S:
            return False

        przewaga_kar = (self._kara_snieg_licznik + self._kara_lod_licznik
                         - self._kara_przegrzanie_licznik + dodatkowa_kara)
        self._czynnik_nauczony += WSPOLCZYNNIK_UCZENIA_C * przewaga_kar
        self._czynnik_nauczony = min(max(self._czynnik_nauczony, CZYNNIK_NAUCZONY_MIN_C), CZYNNIK_NAUCZONY_MAX_C)

        self.historia_uczenia.append({
            'timestamp': timestamp,
            'czynnik_nauczony': self._czynnik_nauczony,
            'kara_przegrzanie': self._kara_przegrzanie_licznik,
            'kara_snieg': self._kara_snieg_licznik,
            'kara_lod': self._kara_lod_licznik,
            'dodatkowa_kara_prognozy': dodatkowa_kara,
        })

        self._kara_przegrzanie_licznik = 0
        self._kara_snieg_licznik = 0
        self._kara_lod_licznik = 0
        self._ostatnia_aktualizacja_uczenia = timestamp
        return True

    def _evaluate_nauczony_setpoint(self, row_data, dodatkowa_kara=0.0, dodatkowy_offset_chwilowy=0.0):
        """
        Cel bazowy z progów normy LET-1 (_evaluate_norm_setpoint) + nauczony
        czynnik (_czynnik_nauczony, aktualizowany raz na dobę) +
        `dodatkowy_offset_chwilowy` (opcjonalny, NIE akumulowany na stałe -
        przejściowy "bonus" z prognozy na TEN konkretny krok, np. wyprzedzające
        dogrzanie przed spodziewanym ochłodzeniem - patrz warianty _temp/_opad).

        Zwraca (target_temperature, need_heat, reason).
        """
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        # Grubość śniegu NIE czytana z row_data['SNIEG_GRUBOSC_MM'] (prawdziwa
        # wartość z modelu fizycznego, dostępna tylko bezpiecznikowi symulacji)
        # - liczona samodzielnie bilansem masy z odczytów, dokładnie jak
        # robiłby to prawdziwy sterownik (patrz
        # rdzen_kontrolera.KontrolerBazowy._estymuj_grubosc_sniegu_mm).
        snow_depth_mm = self._estymuj_grubosc_sniegu_mm(row_data)
        # Lód nie jest osobnym polem row_data (symulacja liczy je wewnętrznie w
        # SnowClimPhysicalModel i zwraca dopiero w historii/statystykach, nie
        # per-krok kontrolerowi) - jako proxy do kary NA BIEŻĄCO (nie wynik
        # końcowy) używamy zalegającego śniegu przy temperaturach ujemnych,
        # gdzie fizycznie zamarza w lód (uproszczenie, świadome i udokumentowane).
        ice_proxy_mm = snow_depth_mm if hrt_temp <= 0.0 else 0.0

        target_temperature, need_heat, reason = self._evaluate_norm_setpoint(row_data)

        self._zarejestruj_kary(hrt_temp, snow_depth_mm, ice_proxy_mm)
        zaktualizowano = self._aktualizuj_uczenie(timestamp, dodatkowa_kara=dodatkowa_kara)
        if zaktualizowano:
            reason = f'{reason} [uczenie: czynnik={self._czynnik_nauczony:+.2f}°C]'

        target_temperature = target_temperature + self._czynnik_nauczony + dodatkowy_offset_chwilowy
        return target_temperature, need_heat, reason
