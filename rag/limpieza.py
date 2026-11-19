import re
import unicodedata

BANDA = 0.09
TOLERANCIA_Y = 4
MIN_PAGINAS_REPETIDAS = 2
NO_LETRAS = re.compile(r"[^a-zñ ]+")
ESPACIOS = re.compile(r"\s+")


def leer_palabras(contenido):
    palabras = []
    for linea in contenido.splitlines():
        campos = linea.split("\t")
        if len(campos) != 8 or not campos[0]:
            continue
        palabras.append({
            "texto": campos[0],
            "y": int(campos[2]),
            "alto": int(campos[6]),
            "pagina": int(campos[7]),
        })
    return palabras


def agrupar_lineas(palabras):
    lineas = []
    actual = None
    for palabra in palabras:
        nueva = (
            actual is None
            or palabra["pagina"] != actual["pagina"]
            or abs(palabra["y"] - actual["y"]) > TOLERANCIA_Y
        )
        if nueva:
            actual = {"pagina": palabra["pagina"], "y": palabra["y"], "alto": palabra["alto"], "palabras": []}
            lineas.append(actual)
        actual["palabras"].append(palabra["texto"])
    return lineas


def clave(linea):
    texto = " ".join(linea["palabras"]).lower()
    texto = unicodedata.normalize("NFD", texto)
    sin_tildes = []
    for caracter in texto:
        if unicodedata.category(caracter) != "Mn":
            sin_tildes.append(caracter)
    texto = NO_LETRAS.sub(" ", "".join(sin_tildes))
    return ESPACIOS.sub(" ", texto).strip()


def en_banda(linea):
    return linea["y"] <= linea["alto"] * BANDA or linea["y"] >= linea["alto"] * (1 - BANDA)


def unir(palabras):
    salida = []
    for palabra in palabras:
        if salida and salida[-1].endswith("-") and len(salida[-1]) > 1 and palabra[:1].islower():
            salida[-1] = salida[-1][:-1] + palabra
        else:
            salida.append(palabra)
    return " ".join(salida)


def limpiar(contenido):
    lineas = agrupar_lineas(leer_palabras(contenido))
    paginas_por_clave = {}
    for linea in lineas:
        if en_banda(linea):
            paginas_por_clave.setdefault(clave(linea), set()).add(linea["pagina"])
    palabras = []
    for linea in lineas:
        if en_banda(linea):
            llave = clave(linea)
            if llave == "" or len(paginas_por_clave[llave]) >= MIN_PAGINAS_REPETIDAS:
                continue
        palabras.extend(linea["palabras"])
    return unir(palabras)
