# Algorytmy/pid_let_szron.py
# ==============================================================================
#  ALGORYTM HYBRYDOWY v2: grzanie WARUNKOWE w suchym mrozie (detekcja szronu)
#
#  ROZNICA WZGLEDEM pid_let_oszczedny.py (v1):
#   v1 w suchym mrozie (AT <= -5 C) trzymal szyne na +2 C non stop - zgodnie
#   z literalnym oknem Tabeli 6 LET-1. Na scenariuszu typu Suwalki 2010
#   (caly miesiac mrozu) oznacza to grzanie ~97% czasu, bo fizyka: utrzymanie
#   dodatniej temperatury przy AT = -11 C wymaga ciaglego doplywu mocy.
#
#   v2 pyta o CEL tego grzania. W suchym mrozie (brak opadu) jedynym
#   zagrozeniem dla rozjazdu jest SZRON - osadzanie sie lodu z pary wodnej,
#   ktore zachodzi TYLKO gdy temperatura powierzchni szyny spadnie do punktu
#   szronu (odpowiednik punktu rosy dla lodu). Punkt szronu wyliczamy na
#   biezaco z wilgotnosci i temperatury powietrza (odwrocony wzor Magnusa).
#   Dopoki szyna jest cieplejsza od punktu szronu + margines - szron
#   fizycznie nie moze powstac i grzanie jest zbedne. Szyna plynie w dol,
#   pilnowana wylacznie podloga -15 C (wymaganie zespolu / LET-5).
#
#  !!! UWAGA FORMALNA (do decyzji zespolu i Wiktora):
#   v2 odchodzi od literalnego okna +1/+3 C Tabeli 6 LET-1 na rzecz
#   realizacji jej CELU (brak oblodzenia) srodkami warunkowymi. To jest
#   propozycja inzynierska wymagajaca akceptacji interpretacji normy -
#   dlatego dostarczamy ja jako OSOBNY modul, a nie podmiane v1.
#
#  TRYBY (nadzorca):
#   1. OPADY (opad/snieg i AT <= +4 C):    cel PID = 5.0 C   [jak v1, Tab. 5]
#   2. RYZYKO SZRONU (AT < 0, brak opadu,
#      HRT blisko punktu szronu):          cel PID = punkt_szronu + 2.0 C
#      - cel jest RUCHOMY i zwykle UJEMNY (np. szron przy -14 C -> cel -12 C),
#        wiec utrzymanie go kosztuje ulamek energii celu +2 C
#   3. PODLOGA -15 C (zawsze):             cel PID = -13.0 C  [margines 2 C]
#   4. poza warunkami: grzanie wylaczone (pkt 2.5.3 LET-1)
#   Wyjscie = max(tryb aktywny, podloga)  [override control]
#
#  Punkt rosy z RH i AT (odwrocony Magnus; dla T<0 wsp. dla lodu daja punkt
#  szronu nieznacznie WYZSZY od punktu rosy - uzywamy wersji lodowej, czyli
#  konserwatywnie wczesniej reagujemy):
#     z  = ln(RH/100) + a*T/(b+T),   T_szronu = b*z/(a - z)
#     a = 22.587, b = 273.86  (stale Magnusa nad lodem)
# ==============================================================================
import math
from Algorytmy.pid_baza import PIDBaza


class RailHeatingController:
    def __init__(self, target_temp=None, max_switches_per_day=None, **_ign):
        self.at_threshold_precip = 4.0
        self.cel_opady = 5.0
        self.margines_szronu = 2.0     # [C] ile nad punktem szronu trzymamy szyne
        self.strefa_czuwania = 1.5     # [C] gdy HRT zblizy sie do punktu szronu
                                       #     na mniej niz tyle -> aktywuj grzanie
        self.podloga = -13.0           # [C] twarde minimum (norma: >= -15 C)

        self.pid_glowny = PIDBaza(Kp=0.0434, Ti=3917.0, Td=648.0,
                                  target_temp=self.cel_opady)
        self.pid_podlogi = PIDBaza(Kp=0.0434, Ti=3917.0, Td=648.0,
                                   target_temp=self.podloga)
        self.tryb_poprzedni = 'wyl'

    @staticmethod
    def punkt_szronu(at, rh):
        """Punkt szronu [C] z temperatury powietrza i wilgotnosci wzglednej.
        Odwrocony wzor Magnusa ze stalymi nad lodem (konserwatywnie)."""
        rh = min(100.0, max(1.0, rh))
        a, b = 22.587, 273.86
        z = math.log(rh / 100.0) + a * at / (b + at)
        return b * z / (a - z)

    def compute_control(self, row_data):
        at = float(row_data['AT_temp_powietrza'])
        rh = float(row_data['RH_wilgotnosc'])
        hrt = float(row_data['HRT_temp_grzana'])
        precip = float(row_data['PRECIP_opad'])
        snow = float(row_data['SNOW_snieg'])

        # --- NADZORCA ---
        opady = (precip > 0.0 or snow > 0.0) and (at <= self.at_threshold_precip)
        if opady:
            tryb = 'opady'
            self.pid_glowny.cel = self.cel_opady
        elif at < 0.0:
            # suchy mroz: grzej TYLKO gdy szyna zbliza sie do punktu szronu
            t_szron = self.punkt_szronu(at, rh)
            if hrt <= t_szron + self.strefa_czuwania:
                tryb = 'szron'
                # cel ruchomy: tuz nad punktem szronu, ale nigdy ponizej podlogi
                self.pid_glowny.cel = max(t_szron + self.margines_szronu,
                                          self.podloga)
            else:
                tryb = 'wyl'   # sucho i szyna bezpiecznie nad punktem szronu
        else:
            tryb = 'wyl'

        # anty-windup miedzytrybowy (jak w v1)
        if tryb != 'wyl' and self.tryb_poprzedni == 'wyl':
            self.pid_glowny.calka = 0.0
        self.tryb_poprzedni = tryb

        if tryb != 'wyl':
            u_glowny = self.pid_glowny.compute_control(row_data)
        else:
            u_glowny = 0.0
            self.pid_glowny.y_prev = hrt
            self.pid_glowny.t_prev = row_data['Timestamp']

        # --- PODLOGA -15 C: zawsze aktywna ---
        u_podloga = self.pid_podlogi.compute_control(row_data)

        return max(u_glowny, u_podloga)
