# -*- coding: utf-8 -*-
"""
Las fichas de los clubes que no son de Primera.

Los treinta de Primera están cargados en `CLUBES_INFO`, adentro de
`server.py`, con sus camisetas dibujadas a mano. Éstos van aparte por dos
razones: son datos de investigación y no de diseño, y son muchos —acá
están los treinta de la Copa Argentina y van a seguir las otras
competencias—. Mezclarlos haría que `server.py` fuera medio archivo de
datos.

Cómo se cargaron
────────────────
Buscando cada dato en la web, con una regla: **si no hay una fuente
decente, va vacío**. Un club sin capacidad muestra la ficha sin esa
tarjeta, que es lo que corresponde; una capacidad equivocada se lee como
un dato y no como una duda.

La capacidad es el campo que peor documentado está en el ascenso
argentino: para el mismo estadio se encuentran cifras que difieren al
doble, y varios están en obra. Por eso la mayoría quedó vacía. En
DUDOSOS.md está el detalle de cada uno, para completarlos con una fuente
mejor.

Tres cosas que aparecieron y conviene no perder
───────────────────────────────────────────────
· Dominios secuestrados. `clubdeportivomoron.com.ar` (el viejo de Morón,
  que Wikipedia todavía cita) y `realpilarfutbolclub.com` hoy redirigen a
  sitios de casino. No están acá.
· Sitios oficiales con spam inyectado: el de Estudiantes de Caseros y el
  `.com` de San Martín de Tucumán. Del segundo hay un `.com.ar` sano, que
  es el que está; del primero no, así que quedó sin sitio.
· Sitios que sólo andan por HTTP —Camioneros, Deportivo Rincón—. No van:
  mandar a alguien a una página sin cifrar desde un link nuestro no está
  bueno. Cuando pongan HTTPS se agregan.

Las claves son el nombre con el que el sitio muestra a cada club, que es
como lo nombra la fuente. Si mañana cambia, la ficha deja de encontrarse:
por eso hay una prueba que las cruza contra los equipos de la competencia.
"""

