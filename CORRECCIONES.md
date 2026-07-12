# Corrección del estado de cuenta

Se corrigió el cálculo de **Bingo Neto** para que coincida con la suma exacta de
la columna **Coge c/u**.

La fórmula utilizada ahora es:

```text
Bingo Neto = Suma exacta de todos los valores "Coge c/u"
```

Las divisiones de cada bingo se suman con todos sus decimales y solamente se
redondea el resultado final. Las exclusiones realizadas manualmente desde
**Excluir del Reparto** continúan respetándose. Las tablas pendientes aparecen
como información separada, pero no reducen el Bingo Neto.

Ejemplo verificado:

```text
Coge c/u acumulado exacto: $55.861928...
Bingo Neto redondeado:      $55.86
Tabla pendiente:            1 (informativa)
```

La misma lógica fue aplicada en la pantalla, el backend y el archivo Excel del
estado de cuenta. También se corrigió el desplazamiento de columnas de ese
reporte Excel.
