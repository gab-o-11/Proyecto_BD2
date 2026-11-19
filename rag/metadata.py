from pydantic import BaseModel

import llm

INSTRUCCIONES = """Recibes el inicio de un artículo científico extraído de un PDF de SciELO.
Devuelve su título, sus autores y la revista donde se publicó.
- titulo: el título en el idioma original del artículo (normalmente español), sin la traducción al inglés.
- autores: nombres separados por "; ", sin números, letras de afiliación ni grados académicos.
- revista: el nombre de la revista tal como aparece, sin volumen, número ni páginas.
Si un dato no aparece en el texto, devuélvelo vacío. No inventes nada."""


class Metadata(BaseModel):
    titulo: str
    autores: str
    revista: str


def extraer(cabecera):
    resultado = llm.estructurado(INSTRUCCIONES, cabecera, Metadata)
    return {
        "titulo": resultado.titulo.strip(),
        "autores": resultado.autores.strip(),
        "revista": resultado.revista.strip(),
    }
