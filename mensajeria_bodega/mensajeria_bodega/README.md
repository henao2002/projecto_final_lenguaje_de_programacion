# Sistema de mensajería interna · Centro de distribución

Servidor de chat multihilo para la red local de la bodega: canales por área, mensajes privados, bitácora auditable en disco con carpeta de respaldo, control de disponibilidad por latidos UDP y reporte de operación con programación funcional.

Solo usa **Python 3.10 o superior y su biblioteca estándar**. No hay que instalar nada (mypy es opcional, solo para desarrollo).

## Cómo ejecutarlo

Todo se ejecuta desde **esta carpeta** (la que tiene `mensajeria/` y `datos/`). En Windows cambie `python` por `py`.

**1. Encender el servidor** (una terminal):

```bash
python -m mensajeria.servidor                  # solo este equipo (localhost)
python -m mensajeria.servidor --host 0.0.0.0   # para que entren otros equipos de la red
```

**2. Conectar estaciones** (una terminal por persona, mínimo tres para la demostración):

```bash
python -m mensajeria.cliente ana
python -m mensajeria.cliente luis
python -m mensajeria.cliente sofia
python -m mensajeria.cliente carlos --host 192.168.1.10   # si el servidor está en otro equipo
```

**3. Apagar el servidor:** `Ctrl + C` en su terminal. Espera a que se escriba todo lo pendiente y hace la copia de respaldo.

**4. Sacar el reporte de operación:**

```bash
python -m mensajeria.analisis.reporte                 # sobre datos/mensajes.log
python generar_bitacora.py                            # crea un mes falso (100.000 mensajes)
python -m mensajeria.analisis.reporte datos/mes_prueba.log
```

**5. Correr las pruebas:**

```bash
python prueba_persistencia.py      # 38 comprobaciones; arranca su propio servidor de prueba
mypy mensajeria                    # opcional, si tienen mypy instalado
```

## Comandos del cliente

| Escriba | Qué hace |
| --- | --- |
| `texto normal` | Lo envía al canal actual (al empezar es `#general`) |
| `/unirse #despacho` | Entra a `#recepcion`, `#alistamiento` o `#despacho` |
| `/usar #despacho` | Cambia el canal donde escribe (debe estar unido) |
| `/dejar #despacho` | Sale de un canal (de `#general` no se puede salir) |
| `/privado luis texto` | Mensaje que solo le llega a luis |
| `/conectados` | Quién está, si está activo o inactivo y su última actividad |
| `/pausa` | Detiene los latidos: a los ~15 s aparece como **inactivo** (para la demo) |
| `/ayuda` · `/salir` | Ayuda · desconectarse |

## Estructura

```
mensajeria_bodega/
├── README.md
├── mypy.ini
├── prueba_persistencia.py      # pruebas del Paso 8 + extremo a extremo
├── generar_bitacora.py         # bitácora falsa de un mes para probar el req. 10
├── datos/
│   ├── mensajes.log            # la bitácora (se crea sola al primer mensaje)
│   └── respaldo/               # CARPETA DE RESPALDO: copias automáticas de la bitácora
└── mensajeria/
    ├── protocolo.py            # framing por prefijo de longitud (4 bytes)
    ├── mensaje.py              # Mensaje + a_json / desde_json (puras)
    ├── conectados.py           # quién está, canales, activo/inactivo
    ├── conexion.py             # atiende a un cliente (un hilo por persona); pone emisor y hora
    ├── latidos.py              # recibe latidos UDP (puerto 8001)
    ├── persistencia.py         # se_guarda, escritor con cola, respaldos
    ├── servidor.py             # arranca todo (TCP 8000)
    ├── cliente.py              # programa de cada estación
    └── analisis/
        ├── lectura.py          # Registro, desde_linea, registros (map/filter), leer_mensajes
        ├── metricas.py         # top_emisores, mensajes_por_hora, palabras_frecuentes
        └── reporte.py          # el único que imprime
```

## La carpeta de respaldo

El servidor copia `datos/mensajes.log` a `datos/respaldo/` **al arrancar** y **al apagar**, con la fecha y hora en el nombre (`mensajes_20261020_184207.log`). Se guardan las 20 copias más recientes. Para restaurar: con el servidor apagado, copiar el respaldo elegido sobre `datos/mensajes.log`. Más detalles en `datos/respaldo/LEEME.txt`.

