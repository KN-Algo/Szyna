# Algorytmy/pid_amigo_dyskretny.py
# ==============================================================================
#  PID DYSKRETNY (Ts = 60 s, sample-and-hold) z nastawami wg reguly: AMIGO
#  Nastawy identyczne z wersja ciagla (pid_amigo.py) - uzasadnienie
#  w Algorytmy/pid_baza.py (probkowanie 60 s ~ +1.5% efektywnego opoznienia).
# ==============================================================================
from Algorytmy.pid_baza import PIDBazaDyskretna


class RailHeatingController(PIDBazaDyskretna):
    def __init__(self, target_temp=4.0, **kw):
        super().__init__(Kp=0.0169, Ti=2756.0, Td=831.0, Ts=60.0,
                         target_temp=target_temp, **kw)
