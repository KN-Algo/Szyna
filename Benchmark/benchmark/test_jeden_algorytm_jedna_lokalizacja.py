# ==============================================================================
# TEST: JEDEN ALGORYTM, JEDNA LOKALIZACJA - interaktywny podgląd pracy JEDNEGO
# wybranego algorytmu sterowania ogrzewaniem rozjazdów na pełnym sezonie pogodowym.
#
# Dawniej main_test.py / test_pojedynczego_algorytmu.py. Służy WYŁĄCZNIE do
# testowania pojedynczych algorytmów - wybiera się je z mapy
# Algorytmy/rejestr_algorytmow.py (ta sama mapa, z której korzystają pozostałe
# dwa skrypty testujące, więc wszystkie trzy zawsze widzą ten sam zestaw
# dostępnych algorytmów).
#
# test_wszystkie_algorytmy_jedna_lokalizacja.py jest ROZSZERZENIEM tego skryptu:
# używa tego samego rdzenia symulacji (symulacja_fizyczna.py), ale uruchamia
# WSZYSTKIE algorytmy naraz i porównuje wyniki zamiast pokazywać interaktywne
# GUI dla jednego.
# ==============================================================================

import os
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
import matplotlib.gridspec as gridspec

matplotlib.use('TkAgg')  # interaktywne okno GUI

import symulacja_fizyczna as fiz
from rejestr_algorytmow import ALGORYTMY, stworz_kontroler

# ==============================================================================
# WYBÓR ALGORYTMU - zmień tylko tę jedną linijkę, żeby przetestować inny
# algorytm z rejestru (dostępne nazwy: patrz Algorytmy/rejestr_algorytmow.py).
# ==============================================================================
NAZWA_ALGORYTMU = 'risk_function_pid'

MAX_SWITCHES_PER_DAY = 100  # budżet dzienny wywiedziony z życiowego budżetu przekaźnika (~500 000) - patrz test_wszystkie_rownolegle.py
WINDOW_SEC = 3600 * 2  # Szerokość okna podglądu (2 godziny)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NAZWA_PLIKU_CSV = os.path.join(BASE_DIR, "Pogoda_pomiary_15_minut", "suwalki_15min_2023.csv")
SCIEZKA_WYNIKOW = os.path.join(BASE_DIR, "wyniki", f"wyniki_symulacji_1s_{NAZWA_ALGORYTMU}.csv")
os.makedirs(os.path.dirname(SCIEZKA_WYNIKOW), exist_ok=True)

if NAZWA_ALGORYTMU not in ALGORYTMY:
    raise ValueError(f"Nieznany algorytm '{NAZWA_ALGORYTMU}'. Dostępne: {', '.join(ALGORYTMY.keys())}")
print(f"🧪 Testowany algorytm: {NAZWA_ALGORYTMU} - {ALGORYTMY[NAZWA_ALGORYTMU]['opis']}")

# ==============================================================================
# SYMULACJA (wspólny rdzeń z porownanie_algorytmow.py)
# ==============================================================================
df_1s = fiz.wczytaj_pogode_1s(NAZWA_PLIKU_CSV)
dt = 1.0

print("⚙️ Konwersja modeli transmitancyjnych do przestrzeni stanów...")
A_wd, B_wd, C_wd, D_wd, A_hd, B_hd, C_hd, D_hd, punkty_opoznienia = fiz.przygotuj_modele_stanowe(dt)

print("🧮 Wyliczanie hurtowe wpływu środowiska (składowa CRT)...")
at_array = df_1s['temperatura_powietrza_C'].to_numpy()
hrt_weather_all = fiz.wylicz_skladowa_pogodowa(at_array, A_wd, B_wd, C_wd, D_wd, dt)

kontroler, metoda = stworz_kontroler(NAZWA_ALGORYTMU, max_switches_per_day=MAX_SWITCHES_PER_DAY)

print(f"🚀 Start symulacji dla CAŁEGO OKRESU (algorytm: {NAZWA_ALGORYTMU})...")
df_wyniki, stats, _, _ = fiz.uruchom_kontroler(
    NAZWA_ALGORYTMU, kontroler, metoda, df_1s, hrt_weather_all,
    A_hd, B_hd, C_hd, D_hd, punkty_opoznienia, dt=dt,
)

print("💾 Trwa zapisywanie danych do pliku CSV...")
df_wyniki.to_csv(SCIEZKA_WYNIKOW, index=False)
print(f"✅ Sukces! Pełna historia zapisana w: {SCIEZKA_WYNIKOW}\n")

