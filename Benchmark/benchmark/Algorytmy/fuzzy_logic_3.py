# Algorytmy/fuzzy_logic_3.py
#
# ALGORYTM: regulator rozmyty (Sugeno) wokół STAŁEGO celu T_ZADANA, jak
# fuzzy_logic_1.py, ale wyjście jest modulowane PWM (modulacja szerokości
# impulsu) zamiast ciągłe/binarne - moc % liczona RAZ na okno 60 s, potem
# rozdzielona w czasie na ON/OFF w tym oknie (patrz silniki_fuzzy.WykonawcaPWM).
# Rdzeń wnioskowania (6 reguł) współdzielony z fuzzy_logic_1.py/fuzzy_logic_2.py.

from silniki_fuzzy import wnioskowanie_fl_podstawowe, WykonawcaPWM


class KontrolerFuzzy3:

    def __init__(self, t_zadana=3.0, max_switches_per_day=12, **kwargs):
        self.T_ZADANA = t_zadana
        self.max_switches_per_day = max_switches_per_day
        self.pwm = WykonawcaPWM(okres_cyklu=60)
        self._flops_licznik = 0  # Licznik RZECZYWISTYCH FLOPs - patrz rdzen_kontrolera.KontrolerBazowy._dodaj_flopy.

    def compute_control(self, row_data):
        hrt = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])

        jest_snieg = snow > 0.0
        jest_deszcz = precip > 0.0

        if self.pwm.na_poczatku_cyklu:
            blad_T = self.T_ZADANA - hrt
            wynik = wnioskowanie_fl_podstawowe(blad_T, hrt, jest_snieg, jest_deszcz)
            self.pwm.ustaw_moc_cyklu(wynik)
            self._flops_licznik += 40  # Silnik FL1 liczony RAZ na początku cyklu PWM (60s), nie co krok.

        self._flops_licznik += 2  # Krok PWM (porównanie licznika cyklu).
        return self.pwm.krok()
