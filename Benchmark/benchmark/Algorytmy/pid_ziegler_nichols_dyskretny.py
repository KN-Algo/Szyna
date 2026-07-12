# Algorytmy/pid_ziegler_nichols_dyskretny.py
# ==============================================================================
#  PID DYSKRETNY (Ts = 60 s, sample-and-hold) z nastawami wg reguly: ZIEGLER-NICHOLS
#  Nastawy identyczne z wersja ciagla (pid_ziegler_nichols.py) - uzasadnienie
#  w Algorytmy/pid_baza.py (probkowanie 60 s ~ +1.5% efektywnego opoznienia).
# ==============================================================================
from Algorytmy.pid_baza import PIDBazaDyskretna


class RailHeatingController(PIDBazaDyskretna):
    def __init__(self, target_temp=4.0, **kw):
        super().__init__(Kp=0.0347, Ti=4001.0, Td=1000.0, Ts=60.0,
                         target_temp=target_temp, **kw)
