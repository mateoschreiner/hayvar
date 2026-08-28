# -*- coding: utf-8 -*-
"""
Los títulos de los clubes españoles: nacionales e internacionales.

Cómo está verificado
────────────────────
Con la misma cuenta que salvó la tabla histórica argentina, que es la
única que sirve de verdad: **los títulos de cada torneo tienen que sumar
sus ediciones**. Si un club tiene una Liga de más, el total se pasa de 95
y salta. Un número inventado que no rompe ninguna suma es casi imposible
de detectar leyendo; uno que rompe la suma se cae solo, y encima se cae
en las pruebas y no en pantalla.

Las tres nacionales cierran: 95, 124 y 42. Las seis internacionales
también: 20, 14, 7, 17, 4 y 8. Corre en cada cambio.

Por qué las nacionales van por cantidad y no por temporada
──────────────────────────────────────────────────────────
Porque es lo que la investigación sostiene. Para Argentina tenemos el
campeón de cada temporada desde 1931 y por eso ahí se guarda la lista
entera. Acá tengo los totales por club cruzados contra tres fuentes, pero
no el detalle año por año de las 124 Copas del Rey. Guardar una lista que
no verifiqué para que "quede igual que la otra" sería inventar 124 filas
para que el archivo se vea prolijo.

Las internacionales sí van con el año de cada una: ésas sí las tengo.

Dos decisiones que cambian números en pantalla
──────────────────────────────────────────────
· La **Copa de Ferias** (1955-71) va aparte, no sumada. La UEFA no la
  reconoce —no la organizó ella— pero la FIFA sí la lista y el Valencia
  directamente la suma a sus Copas UEFA en su propia web. Mostrarla sin
  aclarar de qué lado estamos sería elegir en silencio.
· La **Copa Intercontinental de la FIFA 2024** cuenta, en su propia
  columna. Es un torneo FIFA oficial, pero es una competencia distinta de
  la Intercontinental 1960-2004 y del Mundial de Clubes: la propia FIFA
  reconoce a los campeones de las tres pero no une las estadísticas. El
  Real Madrid anuncia "9 mundiales" juntando las tres cosas; acá van
  separadas y el que quiera sumarlas puede.

Fuentes: Wikipedia en español y en inglés cruzadas entre sí, RSSSF como
tercera pata independiente, laliga.com y las webs oficiales de los clubes.
Agosto de 2026, con la temporada 2025-26 terminada.
"""

# ── Los títulos nacionales, por club ────────────────────────────────────
#
# Los nombres son los canónicos del sitio, los mismos que devuelve el
# calendario. Los seis clubes que hoy no juegan Primera van igual: dejar
# afuera al Zaragoza porque bajó sería contar la historia por la tabla de
# este año.
NACIONALES = {
    "FC Barcelona":                  {"liga": 29, "copa": 32, "supercopa": 16},
    "Real Madrid":                   {"liga": 36, "copa": 20, "supercopa": 13},
    "Athletic Club":                 {"liga":  8, "copa": 24, "supercopa":  3},
    "Atlético de Madrid":            {"liga": 11, "copa": 10, "supercopa":  2},
    "Valencia CF":                   {"liga":  6, "copa":  8, "supercopa":  1},
    "Sevilla FC":                    {"liga":  1, "copa":  5, "supercopa":  1},
    "Real Zaragoza":                 {"liga":  0, "copa":  6, "supercopa":  1},
    "Real Sociedad":                 {"liga":  2, "copa":  3, "supercopa":  1},
    "RC Deportivo":                  {"liga":  1, "copa":  2, "supercopa":  3},
    "Real Betis":                    {"liga":  1, "copa":  3, "supercopa":  0},
    "RCD Espanyol":                  {"liga":  0, "copa":  4, "supercopa":  0},
    "Real Unión":                    {"liga":  0, "copa":  3, "supercopa":  0},
    "RCD Mallorca":                  {"liga":  0, "copa":  1, "supercopa":  1},
    "Arenas Club de Getxo":          {"liga":  0, "copa":  1, "supercopa":  0},
    "Club Ciclista de San Sebastián": {"liga": 0, "copa":  1, "supercopa":  0},
    "Racing Club de Irún":           {"liga":  0, "copa":  1, "supercopa":  0},
}

