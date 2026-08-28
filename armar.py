# -*- coding: utf-8 -*-
"""
Junta lo que leyó `leer.py` y escribe `tabla.py`, que es lo que se publica.

Lo único que hace de difícil es decidir qué club es cada fila. RSSSF
escribe el mismo club de cinco formas a lo largo de noventa años —"River
Plate" en 1931, "CA River Plate" en 2021— y encima hay homónimos de
verdad: tres San Martín, dos Talleres, cuatro Gimnasia.

La forma de distinguirlos está en la propia fuente y estuve a punto de
tirarla: cada fila termina con la ciudad entre paréntesis. `Talleres
(Remedios de Escalada)` y `Talleres (Córdoba)` son dos clubes y la línea
lo dice. Las tablas modernas ya no traen ciudad, pero ahí el nombre viene
completo, así que se cubren entre las dos.
"""
import collections
import os
import re
import leer

AQUI = os.path.dirname(os.path.abspath(__file__))

# El signo `?` es un carácter que se perdió al decodificar: puede ser á, é,
# í, ó, ú o ñ. Se compara tratándolo como comodín.
def parecido(a, b):
    if len(a) != len(b):
        return False
    return all(x == y or x == "?" or y == "?" for x, y in zip(a, b))


# ── Quién es quién ───────────────────────────────────────────────────────
# (nombre como lo escribe RSSSF, ciudad) → nuestro nombre.
#
# La ciudad va sólo cuando hace falta para distinguir. Donde el nombre ya
# es único, alcanza con el nombre y la ciudad se ignora: así una ciudad
# escrita distinto en dos décadas no parte un club en dos.
POR_CIUDAD = {
    # Los homónimos de verdad. Acá la ciudad NO es un adorno: es el dato
    # que dice de qué club estamos hablando.
    ("talleres", "cordoba"): "Talleres (C)",
    ("talleres", "remedios de escalada"): "Talleres (RdE)",
    ("san martin", "san juan"): "San Martín San Juan",
    ("san martin", "san miguel de tucuman"): "San Martín Tucumán",
    ("san martin", "tucuman"): "San Martín Tucumán",
    ("san martin", "mendoza"): "San Martín (M)",
    ("san martin", "general san martin"): "San Martín (M)",
    ("san martin", "concepcion"): "San Martín (T)",
    ("gimnasia y esgrima", "san salvador de jujuy"): "Gimnasia de Jujuy",
    ("gimnasia y esgrima", "mendoza"): "Gimnasia y Esgrima (M)",
    ("gimnasia y esgrima", "la plata"): "Gimnasia y Esgrima (LP)",
    ("gimnasia y esgrima", "concepcion del uruguay"): "Gimnasia y Esgrima (CdU)",
    ("sarmiento", "junin"): "Sarmiento (J)",
    ("sarmiento", "resistencia"): "Sarmiento (R)",
    ("los andes", "lomas de zamora"): "Los Andes",
    ("los andes", "san juan"): "Los Andes (SJ)",
    ("central cordoba", "santiago del estero"): "Central Córdoba (SdE)",
    ("central cordoba", "rosario"): "Central Córdoba (R)",
    ("kimberley", "mar del plata"): "Kimberley",
    ("belgrano", "cordoba"): "Belgrano",
    ("huracan", "tres arroyos"): "Huracán (Tres Arroyos)",
    ("huracan", "comodoro rivadavia"): "Huracán (CR)",
    ("huracan", "ingeniero white"): "Huracán (IW)",
    ("huracan", "san rafael"): "Huracán (SR)",
    ("huracan", "corrientes"): "Huracán Corrientes",
    ("huracan", "las heras"): "Huracán Las Heras",
    ("ferro carril oeste", "general pico"): "Ferro Carril Oeste (GP)",
    ("union", "general pinedo"): "Unión (GP)",
    ("estudiantes", "la plata"): "Estudiantes (LP)",
    ("estudiantes", "caseros"): "Estudiantes (BA)",
    ("estudiantes", "rio cuarto"): "Estudiantes (RC)",
    ("estudiantes", "santiago del estero"): "Estudiantes (SdE)",
    ("racing", "cordoba"): "Racing (C)",
    ("racing", "avellaneda"): "Racing",
    ("independiente", "trelew"): "Independiente (Trelew)",
}

