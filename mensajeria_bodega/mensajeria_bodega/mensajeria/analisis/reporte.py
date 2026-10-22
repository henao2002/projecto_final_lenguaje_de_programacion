"""
reporte.py · El reporte de operación. Es el ÚNICO que imprime.

Cómo se ejecuta (desde la carpeta raíz del proyecto):

    python -m mensajeria.analisis.reporte                       # usa datos/mensajes.log
    python -m mensajeria.analisis.reporte datos/mes_prueba.log  # otra bitácora
    python -m mensajeria.analisis.reporte --top 10

Este módulo NO calcula nada: abre la bitácora (con leer_mensajes), le pasa
los registros a las métricas puras y muestra lo que devuelven.

MEMORIA (req. 10): NO hacemos tuple(...) ni list(...) de toda la bitácora.
Cada métrica recibe un leer_mensajes(ruta) NUEVO, que lee el archivo de a
una línea. Leemos el archivo varias veces, pero la memoria no crece con el
tamaño de la bitácora: 1.000 o 100.000 mensajes ocupan casi lo mismo.
"""

import argparse

from mensajeria import RUTA_LOG
from mensajeria.analisis.lectura import leer_mensajes
from mensajeria.analisis.metricas import mensajes_por_hora, palabras_frecuentes, top_emisores

ANCHO_BARRA = 40


def barra(valor: int, maximo: int) -> str:
    """PURA: una barrita de texto proporcional al valor."""
    if maximo == 0:
        return ""
    return "█" * max(1 if valor else 0, round(valor * ANCHO_BARRA / maximo))


def reporte(ruta: str, n: int = 5) -> None:
    """Calcula (con funciones puras) e imprime (aquí, en el borde) el reporte."""
    total = sum(1 for _ in leer_mensajes(ruta))
    print("=" * 60)
    print(" REPORTE DE OPERACIÓN · Centro de distribución")
    print("=" * 60)
    print(f"Bitácora: {ruta}")
    print(f"Mensajes válidos: {total}")
    if total == 0:
        print("\nTodavía no hay mensajes en la bitácora.")
        return

    print(f"\n1) Quiénes envían más mensajes (top {n})")
    for puesto, (emisor, cantidad) in enumerate(top_emisores(leer_mensajes(ruta), n), start=1):
        print(f"   {puesto}. {emisor:<16} {cantidad:>7} mensajes")

    print("\n2) Mensajes por hora del día")
    por_hora = mensajes_por_hora(leer_mensajes(ruta))
    maximo = max(por_hora.values())
    for hora, cantidad in por_hora.items():
        if cantidad:
            print(f"   {hora:02d}:00  {cantidad:>7}  {barra(cantidad, maximo)}")
    hora_pico = max(por_hora, key=lambda h: por_hora[h])
    print(f"   Hora pico: {hora_pico:02d}:00 ({por_hora[hora_pico]} mensajes)")

    print(f"\n3) Palabras que más se repiten (top {n})")
    for puesto, (palabra, cantidad) in enumerate(palabras_frecuentes(leer_mensajes(ruta), n), start=1):
        print(f"   {puesto}. {palabra:<16} {cantidad:>7} veces")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reporte de operación sobre la bitácora")
    parser.add_argument("ruta", nargs="?", default=str(RUTA_LOG), help="archivo de bitácora")
    parser.add_argument("--top", type=int, default=5, help="cuántos mostrar en cada top")
    args = parser.parse_args()
    reporte(args.ruta, args.top)


if __name__ == "__main__":
    main()
