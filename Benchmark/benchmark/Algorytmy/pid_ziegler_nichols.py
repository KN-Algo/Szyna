# Algorytmy/pid_ziegler_nichols.py
# ==============================================================================
#  PID z nastawami wg reguly: ZIEGLER-NICHOLS (1942)
#  Wzor: Kp=1.2T/(KL), Ti=2L, Td=0.5L
#  Nastawy (z FOPDT kanalu grzania: K=51.1, T=2954 s, L=2001 s):
#     Kp = 0.0347   Ti = 4001.0 s   Td = 1000.0 s
#  Najstarsza regula; cel: tlumienie 1/4 amplitudy (dosc agresywna).
#  Kod regulatora wspolny dla wszystkich regul -> Algorytmy/pid_baza.py
# ==============================================================================
from Algorytmy.pid_baza import PIDBaza


class RailHeatingController(PIDBaza):
    def __init__(self, target_temp=4.0, **kw):
        super().__init__(Kp=0.0347, Ti=4001.0, Td=1000.0,
                         target_temp=target_temp, **kw)
