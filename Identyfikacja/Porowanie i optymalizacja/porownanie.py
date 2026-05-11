import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.widgets import Slider, Button
from scipy import signal
from scipy.stats import pearsonr

# ==================================================================================
# KONFIGURACJA — PARAMETRY TRANSMITANCJI
# ==================================================================================

# --- Model pogodowy: G_AT(s) = K_w * (Tz_w*s + 1) / (T1_w*s + 1) ---
# Wejście: AT (temperatura powietrza) → Wyjście: składnik pogodowy HRT
# K_W   = 1.0774    # wzmocnienie statyczne [-]
# K_W   = K_W * 0.9    # wzmocnienie statyczne [-]
# T1_W  = 5785.78   # stała czasowa [s]
# TZ_W  = 657.05    # stała czasowa zera [s]
# L_W   = 0         # opóźnienie [s]

# # --- Model grzania: G_H(s) = K_h * (Tz_h*s+1) / ((T1_h*s+1)*(T2_h*s+1)) * e^(-L_h*s) ---
# # Wejście: u_bin (0/1 załączenie grzania) → Wyjście: składnik termiczny HRT
# K_H   = 265.79    # wzmocnienie statyczne [°C]
# K_H   = K_H * 0.5    # wzmocnienie statyczne [°C]
# T1_H  = 792.71    # stała czasowa 1 [s]
# T2_H  = 49947.65  # stała czasowa 2 [s]
# T2_H  = T2_H * 0.5  # stała czasowa 2 [s]
# TZ_H  = 5157.87   # stała czasowa zera [s]
# TZ_H  = TZ_H * 0.8   # stała czasowa zera [s]
# L_H   = 30        # opóźnienie [s]

# --- Model pogodowy: G_W(s) ---
# Wejście: AT (temperatura powietrza) → Wyjście: składnik pogodowy HRT
K_W   = 1.09075872    # wzmocnienie statyczne [-]
T1_W  = 5771.977521   # stała czasowa [s]
TZ_W  = 780.0337376   # stała czasowa zera [s]
L_W   = 0             # opóźnienie [s]

# --- Model grzania: G_H(s) ---
# Wejście: u_bin (0/1) → Wyjście: składnik termiczny HRT
K_H   = 51.1163668    # wzmocnienie statyczne [°C]
T1_H  = 1120.914508   # stała czasowa 1 [s]
T2_H  = 2450.968465   # stała czasowa 2 [s]
TZ_H  = 0.0          # stała czasowa zera [s] (praktycznie brak wpływu zera)
L_H   = 1194.184089   # opóźnienie [s] (około 20 minut)


# # --- Zaktualizowany Model pogodowy: G_W(s) ---
# # Wejście: AT (temperatura powietrza) → Wyjście: składnik pogodowy HRT
# K_W  = 1.124083776
# T1_W = 5339.012152
# TZ_W = 1309.189672
# L_W  = 0

# # --- Zaktualizowany Model grzania: G_H(s) ---
# # Wejście: u_bin (0/1) → Wyjście: składnik termiczny HRT
# K_H  = 74.58820507
# T1_H = 2441.993282
# T2_H = 516769.7075
# TZ_H = 316227.766
# L_H  = 121.4116205

# # --- Dodatkowe parametry ---
# offset = 0.7717654254

# --- Offset ---
#offset = 0.5628183043 # stałe przesunięcie modelu
# --- Ścieżka do pliku CSV ---
FILE_PATH = r'D:/Pulpit/KN ALGO/Szyna/Porowanie_modelu_z_obiektem/dane_miesieczne.csv'   # ← zmień na swój plik

# --- Progi czyszczenia danych ---
AT_MIN  = -30.0   # minimalna fizycznie sensowna temp. powietrza [°C]
AT_MAX  =  30.0   # maksymalna fizycznie sensowna temp. powietrza [°C]
HRT_MIN = -30.0   # minimalna temp. szyny [°C]
HRT_MAX =  80.0   # maksymalna temp. szyny [°C]
MOC_MAX = 1e6     # maksymalna moc grzania [W] — usuwanie absurdów

