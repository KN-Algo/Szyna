#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>

#define MAX_LINE_LENGTH 1024
#define MAX_ROWS 5000     
#define TS 225.0         // Czas próbkowania w sekundach

#define COL_INPUT 4 // indeks kolumny z danymi wejściowymi 
#define COL_OUTPUT 8 //indeks kolumny z danymi wyjściowymi (8 dla starych danych, 3 dla nowych)

    double sum_yy = 0.0; // Suma y[k-1]^2
    double sum_yu = 0.0; // Suma y[k-1]*u[k-1]
    double sum_uu = 0.0; // Suma u[k-1]^2
    double sum_Yy = 0.0; // Suma y[k]*y[k-1] (część wektora prawej strony)
    double sum_Yu = 0.0; // Suma y[k]*u[k-1] (część wektora prawej strony)


void replace_comma_with_dot(char *str) {
    for (int i = 0; str[i]; i++) {
        if (str[i] == ',') {
            str[i] = '.';
        }
    }
}

double get_column_value(char *line, int col_index) {
    char *token;
    char temp_line[MAX_LINE_LENGTH];
    strcpy(temp_line, line);

    token = strtok(temp_line, "\t");
    int current_col = 0;

    while (token != NULL) {
        if (current_col == col_index) {
            replace_comma_with_dot(token);
            return atof(token);
        }
        token = strtok(NULL, "\t");
        current_col++;
    }
    return 0.0;
}

void MNK(double *U, double *Y, int n) {
    printf("\nWczytano %d probek danych.\n", n);
    if (n<2) {
        printf("Za malo danych do obliczen.\n");
        return;
    }
    sum_uu = 0.0;
    sum_yy = 0.0; 
    sum_yu = 0.0;
    sum_Yy = 0.0; 
    sum_Yu = 0.0;
    
    // Model: y[k] = a*y[k-1] + b*u[k-1]
    for (int k = 1; k < n; k++) {
        double y_prev = Y[k-1];
        double u_prev = U[k-1];
        double y_curr = Y[k];

        // Elementy macierzy A
        sum_yy += y_prev * y_prev;
        sum_yu += y_prev * u_prev;
        sum_uu += u_prev * u_prev;

        // Elementy wektora B
        sum_Yy += y_curr * y_prev;
        sum_Yu += y_curr * u_prev;
    }

    double det = sum_yy * sum_uu - sum_yu * sum_yu;

    if (fabs(det) < 1e-9) {
        printf("Blad: Wyznacznik macierzy bliski zeru. Uklad osobliwy.\n");
        return;
    }

    double a = (sum_uu * sum_Yy - sum_yu * sum_Yu) / det;
    double b = (sum_yy * sum_Yu - sum_yu * sum_Yy) / det;

   // printf("\n--- Wyniki modelu dyskretnego ---\n");
   // printf("Parametr a: %.6f\n", a);
   // printf("Parametr b: %.6f\n", b);
    
    double K = 0.0;
    double T = 0.0;

    if (a <= 0.0) {
        printf("BLAD: Parametr 'a' jest ujemny lub zerowy (a = %.6f).\n", a);
    } else if (a >= 1.0) {
        printf("Uwaga: Uklad niestabilny lub calkujacy (a >= 1).\n");
        K = b / (1.0 - a);
        T = -TS / log(a);
    } else {
        K = b / (1.0 - a);
        T = -TS / log(a);
        
        printf("\n--- Wyniki ---\n");
        printf("Okres próbkowania TS: %.4f\n", TS);
        printf("Wzmocnienie statyczne K: %.4f\n", K);
        printf("Stala czasowa T: %.2f s\n", T);
        printf("y(t) = %.4f * (1 - e^(-t / %.2f))\n", K, T);
    }
    
    // Zwolnienie pamięci
    free(U);
    free(Y);

}


int main() {
    FILE *file = fopen("pliktxt_filtr.txt", "r");
    if (!file) {
        printf("Blad: Nie mozna otworzyc pliku 'pliktxt_filtr.txt'.\n");
        return 1;
    }

    // Tablice na dane
    double *U = (double*)malloc(MAX_ROWS * sizeof(double)); // Wejście
    double *Y = (double*)malloc(MAX_ROWS * sizeof(double)); // Wyjście
    int n = 0; // Licznik próbek
    bool ilosc_probek = true;

    char line[MAX_LINE_LENGTH];

   // fgets(line, MAX_LINE_LENGTH, file);

    while (fgets(line, MAX_LINE_LENGTH, file) && n < MAX_ROWS) {
        if (strlen(line) < 5) continue;

        if (line[0]=='-')
        {
            ilosc_probek=false;
    
            MNK(U, Y, n);

                double *U = (double*)malloc(MAX_ROWS * sizeof(double)); // Wejście
                double *Y = (double*)malloc(MAX_ROWS * sizeof(double)); // Wyjście

                n = 0; // Licznik próbek
        }
        
        if(ilosc_probek==false)
        {
            fgets(line, MAX_LINE_LENGTH, file);
            U[n] = get_column_value(line, COL_INPUT);
            //printf("U[%d] = %.4f\n", n, U[n]);
            Y[n] = get_column_value(line, COL_OUTPUT);
            //printf("Y[%d] = %.4f\n", n, Y[n]);
            n++;
            ilosc_probek=true;
        } 
        else{
            U[n] = get_column_value(line, COL_INPUT);
            //printf("U[%d] = %.4f\n", n, U[n]);
            Y[n] = get_column_value(line, COL_OUTPUT);
            //printf("Y[%d] = %.4f\n", n, Y[n]);
            n++;
        }
        
    }
    MNK(U, Y, n);
    fclose(file);

    return 0;
}
