"""
conectados.py · Quién está conectado, en qué canales y si está activo.

Resuelve:
  - Req. 01: no puede haber dos sesiones con el mismo nombre.
  - Req. 05: el servidor sabe quién está, su estado y su última actividad.
  - Req. 08: quien lleve más de 15 s sin mandar latido aparece "inactivo".
  - Req. 11: los cuatro canales fijos y quién es miembro de cada uno.

Como muchos hilos (uno por cliente) leen y cambian esta información al mismo
tiempo, todo se protege con un candado (threading.Lock). Solo un hilo a la
vez puede tocar el diccionario de sesiones.
"""

import socket
import threading
from datetime import datetime, timedelta
from typing import NamedTuple

from mensajeria.mensaje import Mensaje, a_bytes
from mensajeria.protocolo import enviar_trama

# Los cuatro canales fijos del centro de distribución (req. 11).
CANAL_GENERAL = "#general"
CANALES = ("#general", "#recepcion", "#alistamiento", "#despacho")

# Si pasan más de 15 segundos sin latido, la persona queda "inactiva" (req. 08).
LIMITE_INACTIVO = timedelta(seconds=15)


class Sesion:
    """Todo lo que el servidor sabe de UNA persona conectada."""

    def __init__(
        self,
        nombre: str,
        sock: socket.socket,
        ip: str,
        ultimo_latido: datetime,
        ultima_actividad: datetime,
    ) -> None:
        self.nombre = nombre
        self.sock = sock
        self.ip = ip                                # para validar que el latido UDP es suyo
        self.ultimo_latido = ultimo_latido          # último "sigo vivo" por UDP
        self.ultima_actividad = ultima_actividad    # último mensaje que mandó por TCP
        self.canales: set[str] = {CANAL_GENERAL}    # todos empiezan en #general
        # Candado propio para ENVIAR: si dos hilos le escriben a la misma persona
        # al mismo tiempo, los mensajes salen uno detrás del otro, sin mezclarse.
        self.candado_envio = threading.Lock()

    def enviar(self, mensaje: Mensaje) -> bool:
        """Le manda un mensaje a esta persona. Devuelve False si ya no está."""
        try:
            with self.candado_envio:
                enviar_trama(self.sock, a_bytes(mensaje))
            return True
        except OSError:
            # La estación se apagó o perdió la red. No pasa nada: su propio
            # hilo se dará cuenta y la sacará de la lista (req. 04).
            return False


class FotoSesion(NamedTuple):
    """Copia de solo lectura de una sesión, para mostrar o calcular sin candado."""

    nombre: str
    ultimo_latido: datetime
    ultima_actividad: datetime
    canales: tuple[str, ...]


# ---------- Funciones PURAS (no tocan red, ni archivos, ni el reloj) ----------

def estado(ultimo_latido: datetime, ahora: datetime) -> str:
    """PURA: 'activo' si mandó latido en los últimos 15 s; si no, 'inactivo'."""
    return "activo" if ahora - ultimo_latido <= LIMITE_INACTIVO else "inactivo"


def describir_conectados(fotos: list[FotoSesion], ahora: datetime) -> str:
    """PURA: arma el texto de la lista de conectados que ve el usuario."""
    lineas = [
        f"  {f.nombre:<14} {estado(f.ultimo_latido, ahora):<9} "
        f"última actividad {f.ultima_actividad:%H:%M:%S}  "
        f"canales: {' '.join(sorted(f.canales))}"
        for f in sorted(fotos, key=lambda f: f.nombre)
    ]
    return f"Conectados ({len(fotos)}):\n" + "\n".join(lineas)


def nombre_valido(nombre: str) -> bool:
    """PURA: un nombre de 2 a 20 letras, números, '_' o '-' (se permiten tildes)."""
    return (
        2 <= len(nombre) <= 20
        and all(c.isalnum() or c in "_-" for c in nombre)
        and nombre.lower() != "servidor"
    )


# ---------- El directorio compartido entre hilos ----------

class Directorio:
    """La lista de personas conectadas, protegida con un candado."""

    def __init__(self) -> None:
        self._sesiones: dict[str, Sesion] = {}
        self._candado = threading.Lock()

    def registrar(self, sesion: Sesion) -> bool:
        """Agrega a alguien. Devuelve False si ese nombre ya está conectado (req. 01)."""
        with self._candado:
            if sesion.nombre in self._sesiones:
                return False
            self._sesiones[sesion.nombre] = sesion
            return True

    def quitar(self, nombre: str) -> None:
        with self._candado:
            self._sesiones.pop(nombre, None)

    def obtener(self, nombre: str) -> Sesion | None:
        with self._candado:
            return self._sesiones.get(nombre)

    def todas(self) -> list[Sesion]:
        with self._candado:
            return list(self._sesiones.values())

    def miembros(self, canal: str) -> list[Sesion]:
        """Las sesiones que están en un canal (req. 11)."""
        with self._candado:
            return [s for s in self._sesiones.values() if canal in s.canales]

    def unirse(self, nombre: str, canal: str) -> None:
        with self._candado:
            sesion = self._sesiones.get(nombre)
            if sesion is not None:
                sesion.canales.add(canal)

    def dejar(self, nombre: str, canal: str) -> None:
        with self._candado:
            sesion = self._sesiones.get(nombre)
            if sesion is not None:
                sesion.canales.discard(canal)

    def canales_de(self, nombre: str) -> set[str]:
        with self._candado:
            sesion = self._sesiones.get(nombre)
            return set(sesion.canales) if sesion is not None else set()

    def marcar_actividad(self, nombre: str, ahora: datetime) -> None:
        """Anota la última vez que la persona mandó algo por TCP."""
        with self._candado:
            sesion = self._sesiones.get(nombre)
            if sesion is not None:
                sesion.ultima_actividad = ahora

    def latido(self, nombre: str, ip: str, ahora: datetime) -> bool:
        """
        Anota un latido UDP. Solo se acepta si el nombre está conectado y el
        latido viene de la MISMA IP de su conexión TCP (para que otro equipo
        no pueda hacerse pasar por él). Devuelve True si se aceptó.
        """
        with self._candado:
            sesion = self._sesiones.get(nombre)
            if sesion is None or sesion.ip != ip:
                return False
            sesion.ultimo_latido = ahora
            return True

    def fotos(self) -> list[FotoSesion]:
        """Una copia de cómo está todo en este momento (para listar sin candado)."""
        with self._candado:
            return [
                FotoSesion(s.nombre, s.ultimo_latido, s.ultima_actividad, tuple(s.canales))
                for s in self._sesiones.values()
            ]