# ==============================================================================
# RAPORT STATYSTYCZNY
# ==============================================================================
przelaczen_na_dobe = stats['przelaczenia'] / max(stats['dni'], 1e-6)
print("=" * 65)
print(f"📊       RAPORT STATYSTYCZNY: {NAZWA_ALGORYTMU}")
print("=" * 65)
print(f"⏱️  Całkowity czas analizy:        {stats['dni']:.2f} dni")
print(f"⚡ Przyjęta moc znamionowa:        {fiz.MOC_ZAMIANOWA_GRZALKI_KW} kW")
print(f"🔋 Szacunkowe zużycie energii:     {stats['energia_kwh']:.3f} kWh")
print(f"📈 Średnia moc grzania:            {stats['srednia_moc_pct']:.1f} %")
print("-" * 65)
print(f"🔄 Całkowita liczba przełączeń:    {stats['przelaczenia']} razy")
print(f"📅 Średnia liczba przełączeń/dobę: {przelaczen_na_dobe:.2f} (limit dobowy: {MAX_SWITCHES_PER_DAY})")
print("-" * 65)
print(f"❄️  Maksymalny śnieg na szynie:     {stats['max_snieg_mm']:.2f} mm")
print(f"🧊 Maksymalny lód na szynie:       {stats['max_lod_mm']:.2f} mm")
print(f"⏳ Czas zalegania śniegu:          {stats['godziny_ze_sniegiem']:.2f} godz.")
print(f"🌡️  Zakres HRT:                     [{stats['min_hrt']:.2f}, {stats['max_hrt']:.2f}] °C")
print("=" * 65)

# ==============================================================================
# OKNO INTERAKTYWNE (DARK MODE)
# ==============================================================================
print("\n📈 Uruchamianie zaawansowanego okna wykresu...")

df_wyniki['t_sec'] = np.arange(len(df_wyniki))
t_sec = df_wyniki['t_sec'].values
timestamps_gui = pd.to_datetime(df_wyniki['Timestamp']).values

colors = {
    'hrt':     '#e74c3c', 'crt':     '#95a5a6', 'at':      '#34495e',
    'moc':     '#f1c40f', 'opad':    '#3498db', 'snieg':   '#2ecc71',
    'lod':     '#9b59b6', 'bg_dark': '#0a0d14', 'bg_axes': '#0f1520',
    'grid':    '#1e2840', 'text':    '#7a8aaa'
}

fig = plt.figure(figsize=(18, 11))
fig.patch.set_facecolor(colors['bg_dark'])

gs = gridspec.GridSpec(2, 1, figure=fig, left=0.06, right=0.93, top=0.94, bottom=0.18, hspace=0.12)
ax1 = fig.add_subplot(gs[0])
ax2 = fig.add_subplot(gs[1], sharex=ax1)

for ax in [ax1, ax2]:
    ax.set_facecolor(colors['bg_axes'])
    ax.tick_params(colors=colors['text'], labelsize=9)
    for sp in ax.spines.values():
        sp.set_edgecolor(colors['grid'])
    ax.grid(True, color=colors['grid'], alpha=0.7, lw=0.5)

fig.suptitle(f"Interaktywna analiza pracy układu grzewczego szyn - {NAZWA_ALGORYTMU}",
             color='#c5cfe8', fontsize=14, fontweight='bold')

line_hrt, = ax1.plot([], [], color=colors['hrt'], linewidth=2, label='HRT (Szyna Ogrzewana)')
line_crt, = ax1.plot([], [], color=colors['crt'], linestyle='--', linewidth=1.5, label='CRT (Szyna Nieogrzewana)')
line_at,  = ax1.plot([], [], color=colors['at'], linestyle=':', linewidth=1.5, label='AT (Otoczenie)')
ax1.set_ylabel('Temperatura (°C)', color=colors['text'], fontweight='bold')

ax1_moc = ax1.twinx()
ax1_moc.tick_params(colors=colors['moc'], labelsize=9)
ax1_moc.set_ylabel('Wysterowanie mocy grzałki (%)', color=colors['moc'], fontweight='bold')
ax1_moc.set_ylim(-5, 105)
fill_moc = [None]

line_opad, = ax2.plot([], [], color=colors['opad'], alpha=0.7, label='Intensywność opadów')
ax2.set_ylabel('Bieżący opad (mm/15min)', color=colors['opad'], fontweight='bold')

ax2_stan = ax2.twinx()
ax2_stan.tick_params(colors=colors['snieg'], labelsize=9)
line_snieg, = ax2_stan.plot([], [], color=colors['snieg'], linewidth=2, label='Śnieg na szynie (mm)')
line_lod,   = ax2_stan.plot([], [], color=colors['lod'], linewidth=2, linestyle='-.', label='Lód na szynie (mm)')
ax2_stan.set_ylabel('Grubość warstwy (mm)', color=colors['snieg'], fontweight='bold')

