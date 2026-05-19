# ==============================================================================
#           PLIK: analizator_wynikow_interaktywny.py (Wersja Premium)
# ==============================================================================
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
import matplotlib.gridspec as gridspec
import os
import matplotlib

# Wymuszenie interaktywnego okna
matplotlib.use('TkAgg')  

# ==============================================================================
# PARAMETRY I KONFIGURACJA
# ==============================================================================
MOC_ZAMIANOWA_GRZALKI_KW = 14.0  # kW mocy na metr/rozjazd
NAZWA_PLIKU_WEJSCIOWEGO = "D:\\Pulpit\\KN ALGO\\Szyna\\benchmark\\wyniki_symualcji_1s.csv"
WINDOW_SEC = 3600 * 2            # Szerokość okna podglądu (np. 2 godziny)

if not os.path.exists(NAZWA_PLIKU_WEJSCIOWEGO):
    print(f"❌ Błąd: Brak pliku '{NAZWA_PLIKU_WEJSCIOWEGO}'.")
    print("👉 Uruchom najpierw główny symulator!")
    exit()

print(f"📖 Wczytywanie danych: {NAZWA_PLIKU_WEJSCIOWEGO} ...")
df = pd.read_csv(NAZWA_PLIKU_WEJSCIOWEGO)

# Tworzymy wektor czasu w sekundach od startu dla łatwiejszego indeksowania suwakiem
df['t_sec'] = np.arange(len(df))
t_sec = df['t_sec'].values
timestamps = pd.to_datetime(df['Timestamp']).values

# --- Statystyki do raportu ---
df['Grzanie_ON'] = df['Moc_procent'] > 0.0
calkowity_czas_s = len(df)
czas_grzania_s = df['Grzanie_ON'].sum()
procent_czasu_grzania = (czas_grzania_s / calkowity_czas_s) * 100

df['Energia_kWh_1s'] = (df['Moc_procent'] / 100.0) * MOC_ZAMIANOWA_GRZALKI_KW * (1.0 / 3600.0)
calkowita_energia_kwh = df['Energia_kWh_1s'].sum()

print("=" * 65)
print("📊       RAPORT STATYSTYCZNY Z PRACY TWOJEGO ALGORYTMU")
print("=" * 65)
print(f"⏱️  Całkowity czas analizy:       {calkowity_czas_s} sek. ({calkowity_czas_s/3600:.2f} godz.)")
print(f"🔥 Czas aktywnego grzania:       {czas_grzania_s} sek. ({czas_grzania_s/3600:.2f} godz.) -> {procent_czasu_grzania:.1f}%")
print(f"⚡ Przyjęta moc znamionowa:       {MOC_ZAMIANOWA_GRZALKI_KW} kW")
print(f"🔋 Szacunkowe zużycie energii:    {calkowita_energia_kwh:.3f} kWh")
print("=" * 65)

# ==============================================================================
# PRZYGOTOWANIE INTERFEJSU GRAFICZNEGO (DARK MODE + SLIDER + SCROLL)
# ==============================================================================
print("\n📈 Uruchamianie zaawansowanego okna wykresu...")

colors = {
    'hrt':     '#e74c3c',  # Czerwony (Szyna grzana)
    'crt':     '#95a5a6',  # Szary (Szyna niegrzana)
    'at':      '#34495e',  # Ciemny szary (Powietrze)
    'moc':     '#f1c40f',  # Żółty (Moc)
    'opad':    '#3498db',  # Niebieski (Opad)
    'snieg':   '#2ecc71',  # Zielony (Śnieg)
    'lod':     '#9b59b6',  # Fioletowy (Lód)
    'bg_dark': '#0a0d14',  # Tło główne
    'bg_axes': '#0f1520',  # Tło wykresów
    'grid':    '#1e2840',  # Kolor siatki
    'text':    '#7a8aaa'   # Kolor czcionek osi
}