NOMBRES = {
    "liga": "LaLiga",
    "copa": "Copa del Rey",
    "supercopa": "Supercopa de España",
}

# Cuántas veces se jugó cada una. Es el número contra el que se verifica
# todo lo de arriba, así que va con su explicación: sin ella, el día que
# no cierre nadie va a saber si el que está mal es un club o esta línea.
EDICIONES = {
    # 1928-29 a 2025-26 son 98 temporadas, menos las tres de la guerra
    # civil (1936-37, 1937-38 y 1938-39) que no se jugaron.
    "liga": 95,
    # 1903 a 2026 son 124 años, menos 1937 y 1938 que no se disputaron,
    # más dos: en 1910 y en 1913 hubo torneos paralelos con dos campeones
    # reconocidos cada año. La final de 1904 no se jugó —el rival se
    # retiró— y aun así cuenta como título del Athletic en todas las
    # fuentes.
    "copa": 124,
    # 1982-83 a 2025-26 son 44, menos 1986 y 1987, que no se disputaron
    # porque no hubo acuerdo de fechas. Ojo: 1984 y 1989 SÍ cuentan
    # aunque no se jugó partido —se adjudicaron al que había hecho el
    # doblete— y la RFEF las numera como ediciones.
    "supercopa": 42,
}

# Clubes desaparecidos, para que la pantalla pueda decirlo en vez de
# dejar a alguien buscando por qué no encuentra su ficha.
DESAPARECIDOS = ("Club Ciclista de San Sebastián", "Racing Club de Irún")

# ── Los títulos internacionales ─────────────────────────────────────────
#
# (año, campeón). Acá sí va el detalle, porque acá sí lo verifiqué.
COPAS = [
    ("Copa de Europa / Champions League", [
        ("1956", "Real Madrid"), ("1957", "Real Madrid"),
        ("1958", "Real Madrid"), ("1959", "Real Madrid"),
        ("1960", "Real Madrid"), ("1966", "Real Madrid"),
        ("1992", "FC Barcelona"),
        ("1998", "Real Madrid"), ("2000", "Real Madrid"),
        ("2002", "Real Madrid"),
        ("2006", "FC Barcelona"), ("2009", "FC Barcelona"),
        ("2011", "FC Barcelona"),
        ("2014", "Real Madrid"),
        ("2015", "FC Barcelona"),
        ("2016", "Real Madrid"), ("2017", "Real Madrid"),
        ("2018", "Real Madrid"), ("2022", "Real Madrid"),
        ("2024", "Real Madrid"),
    ]),
    ("Copa de la UEFA / Europa League", [
        ("1985", "Real Madrid"), ("1986", "Real Madrid"),
        ("2004", "Valencia CF"),
        ("2006", "Sevilla FC"), ("2007", "Sevilla FC"),
        ("2010", "Atlético de Madrid"), ("2012", "Atlético de Madrid"),
        ("2014", "Sevilla FC"), ("2015", "Sevilla FC"),
        ("2016", "Sevilla FC"),
        ("2018", "Atlético de Madrid"),
        ("2020", "Sevilla FC"),
        ("2021", "Villarreal CF"),
        ("2023", "Sevilla FC"),
    ]),
    ("Recopa de Europa", [
        ("1962", "Atlético de Madrid"),
        ("1979", "FC Barcelona"),
        ("1980", "Valencia CF"),
        ("1982", "FC Barcelona"),
        ("1989", "FC Barcelona"),
        ("1995", "Real Zaragoza"),
        ("1997", "FC Barcelona"),
    ]),
    ("Supercopa de Europa", [
        ("1980", "Valencia CF"),
        ("1992", "FC Barcelona"),
        ("1997", "FC Barcelona"),
        ("2002", "Real Madrid"),
        ("2004", "Valencia CF"),
        ("2006", "Sevilla FC"),
        ("2009", "FC Barcelona"),
        ("2010", "Atlético de Madrid"),
        ("2011", "FC Barcelona"),
        ("2012", "Atlético de Madrid"),
        ("2014", "Real Madrid"),
        ("2015", "FC Barcelona"),
        ("2016", "Real Madrid"), ("2017", "Real Madrid"),
        ("2018", "Atlético de Madrid"),
        ("2022", "Real Madrid"), ("2024", "Real Madrid"),
    ]),
    ("Copa Intercontinental", [
        ("1960", "Real Madrid"),
        ("1974", "Atlético de Madrid"),
        ("1998", "Real Madrid"),
        ("2002", "Real Madrid"),
    ]),
    ("Mundial de Clubes", [
        ("2009", "FC Barcelona"),
        ("2011", "FC Barcelona"),
        ("2014", "Real Madrid"),
        ("2015", "FC Barcelona"),
        ("2016", "Real Madrid"), ("2017", "Real Madrid"),
        ("2018", "Real Madrid"), ("2022", "Real Madrid"),
    ]),
    ("Copa Intercontinental de la FIFA", [
        ("2024", "Real Madrid"),
    ]),
]

