# Algorytmy/mpc_wspolne.py
#
# Wspólny rdzeń regulatora predykcyjnego (MPC - Model Predictive Control):
# na KAŻDYM 15-minutowym bloku (siatka HORIZON_STEPS/STEP_SECONDS, ta sama co
# prognoza Kalmana i cyfrowy bliźniak w rdzen_kontrolera.py) rozwiązuje QP
# (przez scipy.optimize.minimize, L-BFGS-B, box-constraints 0-100%) na 8
# przyszłych wartościach mocy, minimalizując energię + karę za spadek poniżej
# progu bezpieczeństwa (setpoint z funkcji ryzyka) + karę za skoki mocy -
# i APLIKUJE STAŁĄ moc z PIERWSZEGO bloku planu przez CAŁY ten blok (move
# blocking o długości = horyzont planowania = 900s), zanim przeplanuje od nowa.
#
# W ODRÓŻNIENIU od funkcja_nauka_kary_pid_blizniak.py/_ryzyko.py (cyfrowy
# bliźniak używany TYLKO jako feedforward do korekty POJEDYNCZEGO kroku), tu
# cyfrowy bliźniak jest PODSTAWĄ OPTYMALIZACJI CAŁEJ TRAJEKTORII na horyzoncie.
#
# Dwie konkretne klasy dziedziczą _MPCMachineryMixin RAZEM z odpowiednim
# wariantem funkcji ryzyka (patrz funkcja_mpc_liniowy.py/funkcja_mpc_prognoza.py):
#   KontrolerMPCBazowy      = _MPCMachineryMixin + KontrolerRyzykaBazowy
#   KontrolerMPCBazowyOpad  = _MPCMachineryMixin + KontrolerRyzykaOpadBazowy
#
# OTWARTE PYTANIA Z PROPOZYCJI (rozstrzygnięte tutaj, patrz AGENTS.md):
#   1) Częstotliwość ponownego rozwiązywania QP: co JEDEN blok 15-minutowy
#      (STEP_SECONDS=900s), NIE co krok symulacji - dla dt_sterowania=1s to
#      i tak 900 kroków między przeplanowaniami. Zamiast klasycznego "receding
#      horizon z aplikowaniem tylko pierwszego elementu i przeplanowaniem co
#      krok" (nierealne obliczeniowo przy dt=1s x rok x 43 lokalizacje), plan
#      ma "move blocking" o długości JEDNEGO bloku - decyzyjne QP ma zawsze
#      TYLKO 8 zmiennych (moc na 8 przyszłych bloków 15-min), niezależnie od
#      dt_sterowania. Model wewnętrzny MPC jest zbudowany BEZPOŚREDNIO w
#      rozdzielczości bloku (dt=STEP_SECONDS, patrz _zbuduj_model_blokowy) -
#      NIE w rozdzielczości dt_sterowania jak "cyfrowy bliźniak" reszty
#      algorytmów - to świadomy kompromis wydajność/optymalność (patrz punkt
#      1 propozycji), a nie przeoczenie.
#   2) Solver QP: scipy.optimize.minimize (L-BFGS-B) - BEZ nowej zależności
#      (scipy już jest w requirements.txt, używane też przez _identify_sopdt).
#      Problem jest wypukły (koszt kwadratowy, ograniczenia to tylko boxy),
#      więc L-BFGS-B z różniczkowaniem numerycznym w pełni wystarcza - nie ma
#      potrzeby dedykowanego solvera QP (osqp/cvxpy).
#   3) Fallback przy niepowodzeniu solvera (wyjątek, NaN w wyniku): OSTATNIA
#      ZASTOSOWANA moc (nie 0%, nie algorytm_z_normy) - najbardziej "gładkie"
#      zachowanie awaryjne, spójne z tym, że MPC i tak kara duże skoki mocy w
#      swojej funkcji celu (MPC_WAGA_ZMIANY_MOCY); status trafia do diagnostyki.
#
# BEZPIECZEŃSTWO: niezależnie od zaplanowanej mocy bloku, jeśli w BIEŻĄCEJ
# chwili (dowolny krok, nie tylko granica bloku) funkcja ryzyka mówi
# need_heat=False, moc jest NATYCHMIAST zerowana (patrz _krok_mpc) - MPC
# planuje trajektorię TYLKO gdy grzanie jest w ogóle potrzebne w danym bloku;
# wyłączenie reaguje od razu (fail-safe szybkie wyłączenie, celowe/rozważne
# załączenie - asymetria uzasadniona w AGENTS.md).

import numpy as np
from scipy import signal
from scipy.optimize import minimize

from rdzen_kontrolera import HORIZON_STEPS, STEP_SECONDS, NANOS_PER_BIN

