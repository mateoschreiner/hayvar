# -*- coding: utf-8 -*-
"""
Busca nombres que no existen, antes de que exploten en producción.

Por qué existe
──────────────
Tres veces en una misma sesión escribí un nombre que no existía y las
tres veces se descubrió en pantalla y no en las pruebas:

  · `norm()` en el navegador, cuando la función se llama `slugTexto`.
    La previa no dibujaba las tablas y no había ningún error a la vista.
  · `escudosDe`, que nunca existió. Los escudos no aparecían.
  · `out["fechasDeEtapa"]` cuando el diccionario se llama `res`. Este
    reventó las cuatro copas y ninguna prueba lo vio, porque ninguna
    llamaba a esa función.

Es siempre el mismo error y siempre se escapa igual: Python no revisa los
nombres hasta que ejecuta la línea. Si esa línea está adentro de un `if`
que sólo se cumple en las copas, la prueba pasa en verde y el sitio se
cae.

Qué hace
────────
Recorre cada función y comprueba que todo nombre que se LEE exista en
algún lado: como variable local, como parámetro, en una función que la
contiene, como global del módulo, o como algo de Python. Lo que no está
en ninguno de esos lugares es un error seguro.

Qué NO hace
───────────
No mira atributos (`a.b`): para eso haría falta saber de qué tipo es `a`,
y eso ya es otro problema. Tampoco entiende `exec` ni `globals()`. Prefiere
callarse a inventar: se equivoca del lado de no avisar.
"""

import ast
import builtins


def _atados(nodo, adentro=False):
    """
    Los nombres que un nodo ATA, o sea que define.

    `adentro` dice si hay que meterse en las funciones anidadas. Para el
    cuerpo de una función no: sus variables son suyas. Pero el NOMBRE de
    la función anidada sí queda atado acá.
    """
    fuera = set()

    def ver(n):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)):
            fuera.add(n.name)
            if not adentro:
                return                       # su cuerpo es otro mundo
        elif isinstance(n, ast.Name) and isinstance(n.ctx,
                                                    (ast.Store, ast.Del)):
            fuera.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                fuera.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            fuera.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            fuera.update(n.names)
        elif isinstance(n, ast.Lambda):
            # Los parámetros de un lambda se suman al alcance de afuera.
            # Es de más —adentro del lambda nada más se ven— pero de más
            # sólo hace que deje pasar algo, y nunca que avise de algo
            # que está bien. Sin esto, cada `key=lambda x: ...` del
            # proyecto salía como error: doce de doce eran esto.
            fuera.update(_parametros(n))
        for hijo in ast.iter_child_nodes(n):
            ver(hijo)

    for hijo in ast.iter_child_nodes(nodo):
        ver(hijo)
    return fuera


def _parametros(fn):
    a = fn.args
    ns = {p.arg for p in a.args + a.kwonlyargs + getattr(a, "posonlyargs", [])}
    if a.vararg:
        ns.add(a.vararg.arg)
    if a.kwarg:
        ns.add(a.kwarg.arg)
    return ns


def _leidos(nodo):
    """Los nombres que se LEEN, sin entrar en las funciones anidadas."""
    fuera = []

    def ver(n, raiz=False):
        if not raiz and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef)):
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            fuera.append((n.id, n.lineno))
        for hijo in ast.iter_child_nodes(n):
            ver(hijo)

    for hijo in ast.iter_child_nodes(nodo):
        ver(hijo)
    return fuera


def revisar(codigo, archivo="<código>"):
    """
    Devuelve la lista de (archivo, línea, función, nombre) que no existen.

    Vacío quiere decir que está todo bien.
    """
    arbol = ast.parse(codigo, archivo)
    # Sólo lo que se define EN EL MÓDULO. `adentro=False` no se mete en el
    # cuerpo de las funciones, y eso es justamente el punto.
    #
    # La primera versión sí se metía —"por las dudas"— y con eso una
    # variable local de cualquier función pasaba por global. Como en
    # server.py hay veinte funciones con un `out = []` adentro, el revisor
    # daba por bueno el `out` de una función que no lo tenía: o sea que no
    # encontraba exactamente el error para el que fue escrito. Un
    # verificador que se cubre "por las dudas" deja de verificar.
    delModulo = _atados(arbol, adentro=False) | set(dir(builtins))
    malos = []

    def mirar(fn, deAfuera, camino):
        propios = _parametros(fn) | _atados(fn, adentro=False)
        # Y las variables de las funciones anidadas, que también ven las
        # de acá: se pasan hacia adentro.
        visibles = deAfuera | propios
        for nombre, linea in _leidos(fn):
            if nombre not in visibles:
                malos.append((archivo, linea, camino, nombre))
        for hijo in ast.iter_child_nodes(fn):
            for n in ast.walk(hijo):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    mirar(n, visibles, camino + " > " + n.name)

    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Sólo las de primer nivel: las anidadas las recorre `mirar`
            # con el alcance de la que las contiene.
            if any(n in ast.walk(o) and o is not n
                   for o in ast.walk(arbol)
                   if isinstance(o, (ast.FunctionDef, ast.AsyncFunctionDef))):
                continue
            mirar(n, delModulo, n.name)
    return malos


def revisar_archivos(rutas):
    """Lo mismo, sobre varios archivos."""
    malos = []
    for r in rutas:
        with open(r, encoding="utf-8") as f:
            malos += revisar(f.read(), r)
    return malos