# Cuántas ganó España en cada una. La otra mitad de la verificación.
GANADAS = {
    "Copa de Europa / Champions League": 20,
    "Copa de la UEFA / Europa League": 14,
    "Recopa de Europa": 7,
    "Supercopa de Europa": 17,
    "Copa Intercontinental": 4,
    "Mundial de Clubes": 8,
    "Copa Intercontinental de la FIFA": 1,
}

# ── La Copa de Ferias, aparte ───────────────────────────────────────────
#
# No se suma a nada. Se muestra con su aclaración porque los clubes la
# exhiben y alguien que ve "Barcelona 17" y en el museo del club cuenta
# 20 tiene derecho a saber de dónde sale la diferencia.
FERIAS = [
    ("1958", "FC Barcelona"),
    ("1960", "FC Barcelona"),
    ("1962", "Valencia CF"),
    ("1963", "Valencia CF"),
    ("1964", "Real Zaragoza"),
    ("1966", "FC Barcelona"),
]

DISCUTIDAS = {
    "Copa de Ferias":
        "La organizó un comité de ferias comerciales y no la UEFA, que por "
        "eso no la cuenta ni en palmarés ni en estadísticas. La FIFA sí la "
        "lista, LaLiga la trata como Europa League y el Valencia la suma a "
        "sus Copas UEFA en su propia web. Acá va aparte y no suma.",
    "Copa Intercontinental de la FIFA":
        "Torneo FIFA oficial estrenado en 2024, distinto de la "
        "Intercontinental 1960-2004 y del Mundial de Clubes. La FIFA "
        "reconoce a los campeones de las tres pero no une las "
        "estadísticas. El Real Madrid anuncia nueve mundiales sumándolas.",
}

# Discusiones que NO cambian nuestros números, pero que alguien va a
# encontrar en otra fuente y va a querer entender.
NOTAS = {
    "Athletic Club":
        "El club cuenta 25 Copas sumando la Copa de la Coronación de 1902, "
        "que ganó un combinado de Bilbao. La RFEF no la reconoce en el "
        "palmarés de la Copa del Rey, así que acá son 24.",
    "Real Sociedad":
        "La Copa de 1909 la ganó el Club Ciclista de San Sebastián, con "
        "jugadores de la Real Sociedad todavía sin constituir formalmente. "
        "Hay fuentes que se la asignan a la Real, que quedaría en 4.",
    "Real Unión":
        "La Copa de 1913 la ganó el Racing Club de Irún, que en 1915 se "
        "fusionó para formar el Real Unión. Hay fuentes que se la asignan "
        "al Real Unión, que quedaría en 4.",
    "RC Deportivo":
        "La RFEF reconoció en 2023 el Concurso España de 1912, pero no "
        "como Copa del Rey. Por eso siguen siendo 2 Copas y no 3.",
    "Levante UD":
        "La RFEF reconoció en 2023 la Copa de la España Libre de 1937 "
        "como competición oficial, pero no como Copa del Rey.",
}


# ── Los escudos de los que hoy no juegan Primera ────────────────────────
#
# Los veinte de LaLiga ya traen su escudo del calendario. Estos cuatro no
# juegan Primera, así que hay que decir dónde está el suyo: (versión, id).
#
# Se confirmaron uno por uno contra el país de la fuente —los cuatro dan
# España, igual que el Barcelona— porque "Arenas" y "Real Unión" tienen
# homónimos en otros países y en categorías juveniles.
#
# Los dos clubes desaparecidos no están y no van a estar: no existe un
# escudo que enlazar. La pantalla los muestra sin escudo, que es lo
# honesto.
ESCUDOS = {
    "Real Zaragoza": (1, 145),
    "RCD Mallorca": (6, 142),
    "Real Unión": (1, 179),
    "Arenas Club de Getxo": (1, 18122),
}