# Y los que se resuelven sólo con el nombre, sin mirar la ciudad. La clave
# es el nombre ya sin la sigla de sociedad y sin tildes.
POR_NOMBRE = {
    "river plate": "River Plate",
    "boca juniors": "Boca Juniors",
    "san lorenzo de almagro": "San Lorenzo",
    "san lorenzo": "San Lorenzo",
    "san lorenzo mdq": "San Lorenzo (MdP)",
    "racing club": "Racing",
    "racing": "Racing",
    "atletico racing": "Racing (C)",
    "velez sarsfield": "Vélez Sarsfield",
    "velez sarfield": "Vélez Sarsfield",
    "velez sarsfield": "Vélez Sarsfield",
    "independiente": "Independiente",
    "independiente a": "Independiente",
    "independiente avellaneda": "Independiente",
    "independiente rivadavia": "Independiente Rivadavia",
    "estudiantes de la plata": "Estudiantes (LP)",
    "estudiantes lp": "Estudiantes (LP)",
    "atletico estudiantes": "Estudiantes (LP)",
    "estudiantes rcu": "Estudiantes (RC)",
    "estudiantes sde": "Estudiantes (SdE)",
    "newell s old boys": "Newell's Old Boys",
    "rosario central": "Rosario Central",
    "argentinos juniors": "Argentinos Juniors",
    "lanus": "Lanús",
    "huracan": "Huracán",
    "huracan ba": "Huracán",
    "huracan bue": "Huracán",
    "huracan buenos aires": "Huracán",
    "huracan afa": "Huracán",
    "atletico huracan": "Huracán",
    "huracan c": "Huracán (CR)",
    "huracan tres arroyos": "Huracán (Tres Arroyos)",
    "huracan las heras": "Huracán Las Heras",
    "gimnasia y esgrima la plata": "Gimnasia y Esgrima (LP)",
    "gimnasia y esgrima lp": "Gimnasia y Esgrima (LP)",
    "de gimnasia y esgrima": "Gimnasia y Esgrima (LP)",
    "gimnasia y esgrima j": "Gimnasia de Jujuy",
    "gimnasia y esgrima juj": "Gimnasia de Jujuy",
    "gimnasia y esgrima jujuy": "Gimnasia de Jujuy",
    "gimnasia y esgrima mdz": "Gimnasia y Esgrima (M)",
    "gimnasia y egrima m": "Gimnasia y Esgrima (M)",
    "atletico gimnasia y esgrima": "Gimnasia y Esgrima (M)",
    "gimnasia y tiro": "Gimnasia y Tiro",
    "banfield": "Banfield",
    "chacarita juniors": "Chacarita Juniors",
    "colon": "Colón",
    "colon sfn": "Colón",
    "union": "Unión",
    "union sfn": "Unión",
    "union sf": "Unión",
    "union santa fe": "Unión",
    "union san vicente": "Unión San Vicente",
    "union general pinedo": "Unión (GP)",
    "union talleres lanus": "Unión Talleres-Lanús",
    "platense": "Platense",
    "platense vl": "Platense",
    "atlanta": "Atlanta",
    "tigre": "Tigre",
    "quilmes": "Quilmes",
    "argentino de quilmes": "Argentino de Quilmes",
    "ferro carril oeste": "Ferro Carril Oeste",
    "ferro carril oeste bue": "Ferro Carril Oeste",
    "ferro carril oeste ba": "Ferro Carril Oeste",
    "ferro carril oeste gpo": "Ferro Carril Oeste (GP)",
    "arsenal": "Arsenal",
    "godoy cruz antonio tomba": "Godoy Cruz",
    "all boys": "All Boys",
    "olimpo": "Olimpo",
    "instituto": "Instituto",
    "instituto acc": "Instituto",
    "belgrano": "Belgrano",
    "belgrano c": "Belgrano",
    "belgrano cordoba": "Belgrano",
    "belgrano cor": "Belgrano",
    "talleres cor": "Talleres (C)",
    "talleres c": "Talleres (C)",
    "talleres cordoba": "Talleres (C)",
    "talleres rde": "Talleres (RdE)",
    "atletico tucuman": "Atlético Tucumán",
    "atletico de rafaela": "Atlético Rafaela",
    "atletico rafaela": "Atlético Rafaela",
    "amsd atletico de rafaela": "Atlético Rafaela",
    "defensa y justicia": "Defensa y Justicia",
    "aldosivi": "Aldosivi",
    "temperley": "Temperley",
    "nueva chicago": "Nueva Chicago",
    "barracas central": "Barracas Central",
    "deportivo riestra afbc": "Deportivo Riestra",
    "central cordoba sde": "Central Córdoba (SdE)",
    "central cordoba r": "Central Córdoba (R)",
    "central norte": "Central Norte (S)",
    "patronato juventud catolica": "Patronato",
    "patronato": "Patronato",
    "sarmiento jni": "Sarmiento (J)",
    "san martin tuc": "San Martín Tucumán",
    "san martin t": "San Martín Tucumán",
    "san martin sm de tucuman": "San Martín Tucumán",
    "san martin mendoza": "San Martín (M)",
    "san martin san juan": "San Martín San Juan",
    "atletico san martin": "San Martín Tucumán",
    "atletico club san martin": "San Martín Tucumán",
    "san telmo": "San Telmo",
    "deportivo espanol": "Deportivo Español",
    "deportivo mandiyu": "Deportivo Mandiyú",
    "deportivo armenio": "Deportivo Armenio",
    "deportivo italiano": "Sportivo Italiano",
    "deportivo moron": "Deportivo Morón",
    "deportivo roca": "Deportivo Roca",
    "chaco for ever": "Chaco For Ever",
    "cipolletti": "Cipolletti",
    "almagro": "Almagro",
    "altos hornos zapla": "Altos Hornos Zapla",
    "alvarado": "Alvarado",
    "andino": "Andino",
    "atletico ledesma": "Atlético Ledesma",
    "atletico concepcion": "Atlético Concepción",
    "atletico regina": "Atlético Regina",
    "atletico santa rosa": "Atlético Santa Rosa",
    "atletico uruguay": "Atlético Uruguay",
    "bartolome mitre": "Bartolomé Mitre",
    "circulo deportivo": "Círculo Deportivo",
    "amdpd crucero del norte": "Crucero del Norte",
    "don orione": "Don Orione",
    "guarani antonio franco": "Guaraní A. Franco",
    "jorge newbery": "Jorge Newbery",
    "juventud antoniana": "Juventud Antoniana",
    "juventud alianza": "Juventud Alianza (SJ)",
    "alianza juventud pringles": "Alianza Juventud-Pringles",
    "kimberley": "Kimberley",
    "kimberley mdq": "Kimberley",
    "loma negra": "Loma Negra",
    "los andes": "Los Andes",
    "los andes lomas de zamora": "Los Andes",
    "mariano moreno": "Mariano Moreno",
    "puerto comercial": "Puerto Comercial",
    "ramon santamarina": "Ramón Santamarina",
    "renato cesarini": "Renato Cesarini",
    "sportivo desamparados": "Desamparados",
    "sportivo patria": "Sportivo Patria",
    "tiro federal": "Tiro Federal",
    "argentino": "Argentino (Firmat)",
}

