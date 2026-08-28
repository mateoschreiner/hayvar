# -*- coding: utf-8 -*-
"""
El historial entre dos clubes, leído de zerozero.

Por qué esta fuente
───────────────────
La que usa el resto del sitio devuelve **quince cruces y nada más**, y no
hay forma de pedir más: se probaron nueve parámetros distintos. Para
Boca-River eso son cinco años. Acá son **137, desde 1955**.

No es todo —el Superclásico tiene unos 266 partidos oficiales y acá está
la mitad moderna, porque no hay nada anterior a 1955— así que el total
histórico sigue viniendo de `historiales.py`, cargado a mano. Esto es la
lista, no el número.

Cómo se pide
────────────
La dirección se arma con dos números y nada más:

    /estadisticas/<lo-que-sea>/t<idA>-t<idB>

El texto del medio es cosmético y el orden de los ids da igual. Lo que no
se puede omitir es ese segmento: sin él la dirección cae en otra página.

La tabla muestra **veinte filas por pedido**, siempre las más recientes.
Para bajar las 137 hay que recorrer por temporada con `epoca_ini` y
`epoca_fim`, que **no son años sino índices**: el índice de un año es el
año menos 1871. Trece pedidos por cruce.

Cómo se lee
───────────
Es HTML plano, servido armado. No hace falta un navegador ni ejecutar
javascript: la tabla ya viene en la respuesta. Se lee con el parser de la
biblioteca estándar, como el resto del sitio.

Sobre pedir con cuidado
───────────────────────
El `robots.txt` no prohíbe esta sección ni pide una demora, pero es un
sitio chico y trece pedidos por cruce se acumulan. Por eso: los pares se
bajan de a uno, con una pausa entre pedidos, en segundo plano, y lo que se
baja **no se vuelve a pedir nunca** —un cruce de 1978 no cambia—. Sólo se
refresca el tramo del año en curso.
"""

import re
import time
from html.parser import HTMLParser

SITIO = "https://www.zerozero.com.ar"

# El índice de temporada que usa el sitio: 1 es 1872.
_ANO_CERO = 1871

# Pausa entre pedidos. No la pide el robots.txt; la ponemos igual.
PAUSA = 1.5


def indice_de_ano(ano):
    return max(1, int(ano) - _ANO_CERO)


def url_historial(ida, idb, desde=None, hasta=None):
    """
    La dirección del historial entre dos clubes.

    El segmento del medio es cosmético pero obligatorio: sin él la
    dirección cae en otra página del sitio.
    """
    u = "%s/estadisticas/h2h/t%s-t%s" % (SITIO, ida, idb)
    if desde or hasta:
        u += "?epoca_ini=%d&epoca_fim=%d" % (
            indice_de_ano(desde or 1955), indice_de_ano(hasta or 2030))
    return u


class _Tabla(HTMLParser):
    """
    Saca las filas de la tabla de partidos.

    No busca una tabla por su clase sino **filas que tengan la forma de un
    partido**: una fecha ISO, un marcador y dos nombres. Es más robusto
    que atarse a `class="zztable stats"`, que es una decisión de diseño de
    ellos y puede cambiar cualquier día sin avisar.
    """

    def __init__(self):
        HTMLParser.__init__(self)
        self.filas = []
        self._fila = None
        self._celda = None
        self._enlace = None

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        if tag == "tr":
            self._fila = []
        elif tag == "td" and self._fila is not None:
            self._celda = {"texto": "", "clase": at.get("class") or "",
                           "enlace": ""}
        elif tag == "a" and self._celda is not None:
            self._celda["enlace"] = self._celda["enlace"] or at.get("href") or ""

    def handle_data(self, data):
        if self._celda is not None:
            self._celda["texto"] += data

    def handle_endtag(self, tag):
        if tag == "td" and self._celda is not None and self._fila is not None:
            self._celda["texto"] = re.sub(r"\s+", " ",
                                          self._celda["texto"]).strip()
            self._fila.append(self._celda)
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            if len(self._fila) >= 5:
                self.filas.append(self._fila)
            self._fila = None


FECHA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
MARCADOR = re.compile(r"^(\d+)\s*-\s*(\d+)")
ID_PARTIDO = re.compile(r"/partido/[^/]+/(\d+)")