ax1.legend(loc='upper left', fontsize=9, facecolor='#151c2e', labelcolor='white', framealpha=0.8)
ax2.legend(loc='upper right', fontsize=9, facecolor='#151c2e', labelcolor='white', framealpha=0.8)

t_max = t_sec[-1]
slider_max = max(t_max - WINDOW_SEC, 1.0)

ax_slide = fig.add_axes([0.06, 0.08, 0.75, 0.035])
ax_btn_l = fig.add_axes([0.83, 0.08, 0.04, 0.035])
ax_btn_r = fig.add_axes([0.88, 0.08, 0.04, 0.035])

for ax in [ax_slide, ax_btn_l, ax_btn_r]:
    ax.set_facecolor(colors['bg_dark'])

slider = Slider(ax_slide, 'Czas →', 0, slider_max, valinit=0, valstep=max(1.0, WINDOW_SEC / 100), color='#00e5ff', track_color=colors['grid'])
slider.label.set_color(colors['text'])
slider.valtext.set_color('#00e5ff')


def format_axes():
    x0 = int(slider.val)
    x1 = int(x0 + WINDOW_SEC)

    mask = (t_sec >= x0) & (t_sec <= x1)
    df_sub = df_wyniki.iloc[mask]

    if len(df_sub) == 0:
        return

    step = max(1, len(df_sub) // 600)
    df_resampled = df_sub.iloc[::step]

    sub_t = df_resampled['t_sec'].values

    line_hrt.set_data(sub_t, df_resampled['HRT'])
    line_crt.set_data(sub_t, df_resampled['CRT'])
    line_at.set_data(sub_t, df_resampled['AT'])

    if fill_moc[0] is not None:
        fill_moc[0].remove()
    fill_moc[0] = ax1_moc.fill_between(sub_t, df_resampled['Moc_procent'], color=colors['moc'], alpha=0.15)

    line_opad.set_data(sub_t, df_resampled['PRECIP_opad_1s'] * 900)
    line_snieg.set_data(sub_t, df_resampled['Snieg_mm'])
    line_lod.set_data(sub_t, df_resampled['Lod_mm'])

    ax1.set_xlim(x0, x1)
    try:
        y1_min = min(df_resampled['HRT'].min(), df_resampled['AT'].min()) - 2
        y1_max = max(df_resampled['HRT'].max(), df_resampled['CRT'].max()) + 2
        ax1.set_ylim(y1_min, y1_max)

        y2_max = max(df_resampled['Snieg_mm'].max(), df_resampled['Lod_mm'].max())
        ax2_stan.set_ylim(-0.2, max(y2_max + 0.5, 2.0))

        y2_opad_max = (df_resampled['PRECIP_opad_1s'] * 900).max()
        ax2.set_ylim(-0.1, max(y2_opad_max + 0.5, 1.0))
    except ValueError:
        pass

    ticks = np.linspace(x0, x1, 6)
    ax2.set_xticks(ticks)

    i_arr = np.searchsorted(t_sec, ticks)
    i_arr = np.clip(i_arr, 0, len(timestamps_gui) - 1)
    labels = [pd.Timestamp(timestamps_gui[i]).strftime('%d.%m\n%H:%M:%S') for i in i_arr]
    ax2.set_xticklabels(labels, fontsize=8, color=colors['text'])

    fig.canvas.draw_idle()


slider.on_changed(lambda v: format_axes())

STEP = WINDOW_SEC // 4
btn_l = Button(ax_btn_l, '◀', color='#1a2235', hovercolor='#253050')
btn_r = Button(ax_btn_r, '▶', color='#1a2235', hovercolor='#253050')

for b in [btn_l, btn_r]:
    b.label.set_color('#c5cfe8')

btn_l.on_clicked(lambda e: slider.set_val(max(0, slider.val - STEP)))
btn_r.on_clicked(lambda e: slider.set_val(min(slider_max, slider.val + STEP)))


def on_scroll(event):
    if event.inaxes in [ax1, ax2, ax1_moc, ax2_stan]:
        delta = -(WINDOW_SEC // 6) if event.button == 'up' else (WINDOW_SEC // 6)
        slider.set_val(np.clip(slider.val + delta, 0, slider_max))


fig.canvas.mpl_connect('scroll_event', on_scroll)
format_axes()

print("💡 WSKAZÓWKA: Symulacja ukończona. Przewijaj rolką myszy nad wykresem, aby przeglądać dane z bieguna zimna!")
plt.show()
