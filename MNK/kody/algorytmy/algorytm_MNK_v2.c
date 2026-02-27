#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>

#define MAX_LINE_LENGTH 1024
#define MAX_ROWS 10000
#define TS 1.0   // Czas próbkowania w sekundach (dane co ~1s)

// Kolumny w krzywa_csv.csv (separator ';'):
// 0:time  1:CRT_name  2:CRT_data  3:CRT_temp
// 4:time  5:HRT_name  6:HRT_data  7:HRT_temp  8:ON/OFF
#define COL_INPUT  8   // ON/OFF (wejście U)
#define COL_OUTPUT 7   // Temperatura HRT (wyjście Y)

void replace_comma_with_dot(char *str) {
    for (int i = 0; str[i]; i++) {
        if (str[i] == ',') str[i] = '.';
    }
}

// Pobierz wartość z kolumny o danym indeksie (separator ';')
double get_column_value(char *line, int col_index) {
    char temp_line[MAX_LINE_LENGTH];
    strncpy(temp_line, line, MAX_LINE_LENGTH - 1);
    temp_line[MAX_LINE_LENGTH - 1] = '\0';

    char *token = strtok(temp_line, ";");
    int current_col = 0;

    while (token != NULL) {
        if (current_col == col_index) {
            replace_comma_with_dot(token);
            // Usuń znaki końca linii
            token[strcspn(token, "\r\n")] = '\0';
            return atof(token);
        }
        token = strtok(NULL, ";");
        current_col++;
    }
    return 0.0;
}

void MNK(double *U, double *Y, int n, double *a_out, double *b_out) {
    printf("\nWczytano %d probek danych.\n", n);
    if (n < 2) {
        printf("Za malo danych do obliczen.\n");
        *a_out = 0.0;
        *b_out = 0.0;
        return;
    }

    double sum_yy = 0.0, sum_yu = 0.0, sum_uu = 0.0;
    double sum_Yy = 0.0, sum_Yu = 0.0;

    // Model: y[k] = a*y[k-1] + b*u[k-1]
    for (int k = 1; k < n; k++) {
        double y_prev = Y[k-1];
        double u_prev = U[k-1];
        double y_curr = Y[k];

        sum_yy += y_prev * y_prev;
        sum_yu += y_prev * u_prev;
        sum_uu += u_prev * u_prev;
        sum_Yy += y_curr * y_prev;
        sum_Yu += y_curr * u_prev;
    }

    double det = sum_yy * sum_uu - sum_yu * sum_yu;

    if (fabs(det) < 1e-9) {
        printf("Blad: Wyznacznik macierzy bliski zeru. Uklad osobliwy.\n");
        *a_out = 0.0;
        *b_out = 0.0;
        return;
    }

    double a = (sum_uu * sum_Yy - sum_yu * sum_Yu) / det;
    double b = (sum_yy * sum_Yu - sum_yu * sum_Yy) / det;

    *a_out = a;
    *b_out = b;

    if (a <= 0.0) {
        printf("BLAD: Parametr 'a' jest ujemny lub zerowy (a = %.6f).\n", a);
    } else if (a >= 1.0) {
        printf("Uwaga: Uklad niestabilny lub calkujacy (a >= 1).\n");
        printf("Parametr a: %.6f\n", a);
        printf("Parametr b: %.6f\n", b);
    } else {
        double K = b / (1.0 - a);
        double T = -TS / log(a);

        printf("\n--- Wyniki MNK ---\n");
        printf("Parametr a:              %.6f\n", a);
        printf("Parametr b:              %.6f\n", b);
        printf("Okres probkowania TS:    %.4f s\n", TS);
        printf("Wzmocnienie statyczne K: %.4f\n", K);
        printf("Stala czasowa T:         %.2f s\n", T);
        printf("Model ciagl.: y(t) = %.4f * (1 - e^(-t / %.2f))\n", K, T);
    }
}

// Generuje plik CSV z porównaniem modelu i danych rzeczywistych
void save_model_comparison(double *U, double *Y, int n, double a, double b, const char *out_file) {
    FILE *f = fopen(out_file, "w");
    if (!f) {
        printf("Blad: Nie mozna zapisac pliku '%s'.\n", out_file);
        return;
    }

    fprintf(f, "probka;y_real;y_model;u_input;error\n");

    double y_model = Y[0]; // Inicjalizacja stanem początkowym
    for (int k = 0; k < n; k++) {
        double y_real = Y[k];
        double err = y_real - y_model;
        fprintf(f, "%d;%.4f;%.4f;%.4f;%.4f\n", k, y_real, y_model, U[k], err);

        // Następny krok modelu
        if (k + 1 < n) {
            y_model = a * y_model + b * U[k];
        }
    }

    fclose(f);
    printf("\nZapisano plik porownania: '%s'\n", out_file);
}

int main() {
    const char *input_file = "krzywa_csv.csv";
    const char *output_file = "wyniki_modelu_v4.csv";

    FILE *file = fopen(input_file, "r");
    if (!file) {
        printf("Blad: Nie mozna otworzyc pliku '%s'.\n", input_file);
        return 1;
    }

    double *U = (double*)malloc(MAX_ROWS * sizeof(double));
    double *Y = (double*)malloc(MAX_ROWS * sizeof(double));
    if (!U || !Y) {
        printf("Blad alokacji pamieci.\n");
        return 1;
    }

    int n = 0;
    char line[MAX_LINE_LENGTH];

    // Pomiń nagłówek
    fgets(line, MAX_LINE_LENGTH, file);

    while (fgets(line, MAX_LINE_LENGTH, file) && n < MAX_ROWS) {
        if (strlen(line) < 5) continue;

        double u_val = get_column_value(line, COL_INPUT);
        double y_val = get_column_value(line, COL_OUTPUT);

        // Pomijaj wiersze z brakującymi danymi
        if (y_val == 0.0 && u_val == 0.0) continue;

        U[n] = u_val;
        Y[n] = y_val;
        n++;
    }
    fclose(file);

    double a = 0.0, b = 0.0;
    MNK(U, Y, n, &a, &b);

    if (a != 0.0 || b != 0.0) {
        save_model_comparison(U, Y, n, a, b, output_file);
    }

    free(U);
    free(Y);
    return 0;
}
