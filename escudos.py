# -*- coding: utf-8 -*-
"""
Los colores de un club, sacados de su escudo.

Por qué existe
──────────────
Los colores de los treinta clubes de Primera están cargados a mano, y así
está bien: son treinta y se revisaron uno por uno. Pero el sitio tiene
catorce competencias y expandirlas quiere decir cientos de clubes. Cargar
cientos de pares de colores a mano no se termina nunca, y es justo el tipo
de trabajo que no hace falta hacer: el escudo ya dice de qué color es el
club, y el servidor **ya tiene el escudo guardado** —los cachea en la base
para no depender del CDN—. O sea que esto no cuesta ni un pedido más.

Por qué a mano y no con una biblioteca
──────────────────────────────────────
El servidor es sólo biblioteca estándar, a propósito: se despliega sin
instalar nada y no hay una dependencia que se rompa sola. Python no trae
lector de PNG, así que hay uno acá abajo. Son ochenta líneas y hace falta
entender el formato, pero es preferible a meter Pillow —quince megas de
binarios— para leer unos escudos de cuatro kilobytes.

El lector cubre lo que manda el CDN y **se rinde limpiamente con lo que
no**: si un escudo viene entrelazado o de 16 bits devuelve None y el club
se queda con los colores cargados a mano, que es exactamente lo que pasa
hoy. Nunca inventa.
"""

import zlib

FIRMA = b"\x89PNG\r\n\x1a\n"

# Cuántos canales tiene cada tipo de color de PNG.
_CANALES = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def leer_png(datos):
    """
    Decodifica un PNG a (ancho, alto, bytes RGBA).

    Devuelve None si el archivo no es un PNG o si usa algo que este lector
    no cubre. Rendirse es parte del diseño: el que llama ya sabe qué hacer
    sin colores, y una decodificación a medias sería peor que ninguna.
    """
    if not datos or not datos.startswith(FIRMA):
        return None
    pos, ancho, alto, prof, tipo, entrelazado = len(FIRMA), 0, 0, 8, 6, 0
    paleta, transp, comprimido = b"", b"", []

    while pos + 8 <= len(datos):
        largo = int.from_bytes(datos[pos:pos + 4], "big")
        nombre = datos[pos + 4:pos + 8]
        cuerpo = datos[pos + 8:pos + 8 + largo]
        pos += 12 + largo               # 4 largo + 4 nombre + cuerpo + 4 crc
        if nombre == b"IHDR":
            if len(cuerpo) < 13:
                return None
            ancho = int.from_bytes(cuerpo[0:4], "big")
            alto = int.from_bytes(cuerpo[4:8], "big")
            prof, tipo, entrelazado = cuerpo[8], cuerpo[9], cuerpo[12]
        elif nombre == b"PLTE":
            paleta = cuerpo
        elif nombre == b"tRNS":
            transp = cuerpo
        elif nombre == b"IDAT":
            comprimido.append(cuerpo)
        elif nombre == b"IEND":
            break

    # Lo que este lector cubre. Todo lo demás se rechaza en vez de
    # adivinarse: un escudo con los colores cambiados es peor que un escudo
    # sin colores.
    if (prof != 8 or entrelazado != 0 or tipo not in _CANALES
            or not comprimido or not ancho or not alto
            or ancho * alto > 4_000_000):
        return None
    try:
        crudo = zlib.decompress(b"".join(comprimido))
    except zlib.error:
        return None

    canales = _CANALES[tipo]
    ancho_linea = ancho * canales
    if len(crudo) < (ancho_linea + 1) * alto:
        return None

    # ── Deshacer los filtros ────────────────────────────────────────────
    # PNG guarda cada renglón restándole el de al lado o el de arriba, para
    # que después comprima mejor. Hay cinco maneras y el primer byte de
    # cada renglón dice cuál se usó. Esto las deshace.
    salida = bytearray(ancho_linea * alto)
    previa = bytearray(ancho_linea)
    lugar = 0
    for y in range(alto):
        filtro = crudo[lugar]
        linea = bytearray(crudo[lugar + 1:lugar + 1 + ancho_linea])
        lugar += ancho_linea + 1
        if filtro == 1:                                  # el de la izquierda
            for i in range(canales, ancho_linea):
                linea[i] = (linea[i] + linea[i - canales]) & 0xFF
        elif filtro == 2:                                # el de arriba
            for i in range(ancho_linea):
                linea[i] = (linea[i] + previa[i]) & 0xFF
        elif filtro == 3:                                # el promedio
            for i in range(ancho_linea):
                izq = linea[i - canales] if i >= canales else 0
                linea[i] = (linea[i] + ((izq + previa[i]) >> 1)) & 0xFF
        elif filtro == 4:                                # Paeth
            for i in range(ancho_linea):
                a = linea[i - canales] if i >= canales else 0
                b = previa[i]
                c = previa[i - canales] if i >= canales else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cual = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                linea[i] = (linea[i] + cual) & 0xFF
        elif filtro != 0:
            return None
        salida[y * ancho_linea:(y + 1) * ancho_linea] = linea
        previa = linea

    # ── Y llevarlo todo a RGBA, que es como se mira después ─────────────
    pix = bytearray(ancho * alto * 4)
    n = ancho * alto
    if tipo == 6:
        return ancho, alto, bytes(salida)
    for i in range(n):
        o = i * canales
        if tipo == 2:                                    # RGB
            r, g, b, a = salida[o], salida[o + 1], salida[o + 2], 255
        elif tipo == 0:                                  # gris
            r = g = b = salida[o]
            a = 0 if (transp and len(transp) >= 2
                      and salida[o] == transp[1]) else 255
        elif tipo == 4:                                  # gris con alfa
            r = g = b = salida[o]
            a = salida[o + 1]
        else:                                            # paleta
            idx = salida[o]
            if (idx + 1) * 3 > len(paleta):
                return None
            r, g, b = paleta[idx * 3], paleta[idx * 3 + 1], paleta[idx * 3 + 2]
            a = transp[idx] if idx < len(transp) else 255
        j = i * 4
        pix[j], pix[j + 1], pix[j + 2], pix[j + 3] = r, g, b, a
    return ancho, alto, bytes(pix)