MPC_WAGA_ENERGIA = 0.01          # w1: kara za pobór mocy [na (%)^2] - energia zużyta w bloku.
MPC_WAGA_BEZPIECZENSTWO = 20.0   # w2: kara za spadek przewidywanej HRT poniżej progu bezpieczeństwa [na (°C)^2].
MPC_WAGA_ZMIANY_MOCY = 0.02      # w3: kara za skok mocy między kolejnymi blokami [na (%)^2] - ogranicza zużycie przekaźnika.
# UWAGA: wagi to rozsądny punkt startowy (ten sam rząd wielkości co pozostałe
# człony kosztu przy typowych deficytach rzędu kilku °C), NIE wynik strojenia -
# dobry kandydat do (planowanego, patrz AGENTS.md) grid searchu z Części 2.

MPC_FALLBACK_KC_PERCENT_NA_C = 3.0  # Prosty regulator P (°C -> %) używany, dopóki autotest się nie powiódł/nie zbudował modelu blokowego.
MPC_MAX_ITER_SOLVER = 60            # Limit iteracji L-BFGS-B na jedno przeplanowanie (koszt vs. dokładność).
MPC_HISTORIA_U_MAX_BLOKOW = 64      # Zapas ponad typowe opóźnienie L w blokach (L~1200s / 900s ~ 1-2 bloki).