fig = plt.figure(figsize=(18, 11))
fig.patch.set_facecolor(colors['bg_dark'])

# Podział okna na 2 główne panele i sekcję sterowania na dole
gs = gridspec.GridSpec(
    2, 1,
    figure=fig,
    left=0.06, right=0.93,
    top=0.94, bottom=0.18,
    hspace=0.12
)

ax1 = fig.add_subplot(gs[0])
ax2 = fig.add_subplot(gs[1], sharex=ax1)

# Formatowanie estetyki paneli
for ax in [ax1, ax2]:
    ax.set_facecolor(colors['bg_axes'])
    ax.tick_params(colors=colors['text'], labelsize=9)
    for sp in ax.spines.values():
        sp.set_edgecolor(colors['grid'])
    ax.grid(True, color=colors['grid'], alpha=0.7, lw=0.5)

fig.suptitle("Interaktywna analiza pracy układu grzewczego szyn", color='#c5cfe8', fontsize=14, fontweight='bold')

# --- Panel 1: Temperatury i Moc (Dwie osie Y) ---
line_hrt, = ax1.plot([], [], color=colors['hrt'], linewidth=2, label='HRT (Szyna Ogrzewana)')
line_crt, = ax1.plot([], [], color=colors['crt'], linestyle='--', linewidth=1.5, label='CRT (Szyna Nieogrzewana)')
line_at,  = ax1.plot([], [], color=colors['at'], linestyle=':', linewidth=1.5, label='AT (Otoczenie)')
ax1.set_ylabel('Temperatura (°C)', color=colors['text'], fontweight='bold')

ax1_moc = ax1.twinx()
ax1_moc.tick_params(colors=colors['moc'], labelsize=9)
ax1_moc.set_ylabel('Wysterowanie mocy grzałki (%)', color=colors['moc'], fontweight='bold')
ax1_moc.set_ylim(-5, 105)
# Dla fill_between zrobimy dynamiczne odświeżanie, więc zachowamy referencję do kolekcji
fill_moc = [None] 

# --- Panel 2: Opady, Śnieg i Lód (Dwie osie Y) ---
line_opad, = ax2.plot([], [], color=colors['opad'], alpha=0.7, label='Intensywność opadów')
ax2.set_ylabel('Bieżący opad (mm/15min)', color=colors['opad'], fontweight='bold')

ax2_stan = ax2.twinx()
ax2_stan.tick_params(colors=colors['snieg'], labelsize=9)
line_snieg, = ax2_stan.plot([], [], color=colors['snieg'], linewidth=2, label='Śnieg na szynie (mm)')
line_lod,   = ax2_stan.plot([], [], color=colors['lod'], linewidth=2, linestyle='-.', label='Lód na szynie (mm)')
ax2_stan.set_ylabel('Grubość warstwy (mm)', color=colors['snieg'], fontweight='bold')

# Legendy
ax1.legend(loc='upper left', fontsize=9, facecolor='#151c2e', labelcolor='white', framealpha=0.8)
ax2.legend(loc='upper right', fontsize=9, facecolor='#151c2e', labelcolor='white', framealpha=0.8)

# ==============================================================================
# KONTROLKI: SUWAK I PRZYCISKI nawigacyjne
# ==============================================================================
t_max = t_sec[-1]
slider_max = max(t_max - WINDOW_SEC, 1.0)

ax_slide = fig.add_axes([0.06, 0.08, 0.75, 0.035])
ax_btn_l = fig.add_axes([0.83, 0.08, 0.04, 0.035])
ax_btn_r = fig.add_axes([0.88, 0.08, 0.04, 0.035])

for ax in [ax_slide, ax_btn_l, ax_btn_r]:
    ax.set_facecolor(colors['bg_dark'])

slider = Slider(
    ax_slide, 'Czas →', 0, slider_max,
    valinit=0, valstep=max(1.0, WINDOW_SEC / 100),
    color='#00e5ff', track_color=colors['grid']
)
slider.label.set_color(colors['text'])
slider.valtext.set_color('#00e5ff')

