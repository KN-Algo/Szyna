# Algorytmy/pid_cohen_coon_dyskretny.py
# ==============================================================================
#  PID DYSKRETNY (Ts = 60 s, sample-and-hold) z nastawami wg reguly: COHEN-COON
#  Nastawy identyczne z wersja ciagla (pid_cohen_coon.py) - uzasadnienie
#  w Algorytmy/pid_baza.py (probkowanie 60 s ~ +1.5% efektywnego opoznienia).
# ==============================================================================
from Algorytmy.pid_baza import PIDBazaDyskretna


class RailHeatingController(PIDBazaDyskretna):
    def __init__(self, target_temp=4.0, **kw):
        super().__init__(Kp=0.0434, Ti=3917.0, Td=648.0, Ts=60.0,
                         target_temp=target_temp, **kw)
