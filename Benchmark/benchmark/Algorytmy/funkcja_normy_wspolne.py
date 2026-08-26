# Algorytmy/funkcja_normy_wspolne.py
#
# Przekłada progi zał/wył normy LET-1 (histereza_let1.py, Tabela nr 5 i 6) na
# JEDEN, ciągle zmieniający się cel temperatury (setpoint) - żeby regulator
# ciągły (PID w funkcja_pid_normy.py) albo rozmyty (funkcja_fuzzy_normy.py)
# mógł do niego "dojechać" zamiast przełączać się dyskretnie między zał/wył.
#
# Cel = próg ZAŁĄCZENIA z normy (nie średnia zał/wył - patrz uzasadnienie przy
# _evaluate_norm_setpoint): hrt_on_precip przy opadach, hrt_on_dry przy suchym
# mrozie, w przeciwnym razie brak potrzeby grzania. Dokładnie te same wartości
# liczbowe co w histereza_let1.KontrolerHisterezaLET1 - żadnych nowych progów.

from rdzen_kontrolera import KontrolerBazowy, RowData

NORMA_AT_THRESHOLD_PRECIP_C = 4.0   # Śnieg występuje w naszym klimacie do +4°C (Pkt 2.4.18.3)
NORMA_HRT_ON_PRECIP_C = 4.0         # HRT załączenie przy opadach: +4°C (Tabela nr 5)
NORMA_AT_LOW_FREEZE_C = -5.0        # Suchy mróz dolna granica: -5°C (Tabela nr 6)
NORMA_HRT_ON_DRY_C = 1.0            # HRT załączenie bez opadów: +1°C (Tabela nr 6)


class KontrolerNormyCiaglaBazowy(KontrolerBazowy):
    """
    Nie jest samodzielnym algorytmem (brak wpisu w rejestr_algorytmow.py) -
    dziedziczą po niej funkcja_pid_normy.KontrolerNormaPID i cztery warianty
    funkcja_fuzzy_normy.py (jeden na każdy silnik rozmyty).
    """

    def __init__(self):
        super().__init__()
        self.at_threshold_precip = NORMA_AT_THRESHOLD_PRECIP_C
        self.hrt_on_precip = NORMA_HRT_ON_PRECIP_C
        self.at_low_freeze = NORMA_AT_LOW_FREEZE_C
        self.hrt_on_dry = NORMA_HRT_ON_DRY_C

    def _evaluate_norm_setpoint(self, row_data):
        """
        Odpowiednik _evaluate_risk_setpoint, ale bez pamięci/prognozy/kary za
        śnieg - czysto progi normy LET-1 z bieżącej próbki. Zwraca
        (target_temperature, need_heat).

        Dlaczego próg ZAŁĄCZENIA, a nie np. średnia zał/wył? Bo to właśnie ten
        próg reprezentuje "jak ciepła ma być szyna, żeby norma uznała warunki za
        bezpieczne" - histereza_let1.py grzeje AŻ szyna go osiągnie, my (regulator
        ciągły) po prostu utrzymujemy się w jego okolicy zamiast przelatywać przez
        całe pasmo histerezy w jedną i drugą stronę.
        """
        timestamp = row_data['Timestamp']
        at_temp = float(row_data['AT_temp_powietrza'])
        crt_temp = float(row_data['CRT_temp_niegrzana'])
        hrt_temp = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        rh_humidity = float(row_data['RH_wilgotnosc_wzgledna'])

        reading = RowData()
        reading.timestamp = timestamp
        reading.crt_temp = crt_temp
        reading.hrt_temp = hrt_temp
        reading.at_temp = at_temp
        reading.precip = precip
        reading.snow = snow
        reading.rh_humidity = rh_humidity
        self._append_sensor_history(reading)

        has_precipitation = (precip > 0.0 or snow > 0.0) and (at_temp <= self.at_threshold_precip)

        if has_precipitation:
            need_heat = True
            target_temperature = self.hrt_on_precip
            reason = 'norma: opady - cel = próg załączenia HRT przy opadach'
        elif at_temp <= self.at_low_freeze:
            need_heat = True
            target_temperature = self.hrt_on_dry
            reason = 'norma: suchy mróz - cel = próg załączenia HRT bez opadów'
        else:
            need_heat = False
            target_temperature = hrt_temp
            reason = 'norma: brak zagrożenia'

        return target_temperature, need_heat, reason