CLUBES = {
    # ── Primera Nacional ────────────────────────────────────────────────
    "Acassuso": {
        "nombre": "Club Atlético Acassuso",
        "apodo": "El Quemero",
        "fundado": 1922,
        "estadio": "Estadio La Quema",
        "direccion": "Santa Rita 2700, Boulogne Sur Mer, San Isidro",
        "ciudad": "Boulogne Sur Mer, Buenos Aires",
        "division": "Primera Nacional",
        "sitio": "https://clubacassuso.com.ar",
    },
    "Agropecuario": {
        "nombre": "Club Agropecuario Argentino",
        "apodo": "El Sojero",
        "fundado": 2011,
        "estadio": "Estadio Ofelia Rosenzuaig",
        "direccion": "Av. Carlos Arroyo 500, Carlos Casares",
        "ciudad": "Carlos Casares, Buenos Aires",
        "division": "Primera Nacional",
        "sitio": "https://clubagropecuario.com",
    },
    "Atlanta": {
        "nombre": "Club Atlético Atlanta",
        "apodo": "El Bohemio",
        "fundado": 1904,
        "estadio": "Estadio Don León Kolbowsky",
        "direccion": "Humboldt 374, Villa Crespo",
        "ciudad": "Ciudad de Buenos Aires",
        "division": "Primera Nacional",
        "sitio": "https://caatlanta.com.ar",
    },
    "Atlético Rafaela": {
        "nombre": "Asociación Mutual Social y Deportiva Atlético de Rafaela",
        "apodo": "La Crema",
        "fundado": 1907,
        "estadio": "Estadio Nuevo Monumental",
        "direccion": "Urquiza y Primera Junta, Rafaela",
        "ciudad": "Rafaela, Santa Fe",
        "division": "Primera Nacional",
        "sitio": "https://atleticorafaela.com.ar",
    },
    "Chaco For Ever": {
        "nombre": "Club Atlético Chaco For Ever",
        "apodo": "El Negro",
        "fundado": 1913,
        "estadio": "Estadio Juan Alberto García",
        "estadioApodo": "El Gigante de la Avenida",
        "direccion": "Av. 9 de Julio 2222, Resistencia",
        "ciudad": "Resistencia, Chaco",
        "division": "Primera Nacional",
        "sitio": "https://chacoforever.club",
    },
    "Ciudad De Bolivar": {
        "nombre": "Club Ciudad de Bolívar",
        "apodo": "Águilas Celestes",
        "fundado": 2002,
        "estadio": "Estadio Municipal Eva Perón",
        "direccion": "Av. Cancio s/n, San Carlos de Bolívar",
        "ciudad": "San Carlos de Bolívar, Buenos Aires",
        "division": "Primera Nacional",
    },
    "Deportivo Madryn": {
        "nombre": "Club Social y Deportivo Madryn",
        "apodo": "El Aurinegro",
        "fundado": 1924,
        "estadio": "Estadio Abel Sastre",
        "estadioApodo": "El Coliseo del Golfo",
        "direccion": "Av. Kenneth Woodley y Av. Juan XXIII Norte, Puerto Madryn",
        "ciudad": "Puerto Madryn, Chubut",
        "division": "Primera Nacional",
        "sitio": "https://deportivomadryn.com",
    },
    "Deportivo Maipú": {
        "nombre": "Club Deportivo Maipú",
        "apodo": "El Cruzado",
        "fundado": 1927,
        "estadio": "Estadio Omar Higinio Sperdutti",
        "direccion": "Vergara y Mercedes Tomasa de San Martín, Maipú",
        "ciudad": "Maipú, Mendoza",
        "division": "Primera Nacional",
        "sitio": "https://deportivomaipu.com",
    },
    "Deportivo Morón": {
        "nombre": "Club Deportivo Morón",
        "apodo": "El Gallo",
        "fundado": 1947,
        "estadio": "Estadio Nuevo Francisco Urbano",
        "capacidad": 32000,
        "direccion": "Monseñor Enrique Angelelli entre Pasteur y Vucetich, Morón",
        "ciudad": "Morón, Buenos Aires",
        "division": "Primera Nacional",
        # El dominio viejo, clubdeportivomoron.com.ar, está secuestrado y
        # redirige a un sitio de casino. Wikipedia todavía lo cita.
        "sitio": "https://deportivomoron.com.ar",
    },
    "Estudiantes": {
        # El de Caseros. En Primera Nacional "Estudiantes" a secas es éste,
        # y no el de La Plata: por eso no está en el índice de nombres.
        "nombre": "Club Atlético Estudiantes",
        "apodo": "Los Matadores",
        "fundado": 1898,
        "estadio": "Estadio Ciudad de Caseros",
        "capacidad": 16740,
        "direccion": "Av. Justo José de Urquiza, Caseros",
        "ciudad": "Caseros, Buenos Aires",
        "division": "Primera Nacional",
        # Sin sitio a propósito: el oficial está comprometido con spam de
        # apuestas inyectado en el WordPress. Ver DUDOSOS.md.
    },
    "Gimnasia de Jujuy": {
        "nombre": "Club Atlético Gimnasia y Esgrima de Jujuy",
        "apodo": "El Lobo",
        "fundado": 1931,
        "estadio": "Estadio 23 de Agosto",
        "capacidad": 24000,
        "direccion": "Av. El Éxodo y Santa Bárbara, San Salvador de Jujuy",
        "ciudad": "San Salvador de Jujuy, Jujuy",
        "division": "Primera Nacional",
        "sitio": "https://www.gyejoficial.com.ar",
    },
    "Gimnasia y Tiro": {
        "nombre": "Club de Gimnasia y Tiro",
        "apodo": "El Albo",
        "fundado": 1902,
        "estadio": "Estadio El Gigante del Norte",
        "capacidad": 24300,
        "direccion": "Leguizamón y Vicente López, Salta",
        "ciudad": "Salta, Salta",
        "division": "Primera Nacional",
    },
    "Godoy Cruz": {
        "nombre": "Club Deportivo Godoy Cruz Antonio Tomba",
        "apodo": "El Tomba",
        "fundado": 1921,
        "estadio": "Estadio Feliciano Gambarte",
        "estadioApodo": "La Bodega",
        "direccion": "Balcarce 477, Godoy Cruz",
        "ciudad": "Godoy Cruz, Mendoza",
        "division": "Primera Nacional",
        "sitio": "https://clubgodoycruz.com.ar",
    },
    "Midland": {
        "nombre": "Club Atlético Ferrocarril Midland",
        "apodo": "El Funebrero",
        "fundado": 1914,
        "estadio": "Estadio Ciudad de Libertad",
        "direccion": "Av. Eva Perón entre Viamonte y Padilla, Libertad",
        "ciudad": "Libertad, Merlo, Buenos Aires",
        "division": "Primera Nacional",
        "sitio": "https://ferrocarrilmidland.com",
    },
    "San Martín San Juan": {
        "nombre": "Club Atlético San Martín",
        "apodo": "El Santo",
        "fundado": 1907,
        "estadio": "Estadio Ingeniero Hilario Sánchez",
        "capacidad": 25500,
        "direccion": "Mendoza 1164 Norte, San Juan",
        "ciudad": "San Juan, San Juan",
        "division": "Primera Nacional",
        "sitio": "https://www.casanmartinsj.com",
    },
    "San Martín Tucumán": {
        "nombre": "Club Atlético San Martín",
        "apodo": "El Santo",
        "fundado": 1909,
        "estadio": "Estadio La Ciudadela",
        "capacidad": 30250,
        "direccion": "Simón Bolívar 1960, San Miguel de Tucumán",
        "ciudad": "San Miguel de Tucumán, Tucumán",
        "division": "Primera Nacional",
        # Ojo: el .com (sin .ar) es el WordPress viejo y tiene publicidad
        # de casino inyectada. El bueno es éste.
        "sitio": "https://clubatleticosanmartin.com.ar",
    },
    "Temperley": {
        "nombre": "Club Atlético Temperley",
        "apodo": "El Gasolero",
        "fundado": 1912,
        "estadio": "Estadio Alfredo Martín Beranger",
        "estadioApodo": "El Teatro de Turdera",
        "direccion": "Av. 9 de Julio 360, Temperley",
        "ciudad": "Temperley, Lomas de Zamora, Buenos Aires",
        "division": "Primera Nacional",
        "sitio": "https://temperley.org.ar",
    },
    "Tristan Suárez": {
        "nombre": "Club Tristán Suárez",
        "apodo": "El Lechero",
        "fundado": 1929,
        "estadio": "Estadio 20 de Octubre",
        "direccion": "Remedios de Escalada 170, Tristán Suárez",
        "ciudad": "Tristán Suárez, Ezeiza, Buenos Aires",
        "division": "Primera Nacional",
        "sitio": "https://clubtsuarez.com.ar",
    },
    "San Miguel": {
        "nombre": "Club Atlético San Miguel",
        "apodo": "El Trueno Verde",
        "fundado": 1922,
        "estadio": "Estadio Malvinas Argentinas",
        "direccion": "José León Suárez 2828, Los Polvorines",
        "ciudad": "Los Polvorines, Buenos Aires",
        "division": "Primera Nacional",
        "sitio": "https://clubatleticosanmiguel.com.ar",
    },

    # ── Primera B Metropolitana ─────────────────────────────────────────
    "Argentino Merlo": {
        "nombre": "Club Atlético Argentino",
        "apodo": "La Academia",
        "fundado": 1906,
        "estadio": "Estadio Juan Carlos Brieva",
        "capacidad": 11000,
        "direccion": "Antezana y Pergamino, Merlo Norte",
        "ciudad": "Merlo, Buenos Aires",
        "division": "Primera B Metropolitana",
    },
    "Camioneros": {
        "nombre": "Club Atlético Social y Deportivo Camioneros",
        "apodo": "El Camión",
        "fundado": 2009,
        "estadio": "Estadio Hugo Moyano",
        "direccion": "Camino de Cintura 6300, Nueve de Abril",
        "ciudad": "Nueve de Abril, Esteban Echeverría, Buenos Aires",
        "division": "Primera B Metropolitana",
        # El sitio oficial sólo anda por HTTP, sin cifrar. Cuando lo pasen
        # a HTTPS se agrega.
    },
    "Deportivo Armenio": {
        "nombre": "Club Deportivo Armenio",
        "apodo": "El Tricolor",
        "fundado": 1962,
        "estadio": "Estadio República de Armenia",
        "direccion": "Ruta Provincial 26 y Quintana, Ingeniero Maschwitz",
        "ciudad": "Ingeniero Maschwitz, Escobar, Buenos Aires",
        "division": "Primera B Metropolitana",
    },
    "Ituzaingó": {
        "nombre": "Club Atlético Ituzaingó",
        "apodo": "El León",
        "fundado": 1912,
        "estadio": "Estadio Carlos Alberto Sacaan",
        "direccion": "Mariano Acosta y General Pacheco, Ituzaingó",
        "ciudad": "Ituzaingó, Buenos Aires",
        "division": "Primera B Metropolitana",
    },
    "Real Pilar": {
        "nombre": "Real Pilar Fútbol Club",
        "fundado": 2017,
        "estadio": "Estadio Municipal Carlos Barraza",
        "direccion": "Ruta Provincial 28 km 6, Pilar",
        "ciudad": "Pilar, Buenos Aires",
        "division": "Primera B Metropolitana",
        # Sin sitio: el dominio oficial está secuestrado y hoy sirve un
        # casino online. Ver DUDOSOS.md.
    },

    # ── Primera C ───────────────────────────────────────────────────────
    "Sportivo Barracas": {
        # Sin cancha propia desde 1942: juega de prestado y va cambiando de
        # estadio, así que no hay estadio ni capacidad que poner.
        "nombre": "Club Sportivo Barracas",
        "apodo": "El Arrabalero",
        "fundado": 1913,
        "ciudad": "Barracas, Ciudad de Buenos Aires",
        "division": "Primera C",
    },
    "Claypole": {
        "nombre": "Club Atlético Claypole",
        "apodo": "El Tambero",
        "fundado": 1923,
        "estadio": "Estadio Rodolfo Vicente Capocasa",
        "direccion": "Av. Pedro Lacaze y Pedro Agrelo, Claypole",
        "ciudad": "Claypole, Almirante Brown, Buenos Aires",
        "division": "Primera C",
        "sitio": "https://www.clubclaypole.com.ar",
    },

    # ── Torneo Federal A ────────────────────────────────────────────────
    "Argentino Monte Maíz": {
        "nombre": "Club Deportivo Argentino",
        "apodo": "El Raya",
        "fundado": 1925,
        "estadio": "Estadio Modesto Marrone",
        "capacidad": 5500,
        "direccion": "Formosa s/n, Monte Maíz",
        "ciudad": "Monte Maíz, Córdoba",
        "division": "Torneo Federal A",
        "sitio": "https://argentinocrece.com.ar",
    },
    "Atenas Río Cuarto": {
        "nombre": "Club Sportivo y Biblioteca Atenas",
        "apodo": "El Albo",
        "fundado": 1916,
        "estadio": "Estadio 9 de Julio",
        "capacidad": 7000,
        "direccion": "Av. Cabrera y Av. Guillermo Marconi, Río Cuarto",
        "ciudad": "Río Cuarto, Córdoba",
        "division": "Torneo Federal A",
        "sitio": "https://csybatenas.com",
    },
    "CSCyD Gimnasia y Esgrima (Chivilcoy)": {
        "nombre": "Club Social, Cultural y Deportivo Gimnasia y Esgrima",
        "apodo": "El Lobo",
        "fundado": 1916,
        "estadio": "Estadio José María Paz",
        "capacidad": 2000,
        "direccion": "Av. Antonio De Tomaso y Felipe Varela, Chivilcoy",
        "ciudad": "Chivilcoy, Buenos Aires",
        "division": "Torneo Federal A",
        # Sin sitio: el dominio que aparecía atribuido a este club es en
        # realidad el de Gimnasia y Esgrima La Plata. Ver DUDOSOS.md.
    },
    "Deportivo Rincón": {
        "nombre": "Club Deportivo Rincón",
        "apodo": "El León",
        "fundado": 2012,
        "estadio": "Estadio Elías Moisés Gómez",
        "ciudad": "Rincón de los Sauces, Neuquén",
        "division": "Torneo Federal A",
        # El sitio existe pero sólo anda por HTTP y está abandonado desde
        # 2024, con contenido de relleno de la plantilla sin reemplazar.
    },
    "Olimpo": {
        "nombre": "Club Olimpo",
        "apodo": "El Aurinegro",
        "fundado": 1910,
        "estadio": "Estadio Roberto Natalio Carminatti",
        "capacidad": 18000,
        "direccion": "Ángel Brunel 11, Bahía Blanca",
        "ciudad": "Bahía Blanca, Buenos Aires",
        "division": "Torneo Federal A",
        "sitio": "https://www.clubolimpo.com.ar",
    },
    "San Martín de Formosa": {
        "nombre": "Club Sportivo General San Martín",
        "apodo": "El Franjeado",
        "fundado": 1941,
        "estadio": "Estadio 17 de Octubre",
        "capacidad": 2000,
        "direccion": "José María Amor y Obispo Scozzina, Formosa",
        "ciudad": "Formosa, Formosa",
        "division": "Torneo Federal A",
    },
    "Sportivo Belgrano": {
        "nombre": "Club Sportivo Belgrano",
        "apodo": "La Verde",
        "fundado": 1914,
        "estadio": "Estadio Juan Pablo Francia",
        "capacidad": 15000,
        "direccion": "Av. Rosario de Santa Fe 1459, San Francisco",
        "ciudad": "San Francisco, Córdoba",
        "division": "Torneo Federal A",
        "sitio": "https://sportivobelgrano.com.ar",
    },
    "Sarmiento De La Banda": {
        "nombre": "Club Atlético Sarmiento",
        "apodo": "El Profe",
        "fundado": 1909,
        "estadio": "Estadio Ciudad de La Banda",
        "direccion": "Av. del Libertador y Soler, La Banda",
        "ciudad": "La Banda, Santiago del Estero",
        "division": "Torneo Federal A",
    },
}


