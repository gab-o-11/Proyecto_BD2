from config import PALABRAS_CHUNK, SOLAPAMIENTO

MIN_PALABRAS_ULTIMO = 60


def partir(texto, tamano=PALABRAS_CHUNK, solapamiento=SOLAPAMIENTO):
    palabras = texto.split()
    if not palabras:
        return []
    paso = tamano - solapamiento
    fragmentos = []
    inicio = 0
    while inicio < len(palabras):
        fin = min(inicio + tamano, len(palabras))
        fragmentos.append(palabras[inicio:fin])
        if fin == len(palabras):
            break
        inicio += paso
    if len(fragmentos) > 1 and len(fragmentos[-1]) - solapamiento < MIN_PALABRAS_ULTIMO:
        ultimo = fragmentos.pop()
        fragmentos[-1] = fragmentos[-1] + ultimo[solapamiento:]
    textos = []
    for fragmento in fragmentos:
        textos.append(" ".join(fragmento))
    return textos
