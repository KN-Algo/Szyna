# Algorytmy/pid_simc.py
# ==============================================================================
#  PID z nastawami wg reguly: SIMC / lambda (Skogestad, 2003)
#  Wzor: Kp=T/(K(tau_c+L)), Ti=min(T,4(tau_c+L)), Td=0; tau_c=L
#  Nastawy (z FOPDT kanalu grzania: K=51.1, T=2954 s, L=2001 s):
#     Kp = 0.0144   Ti = 2954.0 s   Td = 0.0 s
#  Strojenie na zadana stala czasowa petli; dla FOPDT zaleca czyste PI.
#  Kod regulatora wspolny dla wszystkich regul -> Algorytmy/pid_baza.py
# ==============================================================================
from Algorytmy.pid_baza import PIDBaza


class RailHeatingController(PIDBaza):
    def __init__(self, target_temp=4.0, **kw):
        super().__init__(Kp=0.0144, Ti=2954.0, Td=0.0,
                         target_temp=target_temp, **kw)