# ── Capacidad y trayectoria, de Wikipedia en español ─────────────────────
#
# Va aparte del bloque de arriba a propósito: son de una sola fuente, y así
# se ve de dónde salió cada cosa. La capacidad la buscamos ahí porque en el
# ascenso argentino no hay dos fuentes que coincidan, y una sola fuente
# consistente y citable es mejor que el hueco.
#
# `temporadas` es cuántas jugó el club en cada categoría en toda su
# historia. Tiene una trampa que hay que conocer: **la "Primera B" anterior
# a 1986 era la Segunda División de su época y NO es la Primera Nacional**.
# Contarlas juntas le sumaba a Temperley 50 temporadas de Primera Nacional
# que no existieron. Todas ésas quedaron afuera. Lo mismo con el Torneo
# Regional y el del Interior, que no equivalen a nada de lo de hoy.
#
# El Torneo Argentino A sí es el antecesor directo del Federal A, así que
# se suman.
#
# Donde Wikipedia da un total por división sin decir de qué torneo
# —"Tercera División: 38"— no se cargó nada: adivinar a qué categoría
# corresponde es exactamente cómo se llena una ficha de datos falsos.
_WIKIPEDIA = {
    "Acassuso": (1500, {"Primera División": 2, "Primera B Metropolitana": 16,
                        "Primera C": 16}),
    "Agropecuario": (8000, {"Primera Nacional": 8, "Torneo Federal A": 1}),
    "Argentino Merlo": (11000, {"Primera B Metropolitana": 3, "Primera C": 34,
                                "Primera D": 14}),
    "Argentino Monte Maíz": (5500, {"Torneo Federal A": 4}),
    "Atenas Río Cuarto": (7000, {"Torneo Federal A": 2}),
    "Atlanta": (18000, {"Primera División": 64, "Primera Nacional": 13,
                        "Primera B Metropolitana": 28}),
    "Atlético Rafaela": (16500, {"Primera División": 8, "Primera Nacional": 28,
                                 "Torneo Federal A": 1}),
    "Camioneros": (5000, {"Primera B Metropolitana": 1, "Primera C": 1,
                          "Torneo Federal A": 6}),
    "Chaco For Ever": (25000, {"Primera División": 8, "Primera Nacional": 12,
                               "Torneo Federal A": 13}),
    "Ciudad De Bolivar": (4000, {"Primera Nacional": 1, "Torneo Federal A": 5}),
    "Claypole": (4000, {"Primera C": 15}),
    "CSCyD Gimnasia y Esgrima (Chivilcoy)": (3000, None),
    "Deportivo Armenio": (8000, {"Primera División": 2, "Primera Nacional": 2}),
    "Deportivo Madryn": (8000, {"Primera Nacional": 4, "Torneo Federal A": 9}),
    "Deportivo Maipú": (8000, {"Primera Nacional": 9}),
    "Deportivo Morón": (32350, {"Primera División": 1, "Primera Nacional": 19,
                                "Primera B Metropolitana": 22, "Primera C": 3}),
    "Deportivo Rincón": (400, {"Torneo Federal A": 2}),
    "Estudiantes": (16740, {"Primera División": 32, "Primera Nacional": 11,
                            "Primera B Metropolitana": 30, "Primera C": 15,
                            "Primera D": 4}),
    "Gimnasia de Jujuy": (24000, {"Primera División": 18,
                                  "Primera Nacional": 25}),
    "Gimnasia y Tiro": (25000, {"Primera División": 4, "Primera Nacional": 7,
                                "Torneo Federal A": 17}),
    "Godoy Cruz": (24000, {"Primera División": 21, "Primera Nacional": 13}),
    "Ituzaingó": (5470, {"Primera Nacional": 2, "Primera B Metropolitana": 8,
                         "Primera C": 25, "Primera D": 32}),
    # Wikipedia se contradice: el artículo del estadio quedó en 4.000 y el
    # del club dice 11.000 después de la ampliación de 2023. Va el nuevo.
    "Midland": (11000, {"Primera Nacional": 1, "Primera B Metropolitana": 3,
                        "Primera C": 35, "Primera D": 29}),
    # Sólo Primera: el resto lo da como totales por división, sin decir de
    # qué torneo, y mezcla el Torneo del Interior con el Federal A.
    "Olimpo": (18000, {"Primera División": 14}),
    "Real Pilar": (10000, {"Primera B Metropolitana": 1, "Primera C": 7,
                           "Primera D": 2}),
    "San Martín de Formosa": (3000, None),
    "San Martín San Juan": (19000, {"Primera División": 10,
                                    "Primera Nacional": 25}),
    "San Martín Tucumán": (30250, {"Primera División": 4}),
    "San Miguel": (9044, {"Primera Nacional": 7, "Primera B Metropolitana": 20,
                          "Primera C": 20, "Primera D": 4}),
    "Sarmiento De La Banda": (8000, {"Torneo Federal A": 3}),
    # Sin estadio propio desde 1942: no hay capacidad que poner.
    "Sportivo Barracas": (None, {"Primera División": 18, "Primera C": 13,
                                 "Primera D": 43}),
    "Sportivo Belgrano": (15500, {"Primera Nacional": 3,
                                  "Torneo Federal A": 14}),
    # Acá también se contradice: la ficha del estadio dice 26.500 y su
    # propio texto dice 18.000 "en 2026". Va el que tiene fecha.
    "Temperley": (18000, {"Primera División": 19, "Primera Nacional": 13,
                          "Primera B Metropolitana": 19, "Primera C": 2}),
    "Tristan Suárez": (7500, {"Primera Nacional": 5,
                              "Primera B Metropolitana": 27, "Primera C": 20,
                              "Primera D": 12}),
}