class _MPCMachineryMixin:
    """
    Mixin (BEZ własnej klasy bazowej - dziedziczy się go RAZEM z
    KontrolerRyzykaBazowy/KontrolerRyzykaOpadBazowy, patrz nagłówek pliku)
    zawierający całą maszynerię MPC: budowę modelu blokowego z wyniku
    autotestu, symulację trajektorii w przód, funkcję kosztu i rozwiązywanie
    QP. NIE zawiera logiki wyznaczania celu (target_temperature/need_heat) -
    to dostarcza klasa funkcji ryzyka, po której się dziedziczy.
    """

    def __init__(self):
        super().__init__()
        self._mpc_model_zbudowany = False
        self._mpc_model_A = None
        self._mpc_model_B = None
        self._mpc_model_C = None
        self._mpc_model_D = None
        self._mpc_model_opoznienie_bloki = 0
        self._mpc_model_x = None
        self._mpc_model_u_history = []

        self._mpc_bin_id = None            # Id bieżącego bloku 15-minutowego (patrz NANOS_PER_BIN).
        self._mpc_plan_power_pct = 0.0     # Moc [%] zaplanowana na BIEŻĄCY blok (pierwszy element ostatniego planu).
        self._mpc_ostatnia_trajektoria = None  # Ostatnio rozwiązana trajektoria (do warm-startu kolejnego QP).
        self._mpc_ostatni_status = 'brak_planu'

    def _zbuduj_model_blokowy_jesli_trzeba(self):
        """
        Buduje dyskretny model stanowy grzałki W ROZDZIELCZOŚCI BLOKU (dt=
        STEP_SECONDS=900s) z parametrów SOPDT zidentyfikowanych przez autotest
        (self.autotest_result) - RAZ, po udanym autoteście. Ta sama metoda co
        rdzen_kontrolera.KontrolerBazowy._zbuduj_model_z_autotestu (tf2ss +
        cont2discrete, zoh), tylko z INNYM krokiem dyskretyzacji - MPC planuje
        na siatce 15-minutowej (patrz uzasadnienie w nagłówku pliku), więc
        model od razu budowany w tej rozdzielczości (1 krok modelu = 1 blok),
        zamiast symulować tysiące podkroków dt_sterowania wewnątrz QP.
        """
        if self._mpc_model_zbudowany or self.autotest_result is None or not self.autotest_result['fit_ok']:
            return

        wynik = self.autotest_result
        K, T1, T2, L = wynik['K'], wynik['T1'], wynik['T2'], wynik['L']
        tf = signal.TransferFunction([K * 0.0, K], np.polymul([T1, 1], [T2, 1]).tolist())
        sys_ss = signal.tf2ss(tf.num, tf.den)
        A_d, B_d, C_d, D_d, _ = signal.cont2discrete(sys_ss, STEP_SECONDS, method='zoh')

        self._mpc_model_A = A_d
        self._mpc_model_B = B_d
        self._mpc_model_C = C_d
        self._mpc_model_D = D_d
        self._mpc_model_opoznienie_bloki = max(int(round(L / STEP_SECONDS)), 0)
        self._mpc_model_x = np.zeros((A_d.shape[0], 1))
        self._mpc_model_u_history = []
        self._mpc_model_zbudowany = True

    def _przewiduj_trajektorie(self, u_blocks_frac):
        """
        Symuluje model blokowy W PRZÓD na len(u_blocks_frac) bloków, BEZ
        mutowania stanu instancji (self._mpc_model_x/_mpc_model_u_history
        pozostają nietknięte - to jest próbna symulacja wewnątrz optymalizacji,
        wywoływana wielokrotnie na jedno rozwiązanie QP). Zwraca tablicę
        wartości 'y' (składowa grzewcza HRT-CRT) NA KONIEC każdego bloku -
        rzeczywisty stan po zastosowaniu mocy tego bloku przez cały jego czas
        trwania (w odróżnieniu od rdzen_kontrolera._krok_modelu, gdzie y jest
        liczone PRZED przesunięciem stanu - tu, dla MPC, bardziej naturalne
        jest przewidywanie temperatury NA KONIEC bloku, czyli PO jego wpływie).
        """
        x = self._mpc_model_x.copy()
        historia = self._mpc_model_u_history
        u_pelna = historia + list(u_blocks_frac)
        opoznienie = self._mpc_model_opoznienie_bloki
        start_idx = len(historia)

        n_bloki = len(u_blocks_frac)
        y = np.empty(n_bloki, dtype=np.float64)
        for i in range(n_bloki):
            idx = start_idx + i
            u_delayed = u_pelna[idx - opoznienie] if idx - opoznienie >= 0 else 0.0
            x = self._mpc_model_A @ x + self._mpc_model_B * u_delayed
            y[i] = float((self._mpc_model_C @ x + self._mpc_model_D * u_delayed)[0, 0])
        return y

    def _koszt_mpc(self, u_blocks_pct, crt_forecast, target_temperature, ostatnia_moc_pct):
        """J = suma po blokach horyzontu: energia + kara bezpieczeństwa (hook, patrz
        _kara_bezpieczenstwa_mpc) + kara za skok mocy."""
        u_blocks_pct = np.asarray(u_blocks_pct, dtype=np.float64)
        y_blocks = self._przewiduj_trajektorie(u_blocks_pct / 100.0)
        hrt_pred = crt_forecast + y_blocks
        kara_bezpieczenstwa = self._kara_bezpieczenstwa_mpc(hrt_pred, target_temperature)
        poprzednie = np.concatenate(([ostatnia_moc_pct], u_blocks_pct))
        delta_u = np.diff(poprzednie)

        return float(
            MPC_WAGA_ENERGIA * np.sum(u_blocks_pct ** 2)
            + kara_bezpieczenstwa
            + MPC_WAGA_ZMIANY_MOCY * np.sum(delta_u ** 2)
        )

    def _kara_bezpieczenstwa_mpc(self, hrt_pred, target_temperature):
        """
        Domyślny kształt kary za zbliżanie się do progu bezpieczeństwa: kwadratowa
        PROGOWA - dokładnie ZERO, dopóki przewidywana HRT jest powyżej progu, kwadrat
        deficytu poniżej (patrz MPC_WAGA_BEZPIECZENSTWO). Nadpisywane przez warianty z
        INNĄ filozofią kary (patrz funkcja_mpc_miekkie.py - bariera wykładnicza, rosnąca
        już PRZED przekroczeniem progu, nie tylko po nim) - hook istnieje właśnie po to,
        żeby taki wariant dzielił CAŁĄ resztę maszynerii MPC (model, solver, fallback)
        bez duplikacji kodu.
        """
        deficyt = np.maximum(target_temperature - hrt_pred, 0.0)
        return MPC_WAGA_BEZPIECZENSTWO * float(np.sum(deficyt ** 2))

    def _rozwiaz_mpc(self, crt_forecast, target_temperature, ostatnia_moc_pct):
        """Rozwiązuje QP (L-BFGS-B, boxy 0-100%) na horyzoncie min(len(crt_forecast), HORIZON_STEPS) bloków."""
        horizon = min(len(crt_forecast), HORIZON_STEPS) if crt_forecast else 0
        if horizon == 0:
            return np.array([ostatnia_moc_pct]), 'brak_prognozy_crt_fallback_ostatnia_moc'

        crt_arr = np.asarray(crt_forecast[:horizon], dtype=np.float64)

        x0 = self._mpc_ostatnia_trajektoria
        if x0 is None or len(x0) != horizon:
            x0 = np.full(horizon, max(ostatnia_moc_pct, 10.0))
        else:
            x0 = np.concatenate([x0[1:], x0[-1:]])  # Warm-start: przesuń poprzedni plan o jeden blok.

        try:
            wynik = minimize(
                self._koszt_mpc, x0, args=(crt_arr, target_temperature, ostatnia_moc_pct),
                method='L-BFGS-B', bounds=[(0.0, 100.0)] * horizon,
                options={'maxiter': MPC_MAX_ITER_SOLVER},
            )
        except Exception:
            return np.full(horizon, ostatnia_moc_pct), 'solver_wyjatek_fallback_ostatnia_moc'

        # Przybliżony koszt liczenia: nfev wywołań kosztu, każde ~O(horizon*n^2) (symulacja modelu) +
        # O(horizon) (redukcja kosztu) - n=wymiar stanu modelu blokowego (zwykle 2).
        n = self._mpc_model_A.shape[0]
        self._dodaj_flopy(int(wynik.nfev) * horizon * (2 * n * n + 4 * n + 6))

        u_opt = np.clip(wynik.x, 0.0, 100.0)
        if not np.all(np.isfinite(u_opt)):
            return np.full(horizon, ostatnia_moc_pct), 'solver_nan_fallback_ostatnia_moc'

        self._mpc_ostatnia_trajektoria = u_opt
        return u_opt, ('ok' if wynik.success else 'solver_niepelna_zbieznosc')

    def _commit_blok_do_modelu(self, moc_pct_zastosowana):
        """Wołane RAZ na przejście do nowego bloku - dopisuje moc FAKTYCZNIE zastosowaną w POPRZEDNIM bloku do stanu modelu blokowego (analogicznie do rdzen_kontrolera._krok_modelu, w rozdzielczości bloku)."""
        u = moc_pct_zastosowana / 100.0
        self._mpc_model_u_history.append(u)
        if len(self._mpc_model_u_history) > MPC_HISTORIA_U_MAX_BLOKOW * 2:
            self._mpc_model_u_history = self._mpc_model_u_history[-MPC_HISTORIA_U_MAX_BLOKOW:]

        idx = len(self._mpc_model_u_history) - 1
        opoznienie = self._mpc_model_opoznienie_bloki
        u_delayed = self._mpc_model_u_history[idx - opoznienie] if idx - opoznienie >= 0 else 0.0
        self._mpc_model_x = self._mpc_model_A @ self._mpc_model_x + self._mpc_model_B * u_delayed
        n = self._mpc_model_A.shape[0]
        self._dodaj_flopy(2 * n * n + 2 * n)

    def _krok_mpc(self, row_data, target_temperature, need_heat, crt_forecast_fn):
        """
        Rdzeń decyzyjny wspólny dla obu wariantów MPC - wołany PO
        _autotest_startowy/_zbuduj_model_blokowy_jesli_trzeba i PO wyznaczeniu
        target_temperature/need_heat (funkcja ryzyka, jawnie z zewnątrz - patrz
        funkcja_mpc_liniowy.py/funkcja_mpc_prognoza.py, każdy z INNYM
        crt_forecast_fn: stała wartość vs prognoza Kalmana).

        Przeplanowuje TYLKO na granicy bloku 15-minutowego (patrz nagłówek
        pliku, punkt 1) - między granicami zwraca moc zaplanowaną na bieżący
        blok, chyba że need_heat akurat teraz jest False (patrz sekcja
        BEZPIECZEŃSTWO w nagłówku pliku).

        Zwraca (moc_procent, status_string).
        """
        timestamp = row_data['Timestamp']
        hrt_temp = float(row_data['HRT_temp_grzana'])
        bin_id = timestamp.value // NANOS_PER_BIN

        if self._mpc_bin_id is None or bin_id != self._mpc_bin_id:
            if self._mpc_bin_id is not None and self._mpc_model_zbudowany:
                self._commit_blok_do_modelu(self._mpc_plan_power_pct)

            if need_heat and self._mpc_model_zbudowany:
                crt_forecast = crt_forecast_fn()
                u_plan, status = self._rozwiaz_mpc(crt_forecast, target_temperature, self._mpc_plan_power_pct)
                self._mpc_plan_power_pct = float(np.clip(u_plan[0], 0.0, 100.0))
            elif need_heat:
                # Autotest się jeszcze nie powiódł/model blokowy nie zbudowany - prosty regulator P jako telefon
                # awaryjny (analogicznie do "wywołujący ma wrócić do zachowania bez cyfrowego bliźniaka" w
                # rdzen_kontrolera._autotest_startowy), zamiast czekać bezczynnie na model.
                self._mpc_plan_power_pct = float(np.clip((target_temperature - hrt_temp) * MPC_FALLBACK_KC_PERCENT_NA_C, 0.0, 100.0))
                status = 'brak_modelu_blokowego_fallback_p'
            else:
                self._mpc_plan_power_pct = 0.0
                status = 'brak_potrzeby_grzania'

            self._mpc_bin_id = bin_id
            self._mpc_ostatni_status = status

        power = self._mpc_plan_power_pct if need_heat else 0.0
        return power, self._mpc_ostatni_status
