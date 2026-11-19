import os

from openai import OpenAI

from config import ESFUERZO_LLM, MODELO_LLM

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("falta OPENAI_API_KEY en rag/.env")
        _cliente = OpenAI()
    return _cliente


def estructurado(instrucciones, entrada, formato, esfuerzo="none"):
    respuesta = cliente().responses.parse(
        model=MODELO_LLM,
        instructions=instrucciones,
        input=entrada,
        text_format=formato,
        reasoning={"effort": esfuerzo},
    )
    return respuesta.output_parsed


def en_vivo(instrucciones, mensajes, esfuerzo=ESFUERZO_LLM):
    with cliente().responses.stream(
        model=MODELO_LLM,
        instructions=instrucciones,
        input=mensajes,
        reasoning={"effort": esfuerzo},
    ) as flujo:
        for evento in flujo:
            if evento.type == "response.output_text.delta":
                yield evento.delta
        final = flujo.get_final_response()
    uso = final.usage
    if uso is not None:
        yield {"entrada": uso.input_tokens, "salida": uso.output_tokens}
