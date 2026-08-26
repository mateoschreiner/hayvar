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
