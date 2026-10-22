"""
mensaje.py · Qué es un Mensaje y cómo se convierte a texto JSON y de vuelta.

Todo lo que va y viene entre cliente y servidor es un Mensaje. Lo que cambia
es el "tipo":

  Lo manda el CLIENTE:
    hola        -> "me conecto con este nombre" (el nombre va en contenido)
    mensaje     -> un mensaje a un canal (#general, #despacho, ...)
    privado     -> un mensaje para UNA persona (va en destino)
    unirse      -> entrar a un canal
    dejar       -> salir de un canal
    conectados  -> "¿quién está conectado?"
    salir       -> "me desconecto"

  Lo manda el SERVIDOR:
    bienvenida  -> "entraste bien"
    sistema     -> avisos (alguien entró, saliste de un canal, ...)
    error       -> algo salió mal (canal que no existe, etc.)
    (también reenvía los "mensaje" y "privado" ya sellados)

  Por UDP (puerto 8001):
    latido      -> "sigo vivo" (lo manda cada estación cada 5 segundos)

IMPORTANTE (seguridad): usamos JSON y NUNCA pickle. pickle puede ejecutar
código al leer datos, y por la red cualquiera nos puede mandar bytes.
"""

import json
from datetime import datetime
from typing import NamedTuple

# frozenset = conjunto que NO se puede modificar. Es una constante, no un
# "estado global": nadie lo puede cambiar mientras corre el programa.
TIPOS_VALIDOS = frozenset(
    {
        "hola", "bienvenida", "mensaje", "privado", "unirse", "dejar",
        "conectados", "sistema", "error", "salir", "latido",
    }
)

# Límite de caracteres de un mensaje, para que nadie llene la bitácora de basura.
MAX_CONTENIDO = 2000


class Mensaje(NamedTuple):
    """
    Un mensaje del chat. Es un NamedTuple: una tupla con nombres de campo.
    Es INMUTABLE: una vez creado no se puede cambiar. Para "cambiarlo" se usa
    m._replace(campo=valor), que devuelve OTRO mensaje y deja el original igual.
    """

    tipo: str
    emisor: str | None = None          # lo pone SIEMPRE el servidor, nunca el cliente
    canal: str | None = None           # solo para tipo "mensaje", "unirse", "dejar"
    destino: str | None = None         # solo para tipo "privado"
    contenido: str = ""
    timestamp: datetime | None = None  # lo pone SIEMPRE el servidor, al recibir

    def a_json(self) -> str:
        """
        PURA: convierte el mensaje en UNA línea de texto JSON.
        No abre archivos, no imprime y NO lee el reloj: la hora ya viene
        dentro del mensaje. Por eso, mismo mensaje -> misma línea, siempre.
        """
        return json.dumps(
            {
                "tipo": self.tipo,
                "emisor": self.emisor,
                "canal": self.canal,
                "destino": self.destino,
                "contenido": self.contenido,
                "timestamp": (
                    self.timestamp.isoformat(timespec="seconds")
                    if self.timestamp is not None
                    else None
                ),
            },
            ensure_ascii=False,  # para que "recepción" se guarde con su tilde
        )

    @staticmethod
    def desde_json(texto: str) -> "Mensaje | None":
        """
        PURA: convierte un texto JSON en Mensaje.
        Si el texto viene dañado o con datos raros devuelve None (NO lanza
        error y NO imprime). Quien la llama decide qué hacer con el None.
        Recordemos: lo que llega de la red NO es confiable.
        """
        try:
            datos = json.loads(texto)
            if not isinstance(datos, dict):       # "5" o "[]" no son mensajes
                return None

            tipo = datos["tipo"]
            if tipo not in TIPOS_VALIDOS:
                return None

            # Los campos opcionales deben ser texto o no venir (None).
            emisor = _texto_o_nada(datos.get("emisor"))
            canal = _texto_o_nada(datos.get("canal"))
            destino = _texto_o_nada(datos.get("destino"))

            contenido = datos.get("contenido", "")
            if not isinstance(contenido, str) or len(contenido) > MAX_CONTENIDO:
                return None

            hora = datos.get("timestamp")
            timestamp = datetime.fromisoformat(hora) if isinstance(hora, str) else None

            return Mensaje(tipo, emisor, canal, destino, contenido, timestamp)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None


def _texto_o_nada(valor: object) -> str | None:
    """PURA: deja pasar un texto o None; cualquier otra cosa es un error de datos."""
    if valor is None or isinstance(valor, str):
        return valor
    raise TypeError("se esperaba texto")


def desde_bytes(datos: bytes) -> Mensaje | None:
    """PURA: de bytes recibidos por la red a Mensaje (o None si vienen dañados)."""
    try:
        return Mensaje.desde_json(datos.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def a_bytes(mensaje: Mensaje) -> bytes:
    """PURA: de Mensaje a bytes UTF-8 listos para mandar por la red."""
    return mensaje.a_json().encode("utf-8")