# --- Okno widoku na wykresie ---
WINDOW_SEC = 72000   # szerokość widoku [s] (domyślnie 20h)

# ==================================================================================
# FUNKCJE POMOCNICZE
# ==================================================================================

def build_tf_weather(K, T1, Tz):
    """Transmitancja pogodowa: K*(Tz*s+1)/(T1*s+1)"""
    num = [K * Tz, K]
    den = [T1, 1]
    return signal.TransferFunction(num, den)

def build_tf_heating(K, T1, T2, Tz):
    """Transmitancja grzania: K*(Tz*s+1)/((T1*s+1)*(T2*s+1))"""
    num = [K * Tz, K]
    den = np.polymul([T1, 1], [T2, 1]).tolist()
    return signal.TransferFunction(num, den)

def simulate_tf(tf_c, u, t_sec, L_sec=0, x0=None):
    """
    Symuluje transmitancję ciągłą na niejednorodnej siatce czasowej.
    Interpoluje na równą siatkę → lsim → interpoluje z powrotem.
    """
    # Opóźnienie
    if L_sec > 0:
        i_start = np.searchsorted(t_sec, L_sec)
        t_shifted = t_sec - L_sec
        if i_start < len(u):
            u_delayed = np.interp(t_sec, t_shifted[i_start:],
                                  u[i_start:], left=0.0)
        else:
            u_delayed = np.zeros_like(u)
    else:
        u_delayed = u.copy()

    # Równa siatka czasowa z krokiem = mediana dt
    dt_med  = float(np.median(np.diff(t_sec)))
    dt_med  = max(dt_med, 0.1)
    t_uniform = np.arange(t_sec[0], t_sec[-1] + dt_med, dt_med)
    u_uniform = np.interp(t_uniform, t_sec, u_delayed)

    # Stan początkowy
    if x0 == 'steady':
        n_states = len(tf_c.den) - 1
        if n_states == 1:
            dc_gain = tf_c.num[-1] / tf_c.den[-1]
            x0_vec  = np.array([dc_gain * u_uniform[0] / tf_c.den[-1] * tf_c.den[0]])
        else:
            t_pre  = np.linspace(0, 10 * max(tf_c.den[:-1] / tf_c.den[-1]), 500)
            u_pre  = np.full_like(t_pre, u_uniform[0])
            _, _, x0_vec = signal.lsim(tf_c, U=u_pre, T=t_pre, X0=None)
            x0_vec = x0_vec[-1]
    else:
        x0_vec = x0

    # Symulacja na równej siatce
    _, y_uniform, _ = signal.lsim(tf_c, U=u_uniform, T=t_uniform, X0=x0_vec)

    # Interpolacja wyniku z powrotem na oryginalną siatkę
    y = np.interp(t_sec, t_uniform, y_uniform)
    return y

def clean_signal_at(u_raw, t_sec):
    """
    Czyści AT: usuwa wartości poza [AT_MIN, AT_MAX],
    zastępuje interpolacją liniową między dobrymi próbkami.
    """
    u = u_raw.copy().astype(float)
    bad = (u < AT_MIN) | (u > AT_MAX) | np.isnan(u)
    n_bad = bad.sum()
    u[bad] = np.nan
    idx = np.arange(len(u))
    valid = ~np.isnan(u)
    if valid.sum() > 2:
        u = np.interp(idx, idx[valid], u[valid])
    # Medianowy filtr na oknie 5 próbek dla lekkiego wygładzenia
    from scipy.signal import medfilt
    u = medfilt(u.astype(float), kernel_size=5)
    print(f"  Czyszczenie AT: {n_bad} złych próbek zastąpiono interpolacją")
    return u