# Y los nombres legales completos, que es como los escriben las páginas de
# temporada suelta de 2025 en adelante: "Club Atlético River Plate Asoc.
# Civil". Van escritos uno por uno en vez de recortados con reglas —sacar
# "Club Atlético" del principio y "Asociación Civil" del final— porque las
# reglas fallan justo donde importa: "Deportivo Riestra" y "Club Deportivo
# Godoy Cruz" empiezan igual y sólo uno lleva el "Deportivo" en el nombre.
LEGALES = {
    "club atletico river plate asoc civil": "River Plate",
    "club atletico boca juniors asociacion civil": "Boca Juniors",
    "club atletico san lorenzo de almagro": "San Lorenzo",
    "club atletico independiente": "Independiente",
    "racing club asociacion civil": "Racing",
    "club atletico velez sarsfield asociacion civil": "Vélez Sarsfield",
    "club estudiantes de la plata": "Estudiantes (LP)",
    "club de gimnasia y esgrima la plata": "Gimnasia y Esgrima (LP)",
    "club de gimnasia y esgrima lp": "Gimnasia y Esgrima (LP)",
    "club atletico newell s old boys": "Newell's Old Boys",
    "club atletico rosario central": "Rosario Central",
    "asociacion atletica argentinos juniors": "Argentinos Juniors",
    "club atletico lanus": "Lanús",
    "club atletico huracan": "Huracán",
    "club atletico banfield sociedad civil": "Banfield",
    "club atletico platense asociacion civil": "Platense",
    "club atletico tigre sociedad civil": "Tigre",
    "club atletico union": "Unión",
    "club atletico talleres": "Talleres (C)",
    "club atletico belgrano": "Belgrano",
    "instituto atletico central cordoba": "Instituto",
    "club atletico tucuman": "Atlético Tucumán",
    "club atletico tucuman soc civil": "Atlético Tucumán",
    "club atletico central cordoba soc civil": "Central Córdoba (SdE)",
    "club deportivo godoy cruz antonio tomba": "Godoy Cruz",
    "club sportivo independiente rivadavia": "Independiente Rivadavia",
    "club social y deportivo defensa y justicia": "Defensa y Justicia",
    "deportivo riestra asociacion de fomento barrio colon": "Deportivo Riestra",
    "club atletico barracas central": "Barracas Central",
    "club atletico aldosivi": "Aldosivi",
    "club atletico sarmiento": "Sarmiento (J)",
    "club atletico san martin": "San Martín San Juan",
    "asociacion atletica estudiantes": "Estudiantes (RC)",
    "club atletico gimnasia y esgrima": "Gimnasia y Esgrima (M)",
}

