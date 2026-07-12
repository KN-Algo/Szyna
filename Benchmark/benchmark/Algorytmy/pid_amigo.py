# Algorytmy/pid_amigo.py
# ==============================================================================
#  PID z nastawami wg reguly: AMIGO (Astrom-Hagglund, 2004)
#  Wzor: Kp=(0.2+0.45T/L)/K, Ti=L(0.4L+0.8T)/(L+0.1T), Td=0.5LT/(0.3L+T)
#  Nastawy (z FOPDT kanalu grzania: K=51.1, T=2954 s, L=2001 s):
#     Kp = 0.0169   Ti = 2756.0 s   Td = 831.0 s
#  Nowoczesna, wywazona: gwarantowany zapas odpornosci (Ms~1.4).
#  Kod regulatora wspolny dla wszystkich regul -> Algorytmy/pid_baza.py
# ==============================================================================
from Algorytmy.pid_baza import PIDBaza


class RailHeatingController(PIDBaza):
    def __init__(self, target_temp=4.0, **kw):
        super().__init__(Kp=0.0169, Ti=2756.0, Td=831.0,
                         target_temp=target_temp, **kw)
