# Lo que quedó sin confirmar

Copa Argentina 2026 · 27 de agosto de 2026

Cargué 30 clubes en `fichas.py`. Esto es lo que **no** cargué y por qué,
para poder completarlo con una fuente mejor. La regla fue: si dos fuentes
dan números que difieren más de un 20%, o hay una sola fuente floja, va
vacío. Un dato equivocado se lee como un dato; un hueco se lee como un
hueco.

---

## 1. Faltan 6 clubes

La competencia tiene 36 clubes fuera de los 30 de Primera. Saqué la lista
de la captura de `/copa-argentina/equipos`, que se cortaba en la S, así
que **faltan los 6 que van después de "Sarmiento De La Banda"**.

Por las cuentas de AFA (15 Primera Nacional, 5 Primera B, 4 Primera C, 10
Federal A) los que faltan son **3 de Primera C y 3 del Federal A**.

Pasame esos seis nombres tal como los muestra la página y los completo.

---

## 2. Capacidad: 18 de 30 sin cargar

Es el dato peor documentado del ascenso argentino. Para el mismo estadio
se encuentran cifras que difieren al doble, y varios están en obra ahora
mismo. Éstas son las que encontré, por si querés cerrarlas vos:

| Club | Lo que dice cada fuente | Mejor candidato |
|---|---|---|
| Acassuso | club 1.800 · Promiedos 800 | 1.800 (sitio oficial) |
| Atlanta | club 18.000 · Wikipedia 14.000 · estadiosdeargentina 11.000 | 18.000 (oficial, 2025) |
| Camioneros | 5.000 · 2.500 · 2.000 — y tribuna nueva en 2025 sin publicar | 5.000 |
| Claypole | 4.000 · 2.000 · 1.300 | 2.000 |
| Deportivo Armenio | Promiedos 10.500 · Wikipedia 8.000 · estadios 4.000 | 8.000 |
| Argentino de Merlo | *cargado 11.000*, fuente única | revisar |
| Agropecuario | 5.000 (tres fuentes) · Wikipedia 8.000/15.000 | 5.000 |
| Atlético Rafaela | 14.000 · 14.660 · 16.000 · 20.660 · 26.535 | 14.660 |
| Chaco For Ever | 23.000 · 25.000 · 30.500 | 25.000 |
| Ciudad de Bolívar | 4.000 · 3.300 | 3.300 |
| Deportivo Madryn | 8.000 · 12.000 · 25.000 — **en obra hacia 28.000** | esperar |
| Deportivo Maipú | 6.590 · 8.000 · 9.000 · 9.260 — obra en 2025 | 9.000 |
| Ituzaingó | 3.300 · 5.000 · 5.470 | 5.470 |
| Midland | club 11.000 · 9.000 · 7.000 · 6.000 | 11.000 (oficial) |
| Real Pilar | 7.000 · 8.500 · 10.000 | 8.500 |
| San Miguel | club 11.544 · 9.044 · 7.176 | 11.544 (oficial, dic-2025) |
| Godoy Cruz | 14.000 · 15.000 · 18.000 · 21.000 — **Gambarte en obra** | esperar |
| Sarmiento de La Banda | 5.000 · 6.000 · 8.000 — tribuna nueva en 2026 | esperar |
| Deportivo Rincón | 300 · 400 — remodelado para 2026, sin cifra nueva | esperar |

Las que **sí** cargué, con la fuente que las respalda: Deportivo Morón
32.000, Estudiantes de Caseros 16.740, Gimnasia de Jujuy 24.000, Gimnasia
y Tiro 24.300, Olimpo 18.000, San Martín de Formosa 2.000, San Martín de
San Juan 25.500, San Martín de Tucumán 30.250, Argentino de Monte Maíz
5.500, Atenas de Río Cuarto 7.000, Gimnasia de Chivilcoy 2.000, Argentino
de Merlo 11.000.

---

## 3. Sitios oficiales: 12 sin cargar

**Dominios secuestrados — no usar.** Los dos sirven hoy sitios de casino:

- `clubdeportivomoron.com.ar` — el viejo de Morón. **Wikipedia todavía lo
  cita como oficial.** El bueno es `deportivomoron.com.ar`, que sí cargué.
- `realpilarfutbolclub.com` — el de Real Pilar. Sirve un casino con links
  de afiliado. Real Pilar quedó sin sitio.

**Sitios oficiales con spam inyectado.**

- **Estudiantes de Caseros** (`caestudiantes.com.ar`): es el sitio real del
  club, pero el WordPress está comprometido y publica posts de apuestas y
  de trading mezclados con las noticias. No lo cargué. Si el club lo
  limpia, se agrega.
- **San Martín de Tucumán**: el `.com` (sin `.ar`) es un WordPress viejo
  con publicidad de casino inyectada. Cargué el `.com.ar`, que está sano.

**Sólo por HTTP, sin cifrar.** No los cargué porque mandar a alguien a una
página sin cifrar desde un link nuestro no está bueno. Cuando pongan
HTTPS se agregan:

- Camioneros — `clubcamioneros.com.ar/ladeportiva/`
- Deportivo Rincón — `deportivorincon.com.ar` (además abandonado desde
  2024, con contenido de relleno de la plantilla sin reemplazar)

**Caídos o inexistentes.** Argentino de Merlo, Ciudad de Bolívar,
Deportivo Armenio, Gimnasia y Tiro, Ituzaingó, Sarmiento de La Banda y San
Martín de Formosa no tienen sitio propio vigente: sólo redes sociales, que
no cargo.

**Un dato mal atribuido que corregí.** La investigación devolvió
`clubgimnasia.com.ar` como sitio de Gimnasia de Chivilcoy, y ese dominio
es de **Gimnasia y Esgrima La Plata**, que ya lo tenía cargado. Lo dejé
vacío.

---

## 4. Cosas sueltas para revisar

- **Real Pilar** quedó sin apodo. En la prensa aparece "El Monarca", pero
  no lo pude confirmar en ninguna fuente institucional.
- **Estudiantes de Caseros**: le puse "Los Matadores", que es como se
  llama a sí mismo en su web. "El Pincha" también le corresponde, pero es
  el mismo apodo que el de La Plata y en el sitio quedaría confuso.
- **San Martín de San Juan** juega varios partidos de local en el Estadio
  San Juan del Bicentenario, no en el Hilario Sánchez. La ficha dice el
  propio.
- **San Martín de Formosa**: Wikipedia dice que para partidos nacionales
  usa el Estadio Antonio Romero. El dato parece anterior a la
  reinauguración del 17 de Octubre en 2014, pero conviene mirarlo.
- **Direcciones sin altura**: doce estadios del interior no tienen número
  de calle en ninguna fuente, sólo la esquina. Quedaron con la esquina,
  que es lo que hay.