# Cuán distintos tienen que ser los dos colores para que valga la pena
# mostrar los dos. Por debajo de esto son el mismo color con otra luz —el
# celeste y el celeste un poco más oscuro de Belgrano— y conviene devolver
# uno solo, como ya hace la lista cargada a mano.
DISTANCIA_MINIMA = 110
# Y cuánto del escudo tiene que ocupar el segundo para no ser un detalle.
# Sin esto, el hilito dorado del borde de un escudo salía como color del
# club.
PARTE_MINIMA = 0.06
# El alfa desde el cual un pixel cuenta. Los escudos vienen con el fondo
# transparente y los bordes suavizados: contar los medio transparentes
# ensucia todo con colores que no están.
ALFA_MINIMO = 200


def _lejos(a, b):
    """Cuán distintos son dos colores, a ojo de buen cubero."""
    return sum(abs(x - y) for x, y in zip(a, b))


def colores_de(png, minimo=PARTE_MINIMA):
    """
    Los dos colores dominantes de un escudo.

    Devuelve {"principal": "#rrggbb", "acento": "#rrggbb", "parte": 0.42,
    "parteAcento": 0.19} o None si no se pudo leer o no hay con qué.

    Cómo: se juntan los pixeles opacos en cajitas de color parecido —de a
    dieciséis tonos por canal, para que el suavizado de los bordes no
    parta un mismo color en veinte— y se toman las dos cajas más grandes
    que además sean bien distintas entre sí. El color que se devuelve es el
    promedio real de esa caja, no el de la caja: así el azul de Boca sale
    azul de Boca y no un azul redondeado.

    Si el segundo color no llega a `minimo` del escudo, o es casi igual al
    primero, se devuelve el principal en los dos lugares. Es lo mismo que
    hace la lista cargada a mano con los clubes de un solo color.
    """
    leido = leer_png(png)
    if not leido:
        return None
    _ancho, _alto, pix = leido

    cajas = {}
    total = 0
    for i in range(0, len(pix), 4):
        if pix[i + 3] < ALFA_MINIMO:
            continue
        r, g, b = pix[i], pix[i + 1], pix[i + 2]
        clave = (r >> 4, g >> 4, b >> 4)
        c = cajas.get(clave)
        if c is None:
            cajas[clave] = [1, r, g, b]
        else:
            c[0] += 1
            c[1] += r
            c[2] += g
            c[3] += b
        total += 1
    if not total:
        return None

    orden = sorted(cajas.values(), key=lambda c: -c[0])

    def medio(c):
        return (c[1] // c[0], c[2] // c[0], c[3] // c[0])

    principal = medio(orden[0])
    parte = orden[0][0] / total
    acento, parte_acento = principal, 0.0
    for c in orden[1:]:
        if c[0] / total < minimo:
            break                       # de acá para abajo son detalles
        cand = medio(c)
        if _lejos(cand, principal) >= DISTANCIA_MINIMA:
            acento, parte_acento = cand, c[0] / total
            break

    hex_ = lambda c: "#%02x%02x%02x" % c
    return {"principal": hex_(principal), "acento": hex_(acento),
            "parte": round(parte, 3), "parteAcento": round(parte_acento, 3)}
