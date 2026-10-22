"""
protocolo.py · Cómo viajan los mensajes por la red (TCP).

EL PROBLEMA: TCP es un "chorro" de bytes, no de mensajes. Si un cliente
manda "hola" y luego "chao", el otro lado puede recibir "holach" + "ao"
(pegados o partidos), sobre todo cuando hay mucho tráfico.

LA SOLUCIÓN (framing por prefijo de longitud): antes de cada mensaje
mandamos 4 bytes que dicen cuánto mide. Así quien recibe sabe exactamente
cuántos bytes leer, ni uno más ni uno menos.

    [ 4 bytes: largo ][ ...el mensaje en JSON (UTF-8)... ]

TODO lo que se manda por TCP en este proyecto pasa por aquí, sin excepción.
"""

import socket
import struct

# "!I" = un entero sin signo de 4 bytes, en orden de red (big-endian).
CABECERA = struct.Struct("!I")

# Tamaño máximo que aceptamos: 64 KB. Si alguien en la red dice que nos va
# a mandar 2 GB, no le creemos: cortamos esa conexión y el servidor sigue.
MAX_TRAMA = 64 * 1024


def empaquetar(datos: bytes) -> bytes:
    """PURA: pega el largo (4 bytes) delante de los datos."""
    return CABECERA.pack(len(datos)) + datos


def enviar_trama(sock: socket.socket, datos: bytes) -> None:
    """Manda una trama completa. sendall() insiste hasta mandar todos los bytes."""
    sock.sendall(empaquetar(datos))


def recibir_exacto(sock: socket.socket, cantidad: int) -> bytes | None:
    """
    Lee EXACTAMENTE 'cantidad' bytes.

    recv() puede devolver menos de lo que se pidió, por eso se repite en un
    ciclo hasta completar. Devuelve None si el otro lado se desconectó,
    aunque sea a mitad de una trama.
    """
    partes: list[bytes] = []
    faltan = cantidad
    while faltan > 0:
        try:
            trozo = sock.recv(faltan)
        except OSError:          # se cayó la red, se reinició la conexión, etc.
            return None
        if not trozo:            # b"" significa: el otro lado cerró la conexión
            return None
        partes.append(trozo)
        faltan -= len(trozo)
    return b"".join(partes)


def recibir_trama(sock: socket.socket) -> bytes | None:
    """
    Recibe UNA trama completa y devuelve solo el contenido (sin la cabecera).

    Devuelve None si el otro lado se desconectó o si la trama es más grande
    de lo permitido. Nunca lanza excepción: un cliente malo no tumba al servidor.
    """
    cabecera = recibir_exacto(sock, CABECERA.size)
    if cabecera is None:
        return None
    (largo,) = CABECERA.unpack(cabecera)
    if largo > MAX_TRAMA:
        return None
    if largo == 0:
        return b""
    return recibir_exacto(sock, largo)