# Los nombres pelados que NO se pueden resolver sin la ciudad. Si uno de
# éstos llega sin ciudad, se anota como sin resolver en vez de asignarlo
# al que suene parecido: mezclar dos clubes es peor que dejar un hueco.
NECESITAN_CIUDAD = {"talleres", "san martin", "gimnasia y esgrima",
                    "central cordoba", "sarmiento", "estudiantes",
                    "los andes", "racing"}


def clave(txt):
    """
    Sin tildes, sin signos, en minúscula, para poder comparar.

    El `?` se conserva a propósito: es el carácter que se perdió al
    decodificar y hace de comodín. Borrándolo, "V?lez" quedaba "vlez", que
    tiene una letra menos que "velez" y no matcheaba con nada. Ése solo
    error dejaba 16.837 partidos sin asignar a ningún club.
    """
    return re.sub(r"[^a-z0-9 ?]+", "", leer.plano(txt or "")).strip()


def busca(mapa, nombre, ciudad=None):
    """Busca en el mapa tratando el `?` de la fuente como comodín."""
    for k, v in mapa.items():
        kn, kc = (k, None) if ciudad is None else k
        if not parecido(kn, nombre):
            continue
        if ciudad is not None and not parecido(kc, ciudad):
            continue
        return v
    return None


# Las tablas de 2021 en adelante ya no traen la ciudad, y ahí quedan
# nombres pelados que sí son ambiguos en la historia larga. Se resuelven
# por temporada, que es un dato duro: en 2021 el único Talleres de Primera
# era el de Córdoba, y el único Sarmiento el de Junín.
POR_TEMPORADA = {
    ("2009/2010", "gimnasia y esgrima"): "Gimnasia de Jujuy",
    ("2011/2012", "san mart?n"): "San Martín San Juan",
    ("2012/2013", "san mart?n"): "San Martín San Juan",
    ("2021", "talleres"): "Talleres (C)",
    ("2022", "talleres"): "Talleres (C)",
    ("2023", "talleres"): "Talleres (C)",
    ("2024", "talleres"): "Talleres (C)",
    ("2021", "sarmiento"): "Sarmiento (J)",
    ("2022", "sarmiento"): "Sarmiento (J)",
    ("2023", "sarmiento"): "Sarmiento (J)",
    ("2024", "sarmiento"): "Sarmiento (J)",
}


def resolver(fila):
    """De qué club es esta fila. None si no se puede saber."""
    # El nombre legal completo va primero: es el más específico y el que
    # no se puede confundir con nada.
    v = busca(LEGALES, clave(fila["club"]))
    if v:
        return v
    n = clave(leer.sin_siglas(fila["club"]))
    for (t, nn), v in POR_TEMPORADA.items():
        if t == fila["temporada"] and parecido(clave(nn), n):
            return v
    c = clave(fila.get("ciudad"))
    if c:
        v = busca(POR_CIUDAD, n, c)
        if v:
            return v
    v = busca(POR_NOMBRE, n)
    if v and (n.replace("?", "") not in
              {x.replace("?", "") for x in NECESITAN_CIUDAD} or c):
        return v
    return v


def armar():
    filas, _ = leer.todo()
    ac, sinres = {}, collections.Counter()
    for f in filas:
        club = resolver(f)
        if not club:
            sinres[(f["club"], f.get("ciudad"))] += f["pj"]
            continue
        a = ac.setdefault(club, dict(club=club, pj=0, g=0, e=0, p=0,
                                     gf=0, gc=0, temporadas=set()))
        for c in ("pj", "g", "e", "p", "gf", "gc"):
            a[c] += f[c]
        a["temporadas"].add(f["temporada"])
    return ac, sinres