def leer_html(html):
    """
    Los partidos que haya en esta página.

    Devuelve una lista de dicts con lo que sirve: día, local, visitante,
    goles y competencia. Lo que no se entiende se saltea en silencio: una
    fila rota no puede tirar el resto de la tabla.
    """
    t = _Tabla()
    try:
        t.feed(html)
    except Exception:
        pass
    salida = []
    for fila in t.filas:
        dia = mar = None
        idx = None
        for i, c in enumerate(fila):
            if dia is None and FECHA.match(c["texto"]):
                dia = c["texto"]
            m = MARCADOR.match(c["texto"])
            if mar is None and m and "result" in c["clase"]:
                mar = (int(m.group(1)), int(m.group(2)))
                idx = i
                mp = ID_PARTIDO.search(c["enlace"] or "")
                fila_id = mp.group(1) if mp else None
        if not dia or not mar or idx is None:
            continue
        # El local está a la izquierda del marcador y el visitante a la
        # derecha. Es la posición y no la clase lo que lo define, así que
        # se toman los vecinos.
        izq = [c for c in fila[:idx] if c["texto"] and not FECHA.match(c["texto"])
               and len(c["texto"]) > 2]
        der = [c for c in fila[idx + 1:] if c["texto"] and len(c["texto"]) > 2]
        if not izq or not der:
            continue
        # La competencia es la última celda con texto largo.
        comp = der[-1]["texto"] if len(der) > 1 else ""
        salida.append({
            "id": fila_id,
            "dia": dia,
            "local": izq[-1]["texto"],
            "visita": der[0]["texto"],
            "gh": mar[0], "ga": mar[1],
            "torneo": comp if comp != der[0]["texto"] else "",
        })
    return salida


def paginas(ida, idb, desde=1950, hasta=2030, tramo=6):
    """
    Las direcciones a recorrer para bajar un cruce entero.

    Van de a seis temporadas porque la tabla muestra veinte filas: dos
    equipos que se cruzan cuatro veces por año entran justos, y con tramos
    más largos se perderían partidos sin que nadie se entere.
    """
    us = []
    a = desde
    while a <= hasta:
        us.append(url_historial(ida, idb, a, min(a + tramo - 1, hasta)))
        a += tramo
    return us


# Cuántas filas muestra la tabla como máximo. Está medido contra el sitio,
# no supuesto: Boca-River, Independiente-Racing y el rosarino devuelven
# exactamente veinte sin parámetros, y Argentinos-Aldosivi devuelve
# dieciséis, que son todos los que hay. Veinte es el tope.
TOPE = 20


def bajar(traer, ida, idb, desde=1950, hasta=2030, pausa=PAUSA):
    """
    Todos los cruces entre dos clubes.

    Devuelve `(partidos, páginas_pedidas, fallos)`. Los dos últimos son
    para el diario: sin ellos, "no vinieron partidos" no distingue entre
    una red que no responde y un lector que no entiende la página, que se
    arreglan en lugares opuestos.

    `traer` es la función que hace el pedido y devuelve el HTML. Se pasa
    de afuera para que este módulo no sepa nada de red: así se puede
    probar entero sin tocar internet, que es lo que hacen las pruebas.

    Primero se pide la página sin acotar, que trae el historial entero si
    entra en veinte filas. La mayoría de los cruces entran, y ahí es UN
    pedido en vez de catorce. Recién si vuelve llena se recorre por
    tramos, porque una tabla en el tope está diciendo que hay más y no
    que hay veinte.

    Los partidos se juntan por su identificador; los que no lo traen, por
    día y marcador. Sin eso, los tramos que se superponen guardarían el
    mismo partido dos veces.
    """
    vistos = {}
    fallos = []
    pedidas = 0

    def pedir(u):
        nonlocal pedidas
        pedidas += 1
        try:
            html = traer(u)
        except Exception as e:
            fallos.append("%s: %s" % (type(e).__name__, e))
            return 0
        if not html:
            fallos.append("respuesta vacía")
            return 0
        cuantos = 0
        for m in leer_html(html):
            clave = m["id"] or "%s|%s-%s|%s" % (m["dia"], m["gh"], m["ga"],
                                                m["local"])
            vistos.setdefault(clave, m)
            cuantos += 1
        return cuantos

    if pedir(url_historial(ida, idb)) < TOPE and vistos:
        return (sorted(vistos.values(), key=lambda m: m["dia"], reverse=True),
                pedidas, fallos)

    for i, u in enumerate(paginas(ida, idb, desde, hasta)):
        if pausa:
            time.sleep(pausa)
        pedir(u)
    return (sorted(vistos.values(), key=lambda m: m["dia"], reverse=True),
            pedidas, fallos)