# ── El clásico rival ─────────────────────────────────────────────────────
#
# (rival, cómo se llama la rivalidad). El nombre va en None cuando la
# rivalidad no tiene uno propio y consagrado: "el clásico de tal lugar" es
# una descripción, no un nombre, y ponerlo como si lo fuera sería inventar.
#
# Seis clubes no tienen clásico y eso también es un dato: Agropecuario,
# Camioneros, Ciudad de Bolívar, Deportivo Rincón y Real Pilar son
# demasiado nuevos —el más viejo es de 2002— y Deportivo Armenio no tiene
# arraigo barrial: se fundó en CABA, jugó de prestado treinta años y recién
# tuvo cancha propia en Escobar en 1992. Su artículo habla de "enemistad"
# con Fénix y Villa Dálmine, nunca de clásico.
CLASICOS = {
    "Acassuso": ("Central Ballester", None),
    "Argentino Merlo": ("Deportivo Merlo", "Clásico de Merlo"),
    "Argentino Monte Maíz": ("Atlético Lambert", "Clásico de Monte Maíz"),
    "Atenas Río Cuarto": ("Estudiantes de Río Cuarto", "Clásico Riocuartense"),
    "Atlanta": ("Chacarita Juniors", "Clásico de Villa Crespo"),
    "Atlético Rafaela": ("9 de Julio de Rafaela", "Clásico Rafaelino"),
    "Chaco For Ever": ("Sarmiento de Resistencia", "Clásico Chaqueño"),
    "Claypole": ("San Martín de Burzaco", "Clásico de Almirante Brown"),
    "CSCyD Gimnasia y Esgrima (Chivilcoy)": ("Independiente de Chivilcoy",
                                             "Clásico de Chivilcoy"),
    "Deportivo Madryn": ("Guillermo Brown", "Clásico del Golfo"),
    "Deportivo Maipú": ("Gutiérrez Sport Club", "Clásico Maipucino"),
    "Deportivo Morón": ("Almirante Brown", "Clásico del Oeste"),
    "Estudiantes": ("Almagro", "Clásico de Tres de Febrero"),
    "Gimnasia de Jujuy": ("Altos Hornos Zapla", "Clásico Jujeño"),
    "Gimnasia y Tiro": ("Juventud Antoniana", "Viejo Clásico Salteño"),
    # El histórico es Andes Talleres, que no se juega desde 1993. Y el
    # nombre "Clásico Mendocino" es de Gimnasia y Esgrima contra
    # Independiente Rivadavia, no de éste: por eso va sin nombre.
    "Godoy Cruz": ("Independiente Rivadavia", None),
    "Ituzaingó": ("Midland", None),
    "Midland": ("Ituzaingó", None),
    "Olimpo": ("Villa Mitre", "Clásico Bahiense"),
    "San Martín San Juan": ("Sportivo Desamparados", "Clásico Sanjuanino"),
    "San Martín Tucumán": ("Atlético Tucumán", "Clásico Tucumano"),
    "San Miguel": ("Colegiales", None),
    "Sarmiento De La Banda": ("Central Argentino de La Banda",
                              "Clásico Bandeño"),
    "Sportivo Barracas": ("Barracas Central", "Clásico Barraqueño"),
    "Sportivo Belgrano": ("Antártida Argentina", None),
    "Temperley": ("Los Andes", "Clásico de Lomas"),
    "Tristan Suárez": ("Brown de Adrogué", "Clásico Sureño"),
    # San Martín de Formosa queda afuera a propósito: hay tres candidatos y
    # las fuentes no coinciden. Wikipedia dice 1º de Mayo, el artículo de
    # Sportivo Patria se adjudica el "Clásico Formoseño", y la prensa del
    # Federal A se lo da a Sol de América. Con tres respuestas distintas,
    # ninguna.
}