def clean_signal_hrt(y_raw):
    """Czyści HRT: clip do fizycznego zakresu."""
    y = y_raw.copy().astype(float)
    bad = (y < HRT_MIN) | (y > HRT_MAX) | np.isnan(y)
    n_bad = bad.sum()
    y = np.clip(y, HRT_MIN, HRT_MAX)
    print(f"  Czyszczenie HRT: {n_bad} próbek poza zakresem → clip")
    return y

def clean_moc(moc_raw):
    """Czyści moc grzania: NaN→0, absurdy→0."""
    m = moc_raw.copy().astype(float)
    m = np.nan_to_num(m, nan=0.0)
    m[m < 0]       = 0.0
    m[m > MOC_MAX] = 0.0
    return m

# ==================================================================================
# WCZYTANIE I PREPROCESSING DANYCH
# ==================================================================================

def load_and_clean(file_path):
    print(f"\nWczytywanie: {file_path}")
    df = pd.read_csv(file_path, sep=';')

    def to_num(col):
        return pd.to_numeric(col.astype(str).str.replace(',', '.'), errors='coerce')

    # Timestamp
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df.sort_values('Timestamp').reset_index(drop=True)

    # Kolumny
    df['HRT_temp_grzana']   = to_num(df['HRT_temp_grzana'])
    df['AT_temp_powietrza'] = to_num(df['AT_temp_powietrza'])
    df['PWRL1_moc'] = (to_num(df['PWRL1_moc']).fillna(0) > 0).astype(float)
    df['PWRL2_moc'] = (to_num(df['PWRL2_moc']).fillna(0) > 0).astype(float)

    # Usuń wiersze bez HRT lub AT
    df = df.dropna(subset=['HRT_temp_grzana', 'AT_temp_powietrza']).reset_index(drop=True)

    # Czas w sekundach od pierwszej próbki
    t_abs = df['Timestamp'].values.astype('datetime64[ns]').astype(np.int64) / 1e9
    t_sec = t_abs - t_abs[0]

    # dt między próbkami [s]
    dt = np.diff(t_sec, prepend=t_sec[0])
    dt[0] = dt[1] if len(dt) > 1 else 10.0
    dt = np.clip(dt, 0.1, 300.0)   # zabezpieczenie: dt w [0.1s, 5min]

    # Sygnały surowe
    y_raw  = df['HRT_temp_grzana'].values
    u_raw  = df['AT_temp_powietrza'].values
    m1_raw = df['PWRL1_moc'].values
    m2_raw = df['PWRL2_moc'].values

    print(f"Wczytano {len(y_raw)} próbek")
    print(f"Okres: {df['Timestamp'].iloc[0]}  →  {df['Timestamp'].iloc[-1]}")
    print(f"Zmienne dt: min={dt.min():.1f}s  max={dt.max():.1f}s  śr={dt.mean():.1f}s")

    # Czyszczenie
    print("\nCzyszczenie danych:")
    u_clean = clean_signal_at(u_raw, t_sec)
    y_clean = clean_signal_hrt(y_raw)

    # Sygnał binarny grzania — bezpośrednio z surowych kolumn DataFrame
    m1 = pd.to_numeric(df['PWRL1_moc'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).values
    m2 = pd.to_numeric(df['PWRL2_moc'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).values
    u_heat = ((m1 + m2) > 0).astype(float)
    n_on = int(np.sum(np.diff(u_heat) > 0))
    print(f"  Grzanie: {n_on} załączeń  ({100*u_heat.mean():.1f}% czasu załączone)")

    return t_sec, dt, u_clean, u_heat, y_clean, df['Timestamp'].values

# ==================================================================================
# SYMULACJA MODELU DWUWEJŚCIOWEGO
# ==================================================================================

def run_model(t_sec, dt, u_at, u_heat, y_meas):
    print("\nSymulacja modelu...")

    tf_w = build_tf_weather(K_W, T1_W, TZ_W)
    tf_h = build_tf_heating(K_H, T1_H, T2_H, TZ_H)

    # Model pogodowy startuje w stanie ustalonym dla AT[0]
    y_weather = simulate_tf(tf_w, u_at,   t_sec, L_sec=L_W, x0='steady')
    # Model grzania startuje od zera (przed grzaniem nic nie grzeje)
    y_heat    = simulate_tf(tf_h, u_heat, t_sec, L_sec=L_H, x0=None)

    y_combined_raw = y_weather + y_heat

    # Offset: średnia z całego okresu PRZED pierwszym grzaniem
    # (tam model i pomiar powinny być w stanie ustalonym)
    heat_on = np.where(u_heat > 0)[0]
    if len(heat_on) > 0:
        # Użyj próbek przed grzaniem (ostatnie 10% tego okresu dla stabilności)
        n_before = heat_on[0]
        n_start  = max(0, int(n_before * 0.7))
        offset   = np.mean(y_meas[n_start:n_before]) - np.mean(y_combined_raw[n_start:n_before])
        print(f"  Offset liczony z próbek {n_start}..{n_before} (przed grzaniem)")
    else:
        # Brak grzania — użyj środkowych 50% danych
        n = len(y_meas)
        offset = np.mean(y_meas[n//4:3*n//4]) - np.mean(y_combined_raw[n//4:3*n//4])
        print(f"  Offset liczony ze środkowych 50% danych (brak grzania)")

    y_model = y_combined_raw + offset

    print(f"  Offset wyrównania stanu początkowego: {offset:.3f} °C")
    print(f"  Składnik pogodowy: zakres [{y_weather.min():.2f}, {y_weather.max():.2f}] °C")
    print(f"  Składnik grzania:  zakres [{y_heat.min():.2f}, {y_heat.max():.2f}] °C")
    print(f"  Model łączny:      zakres [{y_model.min():.2f}, {y_model.max():.2f}] °C")

    return y_model, y_weather + offset, y_heat

# ==================================================================================
# METRYKI KORELACJI
# ==================================================================================

def compute_correlation_metrics(y_meas, y_model):
    """Oblicza R², RMSE, MAE i korelację Pearsona między pomiarem a modelem."""
    mask = ~(np.isnan(y_meas) | np.isnan(y_model))
    ym = y_meas[mask]
    yp = y_model[mask]
    n  = len(ym)

    ss_res = np.sum((ym - yp) ** 2)
    ss_tot = np.sum((ym - np.mean(ym)) ** 2)
    r2     = 1 - ss_res / (ss_tot + 1e-30)
    rmse   = np.sqrt(ss_res / n)
    mae    = np.mean(np.abs(ym - yp))
    r_p, p_val = pearsonr(ym, yp)

    print(f"\n{'='*55}")
    print(f"  METRYKI JAKOŚCI MODELU")
    print(f"{'='*55}")
    print(f"  R²              : {r2:.4f}")
    print(f"  RMSE            : {rmse:.4f} °C")
    print(f"  MAE             : {mae:.4f} °C")
    print(f"  Korelacja Pearsona: r = {r_p:.4f}  (p = {p_val:.2e})")
    print(f"{'='*55}\n")

    return r2, rmse, mae, r_p

# ==================================================================================
# WYKRES Z SUWAKIEM
# ==================================================================================

def plot_results(t_sec, timestamps, u_at, u_heat, y_meas, y_model, y_weather, y_heat_comp,
                 r2, rmse, mae, r_p):

    n = len(t_sec)
    colors = {
        'meas':    '#e8eaf6',
        'model':   '#00e5ff',
        'weather': '#ffb74d',
        'heat':    '#ef5350',
        'at':      '#4fc3f7',
        'uheat':   '#a5d6a7',
        'resid':   '#ce93d8',
    }

    fig = plt.figure(figsize=(20, 11))
    fig.patch.set_facecolor('#0a0d14')

    gs = gridspec.GridSpec(
        4, 1,
        figure=fig,
        left=0.05, right=0.97,
        top=0.93, bottom=0.18,
        hspace=0.08,
        height_ratios=[3.5, 1, 1, 1]
    )

    ax_main  = fig.add_subplot(gs[0])
    ax_resid = fig.add_subplot(gs[1], sharex=ax_main)
    ax_at    = fig.add_subplot(gs[2], sharex=ax_main)
    ax_heat  = fig.add_subplot(gs[3], sharex=ax_main)

    for ax in [ax_main, ax_resid, ax_at, ax_heat]:
        ax.set_facecolor('#0f1520')
        ax.tick_params(colors='#7a8aaa', labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor('#1e2840')
        ax.grid(True, color='#1e2840', alpha=0.7, lw=0.5)

    # ── Główny wykres ────────────────────────────────────────────────────────
    ax_main.plot(t_sec, y_meas,    color=colors['meas'],    lw=1.2, alpha=0.8,
                 label='HRT pomiar', zorder=5)
    ax_main.plot(t_sec, y_model,   color=colors['model'],   lw=1.8, alpha=0.9,
                 label=f'Model łączny  R²={r2:.4f}  RMSE={rmse:.3f}°C', zorder=6)
    ax_main.plot(t_sec, y_weather, color=colors['weather'], lw=1.0, alpha=0.6,
                 ls='--', label='Składnik pogodowy G_AT·AT', zorder=4)
    ax_main.plot(t_sec, y_heat_comp, color=colors['heat'],  lw=1.0, alpha=0.6,
                 ls='--', label='Składnik grzania G_H·u', zorder=4)

    ax_main.set_ylabel("Temperatura [°C]", color='#7a8aaa', fontsize=9)
    ax_main.legend(loc='upper left', fontsize=8, facecolor='#151c2e',
                   labelcolor='white', framealpha=0.9, ncol=2)
    ax_main.set_title(
        f"Model dwuwejściowy szyny kolejowej  |  "
        f"G_AT: K={K_W} T₁={T1_W:.0f}s Tᵤ={TZ_W:.0f}s  |  "
        f"G_H: K={K_H} T₁={T1_H:.0f}s T₂={T2_H:.0f}s Tᵤ={TZ_H:.0f}s L={L_H}s  |  "
        f"r_Pearson={r_p:.4f}",
        color='#c5cfe8', fontsize=8.5, pad=6
    )

    # ── Residua ──────────────────────────────────────────────────────────────
    resid = y_meas - y_model
    ax_resid.axhline(0, color='#3a4060', lw=0.8)
    ax_resid.fill_between(t_sec, resid, color=colors['resid'], alpha=0.5)
    ax_resid.plot(t_sec, resid, color=colors['resid'], lw=0.7, alpha=0.8)
    ax_resid.set_ylabel("Residuum\n[°C]", color='#7a8aaa', fontsize=8)

    # ── AT ───────────────────────────────────────────────────────────────────
    ax_at.fill_between(t_sec, u_at, color=colors['at'], alpha=0.35)
    ax_at.plot(t_sec, u_at, color=colors['at'], lw=0.8)
    ax_at.set_ylabel("AT [°C]", color='#7a8aaa', fontsize=8)

    # ── Sygnał grzania ───────────────────────────────────────────────────────
    ax_heat.fill_between(t_sec, u_heat, color=colors['uheat'], alpha=0.45)
    ax_heat.plot(t_sec, u_heat, color=colors['uheat'], lw=0.8)
    ax_heat.set_ylabel("Grzanie\n[0/1]", color='#7a8aaa', fontsize=8)
    ax_heat.set_ylim(-0.05, 1.25)
    ax_heat.set_xlabel("Czas [s od startu]", color='#7a8aaa', fontsize=8)

    # ── Suwak i przyciski ────────────────────────────────────────────────────
    W      = min(WINDOW_SEC, t_sec[-1])
    t_max  = t_sec[-1]

    ax_slide = fig.add_axes([0.05, 0.08, 0.80, 0.035])
    ax_btn_l = fig.add_axes([0.86, 0.08, 0.04, 0.035])
    ax_btn_r = fig.add_axes([0.91, 0.08, 0.04, 0.035])
    ax_info  = fig.add_axes([0.05, 0.03, 0.90, 0.035])
    ax_info.axis('off')

    for ax in [ax_slide, ax_btn_l, ax_btn_r]:
        ax.set_facecolor('#0a0d14')

    slider_max = max(t_max - W, 1.0)
    slider = Slider(
        ax_slide, 'Czas →', 0, slider_max,
        valinit=0, valstep=max(1.0, W / 200),
        color='#00e5ff', track_color='#1e2840'
    )
    slider.label.set_color('#7a8aaa')
    slider.valtext.set_color('#00e5ff')

    def format_axes():
        x0 = slider.val
        x1 = x0 + W
        ax_main.set_xlim(x0, x1)
        # Etykiety czasu na dolnej osi
        ticks = np.linspace(x0, x1, 8)
        for ax in [ax_heat]:
            ax.set_xticks(ticks)
            i_arr = np.searchsorted(t_sec, ticks)
            i_arr = np.clip(i_arr, 0, len(timestamps) - 1)
            labels = [pd.Timestamp(timestamps[i]).strftime('%d.%m\n%H:%M') for i in i_arr]
            ax.set_xticklabels(labels, fontsize=7, color='#7a8aaa')
        fig.canvas.draw_idle()

    slider.on_changed(lambda v: format_axes())

    STEP  = W // 4
    btn_l = Button(ax_btn_l, '◀', color='#1a2235', hovercolor='#253050')
    btn_r = Button(ax_btn_r, '▶', color='#1a2235', hovercolor='#253050')
    for b in [btn_l, btn_r]:
        b.label.set_color('#c5cfe8')

    btn_l.on_clicked(lambda e: slider.set_val(max(0, slider.val - STEP)))
    btn_r.on_clicked(lambda e: slider.set_val(min(slider_max, slider.val + STEP)))

    def on_scroll(event):
        if event.inaxes in [ax_main, ax_resid, ax_at, ax_heat]:
            delta = -(W // 8) if event.button == 'up' else (W // 8)
            slider.set_val(np.clip(slider.val + delta, 0, slider_max))

    fig.canvas.mpl_connect('scroll_event', on_scroll)

    # Tekst metryk na dole
    ax_info.text(
        0.0, 0.5,
        f"R² = {r2:.4f}   RMSE = {rmse:.4f} °C   MAE = {mae:.4f} °C   "
        f"Pearson r = {r_p:.4f}   "
        f"G_AT: {K_W}·({TZ_W}s+1)/({T1_W}s+1)   "
        f"G_H: {K_H}·({TZ_H}s+1)/(({T1_H}s+1)·({T2_H}s+1))·e^(-{L_H}s)",
        transform=ax_info.transAxes,
        color='#4a5570', fontsize=7.5, va='center'
    )

    format_axes()

    plt.savefig("symulacja_modelu_szyny.png", dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    print("Wykres zapisany jako: symulacja_modelu_szyny.png")
    plt.show()

# ==================================================================================
# MAIN
# ==================================================================================

if __name__ == "__main__":
    # 1. Wczytaj i oczyść dane
    t_sec, dt, u_at, u_heat, y_meas, timestamps = load_and_clean(FILE_PATH)

    # 2. Uruchom model
    y_model, y_weather, y_heat_comp = run_model(t_sec, dt, u_at, u_heat, y_meas)

    # 3. Oblicz metryki
    r2, rmse, mae, r_p = compute_correlation_metrics(y_meas, y_model)

    # 4. Wykres
    plot_results(t_sec, timestamps, u_at, u_heat, y_meas,
                 y_model, y_weather, y_heat_comp,
                 r2, rmse, mae, r_p)