# -*- coding: utf-8 -*-
"""
El historial completo entre dos clubes, cargado a mano.

Por qué existe
──────────────
La fuente que usa el sitio devuelve **quince cruces y nada más**. No es un
límite que se pueda correr: se probaron nueve formas de pedir más y todas
contestan quince. Para Boca-River eso son cinco años y medio, cuando el
historial de verdad arranca en 1913.

Así que el historial va partido en dos:

  · Los **últimos cruces**, con fecha y resultado, salen solos de la
    fuente y se guardan en la base. Eso es lo que permite decir "no le
    gana desde 2021" y mostrar la lista.
  · El **total histórico** —cuántas veces se enfrentaron y cómo salió—
    viene de acá, escrito a mano y verificado uno por uno.

"Total oficial" no significa lo mismo en cada clásico
─────────────────────────────────────────────────────
Y ésta es la trampa más grande de estos números. El rosarino y el
santafesino **cuentan las ligas regionales** —75 y 61 partidos que se
jugaron antes de que esos clubes entraran a AFA—; el Superclásico y el de
Avellaneda son sólo AFA e internacionales. Poner los dos totales uno al
lado del otro sin aclararlo hace que alguien compare 279 con 266 como si
fueran la misma unidad, y no lo son. Por eso cada par lleva su `nota` y
la pantalla la muestra.

Ninguno cuenta amistosos ni torneos de verano.

Cómo se verifica
────────────────
Los tres números tienen que sumar el total. Corre en las pruebas, en cada
cambio. Los pares donde eso no da están abajo, en DUDOSOS, y NO se
publican: un historial inventado se lee igual que uno verdadero, y ése es
exactamente el problema.

Y una regla que salió de esta misma investigación: **nunca copiar el
resumen del infobox de Wikipedia sin comprobarlo contra el desglose por
competencia**. Falló en tres de diez casos.

Fuente: Wikipedia en español e inglés cruzadas entre sí, y los sitios
oficiales donde los hay. Actualizado a agosto de 2026.
"""

# (club A, club B): {jugados, ganoA, empates, ganoB, desde, incluye, nota}
#
# El orden de los dos nombres no importa para leerlo: `entre()` da vuelta
# los números si se lo pide al revés.
CLASICOS = {
    ("Boca Juniors", "River Plate"): {
        "jugados": 266, "ganoA": 94, "empates": 84, "ganoB": 88,
        "desde": 1913, "incluye": "AFA e internacionales",
        "nota": "218 de Primera, 16 de copas nacionales, 28 de Libertadores "
                "y 4 de otras internacionales. Los 124 amistosos no cuentan.",
    },
    ("Independiente", "Racing"): {
        "jugados": 239, "ganoA": 90, "empates": 78, "ganoB": 71,
        "desde": 1910, "incluye": "AFA e internacionales",
        "nota": "218 de Primera, 2 de Segunda, 17 de copas nacionales y la "
                "Supercopa Libertadores 1992.",
    },
    ("Estudiantes (LP)", "Gimnasia y Esgrima (LP)"): {
        "jugados": 193, "ganoA": 70, "empates": 72, "ganoB": 51,
        "desde": 1916, "incluye": "AFA e internacionales",
        "nota": "180 de Primera —10 del amateurismo y 170 profesionales—, "
                "11 de copas nacionales y 2 de Copa Sudamericana.",
    },
    ("Banfield", "Lanús"): {
        "jugados": 135, "ganoA": 53, "empates": 40, "ganoB": 42,
        "desde": 1918, "incluye": "AFA, con el amateurismo",
        "nota": "106 de Primera, 24 de Segunda y 5 de copas nacionales. El "
                "museo de Lanús publica 115 porque cuenta sólo desde el "
                "profesionalismo: la diferencia son los 20 del amateurismo.",
    },
    ("Unión", "Colón"): {
        "jugados": 159, "ganoA": 57, "empates": 54, "ganoB": 48,
        "desde": 1913, "incluye": "Liga Santafesina y AFA",
        "nota": "61 de la Liga Santafesina (1913-1940) y 98 de AFA. "
                "Congelado desde octubre de 2023: Colón bajó de categoría.",
    },
    # Éste no suma, y por una razón documentada: un partido del Apertura
    # 1997 se les dio por perdido a los DOS. Cuenta como jugado y no como
    # victoria ni empate de nadie. Es el único caso de la lista donde el
    # descuadre es correcto, y por eso lleva su aclaración.
    ("Huracán", "San Lorenzo"): {
        "jugados": 194, "ganoA": 50, "empates": 56, "ganoB": 87,
        "desde": 1915, "incluye": "AFA",
        "nota": "178 de Primera y 16 de copas nacionales. Los tres números "
                "suman 193 y no 194 porque un partido del Apertura 1997 se "
                "les dio por perdido a los dos.",
        "noSuma": True,
    },
    # Las dos fuentes publican 281 como total y las dos se equivocan: sus
    # propios números suman 279. El error está en la fila de Primera, que
    # declara 179 jugados y detalla 177. Se publica lo que se puede
    # sostener —los tres números— y no el total que no cierra.
    ("Newell's Old Boys", "Rosario Central"): {
        "jugados": 279, "ganoA": 77, "empates": 103, "ganoB": 99,
        "desde": 1905, "incluye": "Liga Rosarina, AFA e internacionales",
        "nota": "75 de la Liga y la Asociación Rosarina (1905-1938), 199 de "
                "AFA, 5 de CONMEBOL y 2 de Copa Santa Fe. Wikipedia publica "
                "281 pero sus propios números dan 279.",
    },
}