for _n, (_riv, _como) in CLASICOS.items():
    CLUBES[_n]["clasico"] = _riv
    if _como:
        CLUBES[_n]["clasicoNombre"] = _como

# Los estadios que están en obra ahora mismo: la cifra de Wikipedia es la
# de antes de la reforma y va a quedar corta.
# Los clásicos de los clubes de Primera. Van acá y no en `CLUBES` porque
# esos clubes tienen su ficha en otro lado; esto es sólo el dato del
# rival, que el servidor pega encima.
#
# Están los que nadie discute. Faltan a propósito los que sí se discuten
# —el de Argentinos, el de Defensa, el de Barracas— porque poner un rival
# equivocado en la pantalla de un club es peor que no poner ninguno. Se
# van agregando cuando se puedan confirmar.
CLASICOS_PRIMERA = {
    "Boca Juniors": ("River Plate", "Superclásico"),
    "River Plate": ("Boca Juniors", "Superclásico"),
    "Racing": ("Independiente", "Clásico de Avellaneda"),
    "Independiente": ("Racing", "Clásico de Avellaneda"),
    "San Lorenzo": ("Huracán", "Clásico de Boedo y Parque Patricios"),
    "Huracán": ("San Lorenzo", "Clásico de Boedo y Parque Patricios"),
    "Estudiantes (LP)": ("Gimnasia y Esgrima (LP)", "Clásico platense"),
    "Gimnasia y Esgrima (LP)": ("Estudiantes (LP)", "Clásico platense"),
    "Newell's Old Boys": ("Rosario Central", "Clásico rosarino"),
    "Rosario Central": ("Newell's Old Boys", "Clásico rosarino"),
    "Lanús": ("Banfield", "Clásico del Sur"),
    "Banfield": ("Lanús", "Clásico del Sur"),
    "Talleres (C)": ("Belgrano", "Clásico cordobés"),
    "Belgrano": ("Talleres (C)", "Clásico cordobés"),
    "Instituto": ("Belgrano", "Clásico cordobés"),
    "Atlético Tucumán": ("San Martín Tucumán", "Clásico tucumano"),
    # El clásico mendocino es Gimnasia contra Independiente Rivadavia, no
    # Godoy Cruz contra Independiente Rivadavia: salió al verificar los
    # historiales. El rival clásico de Godoy Cruz es Andes Talleres, que
    # no juega Primera, así que Godoy Cruz queda sin clásico acá.
    "Independiente Rivadavia": ("Gimnasia y Esgrima (M)", "Clásico mendocino"),
    "Gimnasia y Esgrima (M)": ("Independiente Rivadavia", "Clásico mendocino"),
    "Unión": ("Colón", "Clásico santafesino"),
    "Aldosivi": ("Alvarado", "Clásico marplatense"),
    "Vélez Sarsfield": ("Ferro Carril Oeste", "Clásico del Oeste"),
    "Platense": ("Tigre", "Clásico de la zona norte"),
    "Tigre": ("Platense", "Clásico de la zona norte"),
}

EN_OBRA = {"Godoy Cruz", "Deportivo Madryn", "Ciudad De Bolivar",
           "Deportivo Rincón", "Sarmiento De La Banda"}

for _n, (_cap, _temp) in _WIKIPEDIA.items():
    if _cap:
        CLUBES[_n]["capacidad"] = _cap
    if _temp:
        CLUBES[_n]["temporadas"] = _temp