## Paso 0 · Ubicar el borde

| Módulo | Función | ¿Toca archivo, red, pantalla o reloj? | ¿Pura? |
| --- | --- | --- | --- |
| `mensaje.py` | `Mensaje.a_json` | No | Sí |
| `mensaje.py` | `Mensaje.desde_json`, `desde_bytes`, `a_bytes` | No | Sí |
| `protocolo.py` | `empaquetar` | No | Sí |
| `protocolo.py` | `enviar_trama`, `recibir_trama` | Red | No (borde de red) |
| `conexion.py` | `ahora` (la que lee la hora) | Reloj | No |
| `conexion.py` | `sellar` (pone `emisor` y `timestamp`) | No: recibe la hora ya leída | Sí |
| `conectados.py` | `estado`, `describir_conectados`, `nombre_valido` | No | Sí |
| `persistencia.py` | `se_guarda`, `nombre_respaldo`, `respaldos_a_borrar` | No | Sí |
| `persistencia.py` | `escribir` (el escritor) | Archivo | No (borde de escritura) |
| `persistencia.py` | `respaldar` | Archivo | No |
| `analisis/lectura.py` | `desde_linea`, `registros` | No | Sí |
| `analisis/lectura.py` | `leer_mensajes` | Archivo | No (borde de lectura) |
| `analisis/metricas.py` | `top_emisores`, `mensajes_por_hora`, `palabras_frecuentes` | No | Sí |
| `analisis/reporte.py` | `reporte` | Pantalla | No (único que imprime) |
| `cliente.py` | `interpretar`, `formatear` | No | Sí |

## Cómo se cumple cada requerimiento

| Req. | Dónde se resuelve |
| --- | --- |
| 01 Identidad | `conexion._presentarse` + `Directorio.registrar` rechaza nombres repetidos |
| 02 Canal común | `#general`; cada `Sesion` tiene su candado de envío para que los mensajes no se mezclen |
| 03 Varios clientes | Un hilo por cliente; `listen()` sin máximo fijo |
| 04 Tolerancia a fallas | `recibir_trama` devuelve `None` al caerse una estación; su hilo se cierra solo |
| 05 Registro de conectados | `Directorio` con estado y última actividad (`/conectados`) |
| 06 Autoría | `sellar()` en el servidor pisa el emisor y la hora que mande el cliente |
| 07 Bitácora | Cola + un solo escritor no `daemon` + centinela `None` + `fsync` en cada línea |
| 08 Disponibilidad | Latido UDP cada 5 s; más de 15 s sin latido = inactivo |
| 09 Reporte | `analisis/metricas.py` + `analisis/reporte.py` |
| 10 Un mes de datos | Todo perezoso: cada métrica recibe un `leer_mensajes` nuevo, nunca una lista completa |
| 11 Canales | Cuatro canales fijos; `/unirse` y `/dejar` |
| 12 Privados | `tipo: privado` solo llega al `destino` |
| Técnicos | TCP 8000 / UDP 8001, `SO_REUSEADDR`, prefijo de longitud, JSON UTF-8 (nunca pickle), entrada inválida se descarta |

## Tres decisiones de diseño (para la sustentación)

1. **¿Por qué una `Queue` y un solo escritor?** Si cada hilo de cliente abriera el archivo, dos podrían escribir a la vez y mezclar líneas. Con la cola, los hilos solo "dejan" el mensaje y un único hilo lo escribe. La `Queue` ya es segura entre hilos, no necesita candado. El escritor no es `daemon` y termina con el centinela `None`, así que al apagar vacía toda la cola: no se pierde nada.
2. **¿Por qué prefijo de longitud?** TCP es un flujo de bytes: los mensajes pueden llegar pegados o partidos. Con 4 bytes de largo delante, quien recibe sabe exactamente cuánto leer. Además se limita el tamaño (64 KB) para que nadie tumbe el servidor con una trama gigante.
3. **¿Por qué funciones puras en el borde?** Los efectos (archivo, red, pantalla, reloj) viven en pocas funciones; todo lo demás es puro y se prueba con un `assert`, sin servidor, sin archivo y sin hilos. Por eso `registros()` recibe líneas y no una ruta, y por eso la hora se pone una sola vez, al recibir.