def escudo_de(club):
    """La dirección del escudo, o None si no tenemos uno."""
    par = ESCUDOS.get(club)
    return "/img/competidor/%s/%s" % par if par else None


def _plano(s):
    import unicodedata
    import re
    s = "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", s)


def nacionales():
    """
    Los clubes con títulos nacionales, del que más tiene al que menos.

    Con el desglose por competencia: un total pelado de 77 no dice si son
    ligas o copas, y no es lo mismo.
    """
    salida = []
    for club, d in NACIONALES.items():
        total = sum(d.values())
        salida.append({
            "club": club, "total": total,
            "liga": d["liga"], "copa": d["copa"], "supercopa": d["supercopa"],
            "desaparecido": club in DESAPARECIDOS,
            "nota": NOTAS.get(club, ""),
            "detalle": [{"copa": NOMBRES[k], "cuantas": d[k]}
                        for k in ("liga", "copa", "supercopa") if d[k]],
        })
    salida.sort(key=lambda x: (-x["total"], -x["liga"], _plano(x["club"])))
    _posiciones(salida)
    return salida


def internacionales():
    """Los clubes con títulos internacionales, con el año de cada uno."""
    cuenta = {}
    for copa, filas in COPAS:
        for ano, campeon in filas:
            c = cuenta.setdefault(campeon, {"club": campeon, "total": 0,
                                            "detalle": {}})
            c["total"] += 1
            c["detalle"].setdefault(copa, []).append(ano)
    salida = sorted(cuenta.values(),
                    key=lambda x: (-x["total"], _plano(x["club"])))
    for x in salida:
        x["nota"] = NOTAS.get(x["club"], "")
        x["ferias"] = sum(1 for _a, c in FERIAS if c == x["club"])
        x["detalle"] = [{"copa": k, "temporadas": sorted(v, reverse=True),
                         "discutida": DISCUTIDAS.get(k, "")}
                        for k, v in sorted(x["detalle"].items(),
                                           key=lambda kv: -len(kv[1]))]
    _posiciones(salida)
    return salida


def _posiciones(filas):
    """
    El número de orden, compartido cuando hay empate.

    Dos clubes con 8 títulos son los dos octavos y el siguiente es
    décimo. Numerarlos 8, 9, 10 dice que uno tiene más que el otro.
    """
    for i, x in enumerate(filas, 1):
        x["pos"] = i if i == 1 or x["total"] != filas[i - 2]["total"] \
            else filas[i - 2]["pos"]
    return filas


def ferias():
    """La Copa de Ferias, por club. Aparte de todo lo demás."""
    cuenta = {}
    for ano, club in FERIAS:
        cuenta.setdefault(club, []).append(ano)
    return sorted(({"club": c, "cuantas": len(a),
                    "temporadas": sorted(a, reverse=True)}
                   for c, a in cuenta.items()),
                  key=lambda x: (-x["cuantas"], _plano(x["club"])))


def de_club(club):
    """Todo lo de un club, para su ficha. None si no ganó nada."""
    n = next((x for x in nacionales() if _plano(x["club"]) == _plano(club)),
             None)
    i = next((x for x in internacionales()
              if _plano(x["club"]) == _plano(club)), None)
    if not n and not i:
        return None
    return {"nacionales": n, "internacionales": i,
            "total": (n["total"] if n else 0) + (i["total"] if i else 0)}


def controles():
    """
    Las sumas que tienen que cerrar. Devuelve los que NO cierran.

    Vacío quiere decir que está todo bien. Es la única defensa real
    contra un número mal copiado: uno que rompe la suma se cae solo.
    """
    malos = []
    for k, esperado in EDICIONES.items():
        suma = sum(d[k] for d in NACIONALES.values())
        if suma != esperado:
            malos.append((NOMBRES[k], suma, esperado))
    for copa, filas in COPAS:
        if len(filas) != GANADAS.get(copa):
            malos.append((copa, len(filas), GANADAS.get(copa)))
    return malos