# ==============================================================================
# FUNKCJA AKTUALIZACJI WYKRESU (DOWN_SAMPLING I FILTRACJA)
# ==============================================================================
def format_axes():
    x0 = int(slider.val)
    x1 = int(x0 + WINDOW_SEC)
    
    # Wycinamy tylko dane widoczne w danym oknie czasowym
    mask = (t_sec >= x0) & (t_sec <= x1)
    df_sub = df.iloc[mask]
    
    if len(df_sub) == 0:
        return

    # KROK WYGŁADZANIA (Agregacja, by pozbyć się szpilek)
    # Jeśli punktów w oknie jest za dużo, uśredniamy je w locie np. co 15 sekund
    step = max(1, len(df_sub) // 600)  # Celujemy w max ~600 punktów na ekranie
    df_resampled = df_sub.iloc[::step]
    
    sub_t = df_resampled['t_sec'].values
    sub_timestamps = timestamps[mask][::step]

    # Aktualizacja danych linii - Panel 1
    line_hrt.set_data(sub_t, df_resampled['HRT_temp_grzana'])
    line_crt.set_data(sub_t, df_resampled['CRT_temp_niegrzana'])
    line_at.set_data(sub_t, df_resampled['AT_temp_powietrza'])
    
    # Aktualizacja fill_between dla mocy
    if fill_moc[0] is not None:
        fill_moc[0].remove()
    fill_moc[0] = ax1_moc.fill_between(sub_t, df_resampled['Moc_procent'], color=colors['moc'], alpha=0.15)

    # Aktualizacja danych linii - Panel 2
    line_opad.set_data(sub_t, df_resampled['PRECIP_opad_1s'] * 900)
    line_snieg.set_data(sub_t, df_resampled['Snieg_na_szynie_mm'])
    line_lod.set_data(sub_t, df_resampled['Lod_na_szynie_mm'])

    # Skalowanie osi Y do aktualnie widocznych danych (żeby wykres "żył")
    ax1.set_xlim(x0, x1)
    try:
        y1_min = min(df_resampled['HRT_temp_grzana'].min(), df_resampled['AT_temp_powietrza'].min()) - 2
        y1_max = max(df_resampled['HRT_temp_grzana'].max(), df_resampled['CRT_temp_niegrzana'].max()) + 2
        ax1.set_ylim(y1_min, y1_max)
        
        y2_max = max(df_resampled['Snieg_na_szynie_mm'].max(), df_resampled['Lod_na_szynie_mm'].max())
        ax2_stan.set_ylim(-0.2, max(y2_max + 0.5, 2.0))
        
        y2_opad_max = (df_resampled['PRECIP_opad_1s'] * 900).max()
        ax2.set_ylim(-0.1, max(y2_opad_max + 0.5, 1.0))
    except ValueError:
        pass # Zabezpieczenie przed pustymi seriami przy krawędziach danych

    # Podpisy dat i godzin na dolnej osi
    ticks = np.linspace(x0, x1, 6)
    ax2.set_xticks(ticks)
    
    i_arr = np.searchsorted(t_sec, ticks)
    i_arr = np.clip(i_arr, 0, len(timestamps) - 1)
    labels = [pd.Timestamp(timestamps[i]).strftime('%d.%m\n%H:%M:%S') for i in i_arr]
    ax2.set_xticklabels(labels, fontsize=8, color=colors['text'])

    fig.canvas.draw_idle()

# Wywołanie przy zmianie suwaka
slider.on_changed(lambda v: format_axes())

# ==============================================================================
# OBSŁUGA PRZYCISKÓW I SCROLLA MYSZY
# ==============================================================================
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

# Inicjalizacja pierwszego widoku
format_axes()

print("💡 WSKAZÓWKA: Przewijaj rolką myszy nad wykresem lub użyj suwaka na dole, aby płynnie przeglądać dane.")
plt.show()