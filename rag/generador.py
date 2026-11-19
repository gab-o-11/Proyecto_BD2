import llm

INSTRUCCIONES = """Eres un asistente que responde preguntas sobre artículos científicos de revistas
latinoamericanas y españolas indexadas en SciELO.

Reglas:
- Responde SOLO con la información de los fragmentos dentro de <fuentes>. No uses conocimiento propio.
- Cita cada afirmación con el número del fragmento entre corchetes, por ejemplo [1] o [2][4].
- Si los fragmentos no contienen la respuesta, dilo claramente y sugiere cómo reformular la pregunta.
  No inventes datos, cifras ni autores.
- Si los fragmentos vienen de artículos distintos que se contradicen, señálalo.
- Responde en español, de forma clara y breve (uno a tres párrafos), salvo que pidan más detalle."""

MAX_TURNOS_PREVIOS = 6


def describir_fuente(fuente):
    articulo = fuente["articulo"]
    partes = []
    if articulo.get("titulo"):
        partes.append(articulo["titulo"])
    if articulo.get("autores"):
        partes.append(articulo["autores"])
    referencia = []
    if articulo.get("revista"):
        referencia.append(articulo["revista"])
    if articulo.get("anio"):
        referencia.append(str(articulo["anio"]))
    if referencia:
        partes.append(", ".join(referencia))
    cabecera = " — ".join(partes) if partes else "Artículo sin metadata"
    return f"[{fuente['numero']}] {cabecera}\n{fuente['texto']}"


def armar_entrada(mensajes, fuentes):
    entrada = []
    previos = mensajes[:-1][-MAX_TURNOS_PREVIOS:]
    for mensaje in previos:
        rol = "user" if mensaje["rol"] == "usuario" else "assistant"
        entrada.append({"role": rol, "content": mensaje["contenido"]})
    bloques = []
    for fuente in fuentes:
        bloques.append(describir_fuente(fuente))
    contexto = "\n\n".join(bloques) if bloques else "(no se encontraron fragmentos)"
    pregunta = mensajes[-1]["contenido"]
    entrada.append({"role": "user", "content": f"<fuentes>\n{contexto}\n</fuentes>\n\nPregunta: {pregunta}"})
    return entrada


def responder(mensajes, fuentes):
    yield from llm.en_vivo(INSTRUCCIONES, armar_entrada(mensajes, fuentes))
