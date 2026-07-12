# Algorytmy/pid_cohen_coon.py
# ==============================================================================
#  PID z nastawami wg reguly: COHEN-COON (1953)
#  Wzor: Kp=(1/Kr)(4/3+r/4), Ti=L(32+6r)/(13+8r), Td=4L/(11+2r), r=L/T
#  Nastawy (z FOPDT kanalu grzania: K=51.1, T=2954 s, L=2001 s):
#     Kp = 0.0434   Ti = 3917.0 s   Td = 648.0 s
#  Poprawka ZN dla obiektow z duzym L/T - specjalnosc naszego obiektu.
#  Kod regulatora wspolny dla wszystkich regul -> Algorytmy/pid_baza.py
# ==============================================================================
from Algorytmy.pid_baza import PIDBaza


class RailHeatingController(PIDBaza):
    def __init__(self, target_temp=4.0, **kw):
        super().__init__(Kp=0.0434, Ti=3917.0, Td=648.0,
                         target_temp=target_temp, **kw)
