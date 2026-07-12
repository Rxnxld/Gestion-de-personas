# Corrección del estado de cuenta

Se corrigió el cálculo de **Bingo Neto** para evitar que una tabla pendiente se
descuente dos veces.

La fórmula utilizada ahora es:

```text
Bingo Neto = Total acumulado de "Coge c/u" - Tablas pendientes ($1 cada una)
```

Las exclusiones realizadas manualmente desde **Excluir del Reparto** continúan
respetándose. Una tabla marcada como no pagada genera la deuda de $1, pero ya no
elimina también el valor que le corresponde al miembro en el reparto.

Ejemplo verificado:

```text
Coge c/u acumulado: $56.86
Una tabla pendiente: -$1.00
Bingo Neto:          $55.86
```

La misma lógica fue aplicada en la pantalla, el backend y el archivo Excel del
estado de cuenta. También se corrigió el desplazamiento de columnas de ese
reporte Excel.
