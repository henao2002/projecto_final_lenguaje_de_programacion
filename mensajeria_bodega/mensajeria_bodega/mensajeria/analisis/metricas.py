"""
metricas.py · Las tres métricas del reporte (req. 09). TODAS son PURAS:

  - No usan 'global', no abren archivos y no imprimen.
  - Reciben un Iterable de Registros y devuelven un valor.
  - Mismo argumento -> mismo resultado, y NO modifican los registros.

Como reciben un Iterable (no una lista), funcionan igual con una tupla de
prueba o con leer_mensajes(ruta), que va leyendo el archivo de a poco.
"""

import string
from collections import Counter
from collections.abc import Iterable, Iterator
from operator import attrgetter

from mensajeria.analisis.lectura import Registro

# Signos que se quitan antes de contar palabras (incluye los del español).
_SIGNOS = string.punctuation + "¿¡«»“”‘’…"
_QUITAR_SIGNOS = str.maketrans(_SIGNOS, " " * len(_SIGNOS))

# Palabras muy comunes que no dicen nada de la operación ("de", "la", "que"...).
# Sin esto, el top de palabras siempre sería "de", "la", "el".
PALABRAS_VACIAS = frozenset(
    """
    a al algo ante antes como con contra cual cuando de del desde donde e el
    ella ellas ellos en entre era es esa ese eso esta este esto estoy está
    están fue ha hay la las le les lo los mas me mi muy más no nos o otra
    otro para pero por porque que quien qué se sea ser si sin sobre son su
    sus también te tengo tiene todo tu tú un una uno unos unas y ya yo él
    ok listo bien gracias vale hola
    """.split()
)


def top_emisores(registros: Iterable[Registro], n: int) -> list[tuple[str, int]]:
    """
    Quiénes envían más mensajes.
    map + attrgetter("emisor") saca el emisor de cada registro (sin lambda)
    y Counter los cuenta. most_common(n) da los n primeros.
    """
    return Counter(map(attrgetter("emisor"), registros)).most_common(n)


def mensajes_por_hora(registros: Iterable[Registro]) -> dict[int, int]:
    """
    Cuántos mensajes hay en cada hora del día (0 a 23).
    Devuelve las 24 horas, en orden, aunque alguna tenga 0 mensajes.
    """
    conteo = Counter(r.timestamp.hour for r in registros)
    return {hora: conteo.get(hora, 0) for hora in range(24)}


def palabras(texto: str) -> list[str]:
    """PURA: parte un texto en palabras en minúscula, sin signos de puntuación."""
    return texto.lower().translate(_QUITAR_SIGNOS).split()


def _todas_las_palabras(registros: Iterable[Registro]) -> Iterator[str]:
    """
    Comprehension que APLANA: de muchos contenidos a una sola fila de palabras.
    Es un generador (paréntesis): no arma ninguna lista gigante en memoria.
    """
    return (
        palabra
        for r in registros
        for palabra in palabras(r.contenido)
        if len(palabra) > 2 and palabra not in PALABRAS_VACIAS and not palabra.isdigit()
    )


def palabras_frecuentes(registros: Iterable[Registro], n: int) -> list[tuple[str, int]]:
    """Las n palabras que más se repiten en los mensajes."""
    return Counter(_todas_las_palabras(registros)).most_common(n)
