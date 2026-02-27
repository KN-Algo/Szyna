import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def wykresy2(file_path='wyniki_modelu_v4.csv'):
    try:
        #  Wczytanie danych
        df = pd.read_csv(file_path, sep=';')

        y_real = df['y_real']
        y_model = df['y_model']
        error = df['error']
        k = df['probka']

        # Obliczenia statystyczne
        y_mean = np.mean(y_real)
        ss_res = np.sum(error**2)
        ss_tot = np.sum((y_real - y_mean)**2)
        r_squared = 1 - (ss_res / ss_tot)
        rms_error = np.sqrt(np.mean(error**2))

        #  Porównanie Model vs Obiekt 
        plt.figure(figsize=(10, 6))
        plt.plot(k, y_real, 'b-', label='Dane rzeczywiste (Obiekt)', alpha=0.7)
        plt.plot(k, y_model, 'r--', label='Symulacja modelu MNK', linewidth=2)
        plt.title('Zestawienie odpowiedzi modelu i obiektu rzeczywistego')
        plt.xlabel('Numer próbki (k)')
        plt.ylabel('Temperatura [°C]')
        plt.legend()
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.savefig('1_porownanie_modelu.png', dpi=300, bbox_inches='tight')
        plt.close() 

        #  Błędy (Residua) 
        plt.figure(figsize=(10, 5))
        plt.fill_between(k, error, color='gray', alpha=0.3, label='Błąd (y_real - y_model)')
        plt.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        plt.title('Rozkład błędów aproksymacji (Residua)')
        plt.xlabel('Numer próbki (k)')
        plt.ylabel('Wartość błędu')
        plt.legend()
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.savefig('2_wykres_bledow.png', dpi=300, bbox_inches='tight')
        plt.close()

        # Tabela z współczynnikami 
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.axis('off') 

        dane_tabeli = [
            ["Parametr", "Wartość"],
            ["Współczynnik R^2", f"{r_squared:.4f}"],
            ["Błąd RMS", f"{rms_error:.4f}"],
            ["Liczba próbek", f"{len(df)}"]
        ]

        tabela = ax.table(cellText=dane_tabeli, loc='center', cellLoc='center')
        tabela.auto_set_font_size(False)
        tabela.set_fontsize(12)
        tabela.scale(1.2, 2)

        plt.title('Metryki jakości dopasowania modelu', pad=20)
        plt.savefig('3_wspolczynniki_jakosci.png', dpi=300, bbox_inches='tight')
        plt.close()

        print("Wygenerowano 3 osobne pliki PNG:")
        print("- 1_porownanie_modelu.png")
        print("- 2_wykres_bledow.png")
        print("- 3_wspolczynniki_jakosci.png")

    except FileNotFoundError:
        print(f"Błąd: Nie znaleziono pliku '{file_path}'.")
    except Exception as e:
        print(f"Wystąpił błąd: {e}")

if __name__ == "__main__":

    wykresy2()


