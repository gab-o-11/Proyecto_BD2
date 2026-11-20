import pyarrow.parquet as pq


def persona_de(archivo):
    return archivo.rsplit("_", 1)[0]


def nombre_visible(persona):
    return " ".join(persona.replace("_", " ").split())


def leer(ruta):
    tabla = pq.read_table(ruta, columns=["filename", "image"])
    archivos = tabla.column("filename").to_pylist()
    imagenes = tabla.column("image").to_pylist()
    fotos = []
    for archivo, imagen in zip(archivos, imagenes):
        fotos.append({"archivo": archivo, "persona": persona_de(archivo), "datos": imagen["bytes"]})
    fotos.sort(key=lambda foto: foto["archivo"])
    return fotos
