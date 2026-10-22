"""
prueba_persistencia.py · Comprobaciones del proyecto (Paso 8 de la guía y más).

    python prueba_persistencia.py

Cada prueba imprime OK o FALLA. No necesita tener el servidor encendido:
la prueba extremo a extremo arranca su PROPIO servidor en puertos libres y
con una bitácora temporal, así que no toca datos/mensajes.log.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tracemalloc
from datetime import datetime

from mensajeria.analisis.lectura import desde_linea, leer_mensajes, registros
from mensajeria.analisis.metricas import mensajes_por_hora, palabras_frecuentes, top_emisores
from mensajeria.conectados import estado
from mensajeria.mensaje import Mensaje, a_bytes, desde_bytes
from mensajeria.persistencia import respaldos_a_borrar, se_guarda
from mensajeria.protocolo import CABECERA, empaquetar, enviar_trama, recibir_trama
from mensajeria.servidor import Servidor

RESULTADOS: list[bool] = []


def comprobar(nombre: str, condicion: bool) -> None:
    """Muestra el resultado de una prueba y lo anota."""
    RESULTADOS.append(condicion)
    print(f"  [{'OK' if condicion else 'FALLA'}] {nombre}")


# Datos fijos para las pruebas puras (sin red, sin archivo, sin hilos).
HORA = datetime(2026, 10, 20, 18, 42, 7)
MENSAJES = (
    Mensaje("mensaje", "ana", "#general", None, "Pedido 4512 listo en el muelle 3", HORA),
    Mensaje("mensaje", "luis", "#despacho", None, "Falta una caja del pedido 4512", HORA.replace(hour=9)),
    Mensaje("privado", "ana", None, "luis", "¿Revisas el muelle 3? Recepción espera", HORA),
)


def prueba_1_ida_y_vuelta() -> None:
    print("1. Ida y vuelta: desde_linea(mensaje.a_json()) reconstruye los campos")
    for m in MENSAJES:
        r = desde_linea(m.a_json())
        comprobar(f"{m.tipo} de {m.emisor}",
                  r is not None and tuple(r) == (m.tipo, m.emisor, m.canal, m.destino, m.contenido, m.timestamp))
    comprobar("Mensaje.desde_json(a_json()) == original", all(Mensaje.desde_json(m.a_json()) == m for m in MENSAJES))
    comprobar("a_json es pura (dos llamadas, mismo texto)", MENSAJES[0].a_json() == MENSAJES[0].a_json())
    comprobar("una línea por objeto (sin saltos de línea)", all("\n" not in m.a_json() for m in MENSAJES))
    comprobar("las tildes se guardan tal cual (UTF-8)", "Recepción" in MENSAJES[2].a_json())
    comprobar("se_guarda solo mensaje y privado",
              [se_guarda(Mensaje(t)) for t in ("mensaje", "privado", "unirse", "dejar", "error")]
              == [True, True, False, False, False])


def prueba_2_y_3_metricas_puras() -> None:
    print("2-3. Métricas: mismo resultado dos veces y los datos no cambian")
    datos = tuple(registros(m.a_json() for m in MENSAJES))
    antes = datos[:]
    comprobar("top_emisores igual dos veces", top_emisores(datos, 5) == top_emisores(datos, 5))
    comprobar("mensajes_por_hora igual dos veces", mensajes_por_hora(datos) == mensajes_por_hora(datos))
    comprobar("palabras_frecuentes igual dos veces", palabras_frecuentes(datos, 5) == palabras_frecuentes(datos, 5))
    comprobar("los registros no cambiaron", datos == antes)
    comprobar("top_emisores correcto", top_emisores(datos, 5) == [("ana", 2), ("luis", 1)])
    por_hora = mensajes_por_hora(datos)
    comprobar("mensajes_por_hora correcto", por_hora[18] == 2 and por_hora[9] == 1 and sum(por_hora.values()) == 3)
    comprobar("palabras: 'muelle' y 'pedido' arriba", dict(palabras_frecuentes(datos, 3)).get("muelle") == 2)


def prueba_4_lineas_danadas() -> None:
    print("4. Líneas dañadas: se omiten sin excepción")
    buenas = [m.a_json() for m in MENSAJES]
    lineas = buenas[:1] + ["{ roto", '{"tipo": "mensaje"}'] + buenas[1:]
    flujo = registros(lineas)
    comprobar("registros() es perezoso (no es una lista)", not isinstance(flujo, list))
    comprobar("dos líneas rotas -> dos registros menos", len(tuple(flujo)) == len(lineas) - 2)
    malas = ["", "{", "5", "[]", '{"tipo": "x"}', '{"tipo":"mensaje","emisor":"a","contenido":"b","timestamp":"ayer"}']
    comprobar("cada línea mala devuelve None", all(desde_linea(x) is None for x in malas))
    comprobar("Mensaje.desde_json rechaza basura",
              all(Mensaje.desde_json(x) is None for x in ["", "{", "5", "[]", '{"tipo": "hackeo"}', '{"tipo":"mensaje","canal":5}']))
    comprobar("bytes que no son UTF-8 -> None", desde_bytes(b"\xff\xfe\x00") is None)


def prueba_protocolo_y_estado() -> None:
    print("Extra. Framing, disponibilidad y respaldos")
    comprobar("empaquetar pone 4 bytes de largo", empaquetar(b"hola") == CABECERA.pack(4) + b"hola")
    a, b = socket.socketpair()
    try:
        # Dos tramas mandadas de un solo golpe (pegadas) se separan bien.
        a.sendall(empaquetar(b"uno") + empaquetar("dos·ñ".encode()))
        comprobar("tramas pegadas se separan", recibir_trama(b) == b"uno" and recibir_trama(b) == "dos·ñ".encode())
        # Una trama partida en dos pedazos se junta bien.
        trama = empaquetar(b"partida")
        a.sendall(trama[:5])
        time.sleep(0.05)
        a.sendall(trama[5:])
        comprobar("trama partida se reconstruye", recibir_trama(b) == b"partida")
        a.sendall(CABECERA.pack(10) + b"abc")
        a.close()
        comprobar("desconexión a mitad de trama -> None, sin excepción", recibir_trama(b) is None)
    finally:
        b.close()
    comprobar("activo con latido hace 10 s", estado(HORA, HORA.replace(second=17)) == "activo")
    comprobar("inactivo con latido hace 16 s", estado(HORA, HORA.replace(second=23)) == "inactivo")
    nombres = [f"mensajes_2026010{i}_120000.log" for i in range(1, 6)]
    comprobar("respaldos: se borran los más viejos", respaldos_a_borrar(nombres, 3) == nombres[:2])


# ---------------- Prueba 5: extremo a extremo con servidor real ----------------

def puerto_libre(tipo: int) -> int:
    with socket.socket(socket.AF_INET, tipo) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class ClientePrueba:
    """Un cliente mínimo para la prueba (sin pantalla)."""

    def __init__(self, puerto: int, nombre: str) -> None:
        self.sock = socket.create_connection(("127.0.0.1", puerto), timeout=5)
        self.enviar(Mensaje("hola", contenido=nombre))
        self.bienvenida = self.recibir()

    def enviar(self, m: Mensaje) -> None:
        enviar_trama(self.sock, a_bytes(m))

    def recibir(self) -> Mensaje | None:
        trama = recibir_trama(self.sock)
        return desde_bytes(trama) if trama is not None else None

    def recibir_todo(self, segundos: float = 0.5) -> list[Mensaje]:
        """Lee todo lo que llegue durante unos instantes."""
        self.sock.settimeout(segundos)
        llegados: list[Mensaje] = []
        try:
            while (m := self.recibir()) is not None:
                llegados.append(m)
        except OSError:
            pass
        return llegados


def prueba_5_extremo_a_extremo() -> None:
    print("5. Extremo a extremo: 2 clientes, 10 mensajes, un unirse y un error -> 10 líneas")
    carpeta = tempfile.mkdtemp()
    ruta_log = os.path.join(carpeta, "mensajes.log")
    carpeta_respaldo = os.path.join(carpeta, "respaldo")
    puerto_tcp, puerto_udp = puerto_libre(socket.SOCK_STREAM), puerto_libre(socket.SOCK_DGRAM)
    servidor = Servidor("127.0.0.1", puerto_tcp, puerto_udp, ruta_log, carpeta_respaldo)
    servidor.iniciar()
    try:
        ana = ClientePrueba(puerto_tcp, "ana")
        luis = ClientePrueba(puerto_tcp, "luis")
        comprobar("los dos entran", ana.bienvenida is not None and ana.bienvenida.tipo == "bienvenida"
                  and luis.bienvenida is not None and luis.bienvenida.tipo == "bienvenida")
        repetida = ClientePrueba(puerto_tcp, "ana")
        comprobar("no se permiten dos sesiones con el mismo nombre",
                  repetida.bienvenida is not None and repetida.bienvenida.tipo == "error")
        repetida.sock.close()
        ana.recibir_todo(0.3)

        ana.enviar(Mensaje("unirse", canal="#despacho"))                 # no se guarda
        for i in range(5):                                               # 5 mensajes
            ana.enviar(Mensaje("mensaje", canal="#general", contenido=f"general {i}"))
        # Intento de suplantación: ana dice ser luis y manda una hora falsa.
        ana.enviar(Mensaje("mensaje", emisor="luis", canal="#general", contenido="suplantado",
                           timestamp=datetime(2000, 1, 1)))              # 6
        ana.enviar(Mensaje("mensaje", canal="#despacho", contenido="solo despacho"))  # 7
        ana.enviar(Mensaje("privado", destino="luis", contenido="secreto"))           # 8
        luis.enviar(Mensaje("mensaje", canal="#general", contenido="respuesta"))      # 9
        luis.enviar(Mensaje("privado", destino="ana", contenido="ok recibido"))       # 10
        luis.enviar(Mensaje("mensaje", canal="#bodega", contenido="canal que no existe"))  # error
        enviar_trama(luis.sock, b"{esto no es json")                     # trama dañada

        llegan_a_luis = luis.recibir_todo()
        textos_luis = [m.contenido for m in llegan_a_luis if m.tipo in ("mensaje", "privado")]
        comprobar("luis recibe los de #general y su privado", "general 4" in textos_luis and "secreto" in textos_luis)
        comprobar("luis NO recibe #despacho (no es miembro)", "solo despacho" not in textos_luis)
        comprobar("luis recibe 2 errores y la conexión sigue",
                  sum(1 for m in llegan_a_luis if m.tipo == "error") == 2)
        suplantado = next((m for m in llegan_a_luis if m.contenido == "suplantado"), None)
        comprobar("el emisor y la hora los pone el servidor",
                  suplantado is not None and suplantado.emisor == "ana"
                  and suplantado.timestamp is not None and suplantado.timestamp.year > 2000)
        textos_ana = [m.contenido for m in ana.recibir_todo() if m.tipo in ("mensaje", "privado")]
        comprobar("ana recibe solo lo de luis (no su propio eco)", sorted(textos_ana) == ["ok recibido", "respuesta"])
        ana.enviar(Mensaje("conectados"))
        lista = ana.recibir_todo(0.3)
        comprobar("lista de conectados con estado", any("luis" in m.contenido and "activo" in m.contenido for m in lista))
        ana.sock.close()
        luis.sock.close()
        time.sleep(0.2)
    finally:
        servidor.detener()

    with open(ruta_log, encoding="utf-8") as f:
        lineas = sum(1 for _ in f)
    comprobar(f"la bitácora tiene 10 líneas (tiene {lineas})", lineas == 10)
    comprobar("se creó la copia en la carpeta de respaldo", len(os.listdir(carpeta_respaldo)) == 1)
    shutil.rmtree(carpeta, ignore_errors=True)


# ---------------- Extra: memoria del reporte (req. 10) ----------------

def pico_de_memoria(ruta: str) -> int:
    tracemalloc.start()
    top_emisores(leer_mensajes(ruta), 5)
    mensajes_por_hora(leer_mensajes(ruta))
    palabras_frecuentes(leer_mensajes(ruta), 5)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return pico


def prueba_memoria() -> None:
    print("Extra. Req. 10: la memoria no crece con el tamaño de la bitácora")
    from generar_bitacora import generar
    carpeta = tempfile.mkdtemp()
    chica, grande = os.path.join(carpeta, "chica.log"), os.path.join(carpeta, "grande.log")
    generar(5_000, chica)
    generar(50_000, grande)
    pico_chica, pico_grande = pico_de_memoria(chica), pico_de_memoria(grande)
    print(f"     pico con 5.000: {pico_chica / 1024:.0f} KB · pico con 50.000: {pico_grande / 1024:.0f} KB")
    comprobar("10 veces más mensajes NO usan 10 veces más memoria", pico_grande < pico_chica * 2)
    shutil.rmtree(carpeta, ignore_errors=True)


def prueba_6_mypy() -> None:
    print("6. mypy mensajeria sin errores")
    try:
        resultado = subprocess.run([sys.executable, "-m", "mypy", "mensajeria"],
                                   capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
    except OSError:
        print("  [--] no se pudo ejecutar mypy")
        return
    if "No module named mypy" in resultado.stderr:
        print("  [--] mypy no está instalado (pip install mypy, solo en desarrollo). Se omite.")
        return
    print("     " + resultado.stdout.strip().replace("\n", "\n     "))
    comprobar("mypy sin errores", resultado.returncode == 0)


if __name__ == "__main__":
    prueba_1_ida_y_vuelta()
    prueba_2_y_3_metricas_puras()
    prueba_4_lineas_danadas()
    prueba_protocolo_y_estado()
    prueba_5_extremo_a_extremo()
    prueba_memoria()
    prueba_6_mypy()
    print(f"\nResultado: {sum(RESULTADOS)} de {len(RESULTADOS)} comprobaciones OK")
    sys.exit(0 if all(RESULTADOS) else 1)
