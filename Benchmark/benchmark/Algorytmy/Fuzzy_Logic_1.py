class RailHeatingController:
    def __init__(self, t_zadana=3.0, max_switches_per_day=12, **kwargs):
        self.T_ZADANA = t_zadana
        self.max_switches_per_day = max_switches_per_day  # kompatybilność z main_test.py (limit niezaimplementowany w FL1)
    
        # Singletony Sugeno (pozostają płynne do obliczeń)
        self.MOC_OFF = 0.0
        self.MOC_LOW = 25.0
        self.MOC_MED = 60.0
        self.MOC_HIGH = 100.0

    def _rampa_rosnaca(self, x, x0, x1):
        if x <= x0: return 0.0
        if x >= x1: return 1.0
        return (x - x0) / (x1 - x0)

    def _rampa_malejaca(self, x, x0, x1):
        if x <= x0: return 1.0
        if x >= x1: return 0.0
        return 1.0 - ((x - x0) / (x1 - x0))

    def _trojkat(self, x, x0, x_srodek, x1):
        if x <= x0 or x >= x1: return 0.0
        if x == x_srodek: return 1.0
        if x < x_srodek: return (x - x0) / (x_srodek - x0)
        return 1.0 - ((x - x_srodek) / (x1 - x_srodek))

    def _fuzzifikuj_temperature(self, blad_T, hrt):
        ok = self._rampa_malejaca(blad_T, 0.0, 3.0)
        chlodno = self._trojkat(blad_T, 0.0, 3.0, 6.0)
        mrozno = self._rampa_rosnaca(blad_T, 3.0, 6.0)
        lodowato = self._rampa_malejaca(hrt, -15.0, -12.0)
        return ok, chlodno, mrozno, lodowato

    def compute_control(self, row_data):
        hrt = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])
        
        # Progi odcięcia małych opadów
        jest_snieg = snow > 0.0
        jest_deszcz = precip > 0.0
        
        # 1. Obliczenie mocy rozmytej (wykonywane przy każdym wywołaniu compute_control)
        blad_T = self.T_ZADANA - hrt
        t_ok, t_chlodno, t_mrozno, t_lodowato = self._fuzzifikuj_temperature(blad_T, hrt)
        
        opad_aktywny = 1.0 if (jest_snieg or jest_deszcz) else 0.0
        opad_brak = 1.0 if not (jest_snieg or jest_deszcz) else 0.0
        
        r1 = t_ok
        r2 = min(t_chlodno, opad_brak)
        r3 = min(t_chlodno, opad_aktywny)
        r4 = min(t_mrozno, opad_brak)
        r5 = min(t_mrozno, opad_aktywny)
        r6 = t_lodowato
        licznik = (r1 * self.MOC_OFF + 
                        r2 * self.MOC_OFF + 
                        r3 * self.MOC_MED + 
                        r4 * self.MOC_LOW + 
                        r5 * self.MOC_HIGH + 
                        r6 * self.MOC_HIGH)        
        
        mianownik = r1 + r2 + r3 + r4 + r5 + r6
        
        if mianownik == 0:
            return 0.0
        
        wynik = licznik / mianownik

        if wynik < 10.0:
            wynik = 0.0
        if wynik > 90.0:
            wynik = 100.0

        return wynik