# Algorytmy/pid_let_oszczedny.py
# ==============================================================================
#  ALGORYTM HYBRYDOWY: nadzorca normowy (LET-1) + regulator PID + podloga -15C
#
#  IDEA (skad biora sie oszczednosci):
#   Czysty PID trzyma szyne na 4 C przez CALA zime - takze wtedy, gdy wg
#   LET-1 grzanie jest "ekonomicznie nieuzasadnione" (pkt 2.5.3: brak opadow
#   i AT > -5 C). Z kolei automat LET-1 grzeje bang-bang 0/100%, przestrzela
#   okna temperaturowe i pozwala sniegowi zalegac. Hybryda rozdziela role:
#
#   1. NADZORCA (logika okien z LET-1, progi jak w Aktualny_algorytm.py):
#      - TRYB OPADOWY: opad/snieg i AT <= +4 C (Tabela 5)
#            -> cel PID = 5.0 C (tuz nad progiem zalaczenia HRT <= 4 C,
#               daleko od marnotrawnego gornego progu 7 C)
#      - TRYB SUCHEGO MROZU: brak opadu i AT <= -5 C (Tabela 6)
#            -> cel PID = 2.0 C (srodek okna zalaczenia +1 / wylaczenia +3;
#               kazdy stopien celu mniej to wprost mniejsza delta T do
#               utrzymania, czyli mniejsza moc srednia)
#      - POZA WARUNKAMI: grzanie glowne WYLACZONE (pkt 2.5.3)
#
#   2. PODLOGA BEZPIECZENSTWA (LET-5 + wymaganie zespolu):
#      szyna NIGDY ponizej -15 C. Realizacja: drugi, niezalezny PID z celem
#      -13 C (margines 2 C na dynamike i opoznienie grzania ~20 min).
#      Aktywny zawsze - takze gdy nadzorca mowi "nie grzej" - bo norma
#      bezpieczenstwa jest nadrzedna wobec ekonomii.
#
#   3. SELEKTOR MAKSIMUM: moc = max(PID_glowny, PID_podloga).
#      Klasyczna struktura "override control": w normalnych warunkach rzadzi
#      PID glowny (lub cisza), w ekstremalnym mrozie przejmuje podloga.
#
#  MECHANIZMY PID: jak w pid_baza.py (saturacja, anty-windup, pochodna po
#  pomiarze z filtrem). Dodatkowo przy DEZAKTYWACJI PID-u glownego jego
#  calka jest zerowana - inaczej podczas przerwy w grzaniu "nabijalaby sie"
#  na zapas i po powrocie trybu regulator kopnalby pelna moca (windup
#  miedzytrybowy - subtelniejszy kuzyn zwyklego windupu od saturacji).
#
#  NASTAWY: Cohen-Coon (zwyciezca testu regul; ta sama dynamika obiektu
#  obowiazuje niezaleznie od wartosci zadanej, wiec jedne nastawy
#  obsluguja wszystkie tryby).
# ==============================================================================
from Algorytmy.pid_baza import PIDBaza


class RailHeatingController:
    def __init__(self, target_temp=None, max_switches_per_day=None, **_ign):
        # progi normowe - te same co w Aktualny_algorytm.py (LET-1)
        self.at_threshold_precip = 4.0    # opad traktujemy jako snieg do +4 C
        self.at_low_freeze = -5.0         # suchy mroz: reakcja od -5 C
        self.cel_opady = 5.0              # [C] cel PID w trybie opadowym
        self.cel_suchy_mroz = 2.0         # [C] cel PID w trybie suchego mrozu
        self.podloga = -13.0              # [C] cel podlogi (norma: nie mniej
                                          #     niz -15 C; 2 C marginesu)

        # dwa niezalezne regulatory (nastawy Cohen-Coon)
        self.pid_glowny = PIDBaza(Kp=0.0434, Ti=3917.0, Td=648.0,
                                  target_temp=self.cel_opady)
        self.pid_podlogi = PIDBaza(Kp=0.0434, Ti=3917.0, Td=648.0,
                                   target_temp=self.podloga)
        self.tryb_poprzedni = 'wyl'

    def compute_control(self, row_data):
        at = float(row_data['AT_temp_powietrza'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])

        # --- NADZORCA: wyznaczenie trybu wg okien LET-1 ---
        opady = (precip > 0.0 or snow > 0.0) and (at <= self.at_threshold_precip)
        if opady:
            tryb = 'opady'
            self.pid_glowny.cel = self.cel_opady
        elif at <= self.at_low_freeze:
            tryb = 'suchy_mroz'
            self.pid_glowny.cel = self.cel_suchy_mroz
        else:
            tryb = 'wyl'   # pkt 2.5.3: grzanie ekonomicznie nieuzasadnione

        # anty-windup miedzytrybowy: przy powrocie z 'wyl' zaczynamy z czysta
        # calka (stan swiata sprzed przerwy jest nieaktualny)
        if tryb != 'wyl' and self.tryb_poprzedni == 'wyl':
            self.pid_glowny.calka = 0.0
        self.tryb_poprzedni = tryb

        # --- PID glowny: liczony tylko w trybach aktywnych ---
        if tryb != 'wyl':
            u_glowny = self.pid_glowny.compute_control(row_data)
        else:
            u_glowny = 0.0
            # PID sledzi pomiar takze w trybie wyl (pochodna/poprzedni pomiar
            # aktualne przy wznowieniu), ale bez calkowania i bez mocy:
            self.pid_glowny.y_prev = float(row_data['HRT_temp_grzana'])
            self.pid_glowny.t_prev = row_data['Timestamp']

        # --- PODLOGA -15 C: zawsze aktywna (norma nadrzedna wobec ekonomii) ---
        u_podloga = self.pid_podlogi.compute_control(row_data)

        # --- SELEKTOR: bezpieczenstwo wygrywa z ekonomia ---
        return max(u_glowny, u_podloga)
