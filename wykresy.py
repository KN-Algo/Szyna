import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def wykresy(file_path='wyniki_modelu_v2.csv'):
    try:
        # 1. Wczytanie danych
        df = pd.read_csv(file_path, sep=';')

        # 2. Obliczenie R^2 (Współczynnik determinacji)
        y_real = df['y_real']
        y_model = df['y_model']
        error = df['error']

        y_mean = np.mean(y_real)
        ss_res = np.sum(error**2)
        ss_tot = np.sum((y_real - y_mean)**2)
        r_squared = 1 - (ss_res / ss_tot)

        # 3. Tworzenie wykresów
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))
        plt.subplots_adjust(bottom=0.15) # Zostawienie miejsca na tekst pod wykresem

        # Wykres górny: Real vs Model
        ax1.plot(df['probka'], y_real, 'b-', label='Dane rzeczywiste', alpha=0.7)
        ax1.plot(df['probka'], y_model, 'r--', label='Model MNK')
        ax1.set_title('Porównanie modelu z danymi rzeczywistymi')
        ax1.set_ylabel('Amplituda wyjścia (y)')
        ax1.legend()
        ax1.grid(True, linestyle=':', alpha=0.6)

        # Wykres dolny: Błędy (Residua)
        ax2.fill_between(df['probka'], error, color='gray', alpha=0.3, label='Błąd (y_real - y_model)')
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        ax2.set_title('Wykres błędów aproksymacji (Residua)')
        ax2.set_xlabel('Numer próbki (k)')
        ax2.set_ylabel('Wartość błędu')
        ax2.legend()
        ax2.grid(True, linestyle=':', alpha=0.6)

        # 4. Wypisanie R^2 pod wykresem
        tekst_jakosci = f'Współczynnik dopasowania R^2: {r_squared:.4f}\nBłąd średniokwadratowy (RMS): {np.sqrt(np.mean(error**2)):.4f}'
        plt.figtext(0.5, 0.02, tekst_jakosci, ha="center", fontsize=12,
                    bbox={"facecolor":"orange", "alpha":0.2, "pad":5})

        # 5. Zapis wykresu do pliku
        nazwa_pliku = 'wykres_jakosci_mnk2.png'
        plt.savefig(nazwa_pliku, dpi=300)

        plt.show()
        print(f"Wyliczony współczynnik R^2: {r_squared:.4f}")

    except FileNotFoundError:
        print("Błąd: Nie znaleziono pliku 'wyniki_modelu.csv'.")

if __name__ == "__main__":
    wykresy()