def _ms(segundos):
    return segundos * 1000.0


def _buffers(nodo):
    if nodo.real is None:
        return None
    aciertos = nodo.real.io.aciertos()
    leidas = nodo.real.io.leidas()
    if aciertos == 0 and leidas == 0:
        return None
    partes = []
    if aciertos:
        partes.append("hit=" + str(aciertos))
    if leidas:
        partes.append("read=" + str(leidas))
    return "Buffers: shared " + " ".join(partes)


def _cabecera(nodo, analyze):
    texto = nodo.titulo()
    texto += "  (cost=%.2f..%.2f rows=%d width=%d)" % (
        nodo.costo_inicio, nodo.costo_total, nodo.filas_est, nodo.ancho
    )
    if analyze:
        if nodo.real is None:
            texto += " (never executed)"
        else:
            texto += " (actual time=%.3f..%.3f rows=%d loops=%d)" % (
                _ms(nodo.real.inicio), _ms(nodo.real.total), nodo.real.filas, nodo.real.loops
            )
    return texto


def _lineas_detalle(nodo, analyze):
    lineas = list(nodo.detalles())
    if analyze and nodo.real is not None:
        lineas.extend(nodo.detalles_reales())
        buffers = _buffers(nodo)
        if buffers is not None:
            lineas.append(buffers)
    return lineas


def a_texto(nodo, analyze, nivel=0):
    if nivel == 0:
        lineas = [_cabecera(nodo, analyze)]
        sangria = "  "
    else:
        lineas = [" " * (6 * nivel - 4) + "->  " + _cabecera(nodo, analyze)]
        sangria = " " * (6 * nivel + 2)
    for detalle in _lineas_detalle(nodo, analyze):
        lineas.append(sangria + detalle)
    for hijo in nodo.hijos:
        lineas.extend(a_texto(hijo, analyze, nivel + 1))
    return lineas


def a_dict(nodo, analyze):
    salida = {
        "node": nodo.tipo,
        "title": nodo.titulo(),
        "relation": nodo.relacion(),
        "index": nodo.indice(),
        "startupCost": round(nodo.costo_inicio, 2),
        "totalCost": round(nodo.costo_total, 2),
        "planRows": nodo.filas_est,
        "planWidth": nodo.ancho,
        "details": list(nodo.detalles()),
        "actual": None,
        "children": [],
    }
    if analyze and nodo.real is not None:
        salida["actual"] = {
            "startupMs": round(_ms(nodo.real.inicio), 3),
            "totalMs": round(_ms(nodo.real.total), 3),
            "rows": nodo.real.filas,
            "loops": nodo.real.loops,
            "sharedHit": nodo.real.io.aciertos(),
            "sharedRead": nodo.real.io.leidas(),
            "details": list(nodo.detalles_reales()),
        }
    for hijo in nodo.hijos:
        salida["children"].append(a_dict(hijo, analyze))
    return salida


def reporte(nodo, analyze, planificacion, ejecucion):
    lineas = a_texto(nodo, analyze)
    lineas.append("Planning Time: %.3f ms" % _ms(planificacion))
    if analyze:
        lineas.append("Execution Time: %.3f ms" % _ms(ejecucion))
    return {
        "analyze": analyze,
        "planningMs": round(_ms(planificacion), 3),
        "executionMs": round(_ms(ejecucion), 3) if analyze else None,
        "tree": a_dict(nodo, analyze),
        "text": lineas,
    }