CABECERA = '''# -*- coding: utf-8 -*-
"""
La tabla histórica de Primera División, era profesional.

ESTE ARCHIVO SE GENERA. No lo edites a mano: lo escribe
`_fuente/armar.py` a partir de las tablas de RSSSF guardadas en
`_fuente/`. Para actualizarlo cuando termine una temporada, se baja la
página de esa temporada y se vuelve a correr.

De dónde sale
─────────────
De sumar la tabla final de cada torneo de Primera desde 1931: Campeonato,
Copa Campeonato, Metropolitano, Nacional, Apertura, Clausura, Inicial,
Final y Liga Profesional, con sus zonas y sus fases finales.

No cuentan los torneos que no son el campeonato —Reclasificación,
Liguilla Pre Libertadores, Promocional, Petit— ni los playoffs de
descenso, ni la Copa de la Liga, que es una copa y ya está en historia.py.

Por qué se hizo de cero
───────────────────────
Porque no existe publicada y bien. La de Wikipedia falla las cuatro
verificaciones básicas: los ganados de todos los clubes suman 390 más que
los perdidos, hay 24 filas donde los partidos no dan la suma de ganados,
empatados y perdidos, está congelada en abril de 2020 aunque el título
diga 2025, y Barracas Central no aparece.

Los puntos
──────────
Se cuentan 3 por victoria en toda la historia, también en los años en que
se daban 2. Es la única forma de comparar a un equipo de los 60 con uno
de hoy: con el sistema viejo, un triunfo del 72 vale menos que uno del
2020 y el orden queda distorsionado a favor de los clubes modernos.

Qué tan exacta es
─────────────────
Las cuatro verificaciones corren en las pruebas. Los partidos dan la suma
de ganados, empatados y perdidos en las %(filas)s filas leídas, sin una
sola excepción. Quedan %(dg)s partidos y %(dgol)s goles de desbalance
sobre %(tg)s y %(tgol)s: es el residuo de la propia fuente, que asienta de
forma asimétrica los partidos dados por ganados y los abandonados.

Fuente: RSSSF, tablas finales de Argentina, de Osvaldo José Gorgazzi y
Víctor Hugo Kurhy. %(temporadas)s temporadas, de %(desde)s a %(hasta)s.
"""

# (club, PJ, G, E, P, GF, GC). Los puntos se calculan: 3*G + E.
TABLA = [
'''


def escribir():
    ac, sinres = armar()
    filas, _ = leer.todo()
    if sinres:
        raise SystemExit("hay filas sin resolver: %s" % sinres.most_common(5))
    temps = sorted({t for a in ac.values() for t in a["temporadas"]},
                   key=lambda x: (int(x[:4]), x))
    orden = sorted(ac.values(),
                   key=lambda a: (-(3 * a["g"] + a["e"]), a["club"]))
    tot = lambda k: sum(a[k] for a in ac.values())
    datos = {"filas": "{:,}".format(len(filas)).replace(",", "."),
             "dg": abs(tot("g") - tot("p")), "dgol": abs(tot("gf") - tot("gc")),
             "tg": "{:,}".format(tot("g")).replace(",", "."),
             "tgol": "{:,}".format(tot("gf")).replace(",", "."),
             "temporadas": len(temps), "desde": temps[0], "hasta": temps[-1]}
    salida = [CABECERA % datos]
    for a in orden:
        salida.append('    (%-26s %5d, %5d, %5d, %5d, %6d, %6d),\n'
                      % ('"%s",' % a["club"], a["pj"], a["g"], a["e"],
                         a["p"], a["gf"], a["gc"]))
    salida.append("]\n\nDESDE = %r\nHASTA = %r\nTEMPORADAS = %d\n"
                  % (temps[0], temps[-1], len(temps)))
    destino = os.path.join(os.path.dirname(AQUI), "tabla.py")
    open(destino, "w", encoding="utf-8").write("".join(salida))
    print("escrito:", destino, "-", len(orden), "clubes")


if __name__ == "__main__":
    import sys
    if "--escribir" in sys.argv:
        escribir()
        raise SystemExit
    ac, sinres = armar()
    print("clubes resueltos:", len(ac))
    print("filas sin resolver:", sum(sinres.values()), "partidos")
    for (n, c), v in sinres.most_common(14):
        print("   ?", n, "|", c, "→", v)
    print()
    tot = lambda k: sum(a[k] for a in ac.values())
    print("ΣG %d vs ΣP %d → %+d" % (tot("g"), tot("p"), tot("g") - tot("p")))
    print("ΣGF %d vs ΣGC %d → %+d" % (tot("gf"), tot("gc"),
                                      tot("gf") - tot("gc")))
    print()
    orden = sorted(ac.values(), key=lambda a: -(3 * a["g"] + a["e"]))
    print(f"{'club':<26}{'PJ':>5}{'G':>5}{'E':>5}{'P':>5}{'GF':>6}{'GC':>6}{'Pts':>6}")
    for a in orden[:22]:
        print(f"{a['club'][:25]:<26}{a['pj']:>5}{a['g']:>5}{a['e']:>5}"
              f"{a['p']:>5}{a['gf']:>6}{a['gc']:>6}{3*a['g']+a['e']:>6}")