# Los que NO se publican, y por qué. Están acá para no volver a
# investigarlos de cero el día que aparezca una fuente mejor.
DUDOSOS = {
    ("Talleres (C)", "Belgrano"):
        "Wikipedia en español dice 261 (96-88-77) en la tabla y 260 en el "
        "infobox; la inglesa dice 257 (96-85-76). La diferencia son 4 "
        "partidos, todos en la fila de Primera, y la fila de la española "
        "tampoco cierra: 5+17+6 da 28 y declara 27. Las dos coinciden en el "
        "último partido, así que no es que una esté vieja.",
    ("Godoy Cruz", "Independiente Rivadavia"):
        "No hay artículo de este cruce: el 'clásico mendocino' de Wikipedia "
        "es Gimnasia (M) contra Independiente Rivadavia. Lo mejor que hay "
        "—171 partidos, 87-41-43 desde 1923, contando Liga Mendocina— es de "
        "abril de 2025 y desde entonces jugaron varias veces más.",
    ("Atlético Tucumán", "San Martín Tucumán"):
        "Wikipedia dice 284 (101-88-95) y suma bien, pero dos "
        "investigaciones argentinas —Alejandro Fabbri y Sebastián "
        "Lampasona— dicen 283 (100-88-95). No es falta de actualización: no "
        "se juega desde 2018. Es una discusión abierta sobre si cuenta un "
        "partido, y elegir un número es tomar partido.",
}


def _plano(s):
    import unicodedata
    import re
    s = "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s)


_INDICE = None


def entre(a, b):
    """
    El total histórico entre dos clubes, o None si no lo tenemos cargado.

    Devuelve los números desde el lado de `a`, sin importar en qué orden
    esté escrito el par: pedirlo al revés da vuelta ganados y perdidos.
    Es lo que hace que la pantalla no tenga que saber cuál se cargó
    primero.
    """
    global _INDICE
    if _INDICE is None:
        _INDICE = {}
        for (x, y), d in CLASICOS.items():
            _INDICE[(_plano(x), _plano(y))] = (d, False)
            _INDICE[(_plano(y), _plano(x))] = (d, True)
    hit = _INDICE.get((_plano(a), _plano(b)))
    if not hit:
        return None
    d, alReves = hit
    return {
        "jugados": d["jugados"],
        "gano": d["ganoB"] if alReves else d["ganoA"],
        "empates": d["empates"],
        "perdio": d["ganoA"] if alReves else d["ganoB"],
        "desde": d["desde"],
        "incluye": d["incluye"],
        "nota": d["nota"],
    }


def pares():
    """Los pares cargados, para las pruebas y para el administrador."""
    return sorted(CLASICOS)
