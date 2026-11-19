const estado = { mensajes: [], modo: "hibrido", ocupado: false };

const $mensajes = document.getElementById("mensajes");
const $fuentes = document.getElementById("fuentes");
const $tiempos = document.getElementById("tiempos");
const $formulario = document.getElementById("formulario");
const $pregunta = document.getElementById("pregunta");
const $enviar = document.getElementById("enviar");
const $pais = document.getElementById("pais");
const $k = document.getElementById("k");
const $estado = document.getElementById("estado");

const NOMBRES_MODO = { bm25: "BM25", vectorial: "Embeddings", hibrido: "Híbrido" };

function elemento(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto !== undefined) nodo.textContent = texto;
  return nodo;
}

function pintarConCitas(nodo, texto) {
  nodo.replaceChildren();
  const partes = texto.split(/(\[\d+\]|\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g);
  for (const parte of partes) {
    const cita = parte.match(/^\[(\d+)\]$/);
    const negrita = parte.match(/^\*\*([^*\n]+)\*\*$/);
    const cursiva = parte.match(/^\*([^*\n]+)\*$/);
    if (cita) {
      const marca = elemento("span", "cita", cita[1]);
      marca.title = "Ver fuente " + cita[1];
      marca.addEventListener("click", () => resaltarFuente(cita[1]));
      nodo.appendChild(marca);
    } else if (negrita) {
      nodo.appendChild(elemento("strong", "", negrita[1]));
    } else if (cursiva) {
      nodo.appendChild(elemento("em", "", cursiva[1]));
    } else if (parte) {
      nodo.appendChild(document.createTextNode(parte));
    }
  }
}

function resaltarFuente(numero) {
  for (const tarjeta of $fuentes.querySelectorAll(".fuente")) {
    const coincide = tarjeta.dataset.numero === String(numero);
    tarjeta.classList.toggle("resaltada", coincide);
    if (coincide) tarjeta.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function pintarFuentes(fuentes) {
  $fuentes.replaceChildren();
  if (!fuentes.length) {
    $fuentes.appendChild(elemento("p", "vacio", "No se recuperaron fragmentos."));
    return;
  }
  for (const fuente of fuentes) {
    const tarjeta = elemento("article", "fuente");
    tarjeta.dataset.numero = fuente.numero;
    const titulo = elemento("h3");
    titulo.appendChild(elemento("span", "cita", String(fuente.numero)));
    titulo.appendChild(elemento("span", "", fuente.titulo || "Artículo sin título"));
    tarjeta.appendChild(titulo);
    const detalle = [fuente.autores, fuente.revista, fuente.anio, fuente.pais].filter(Boolean).join(" · ");
    tarjeta.appendChild(elemento("div", "detalle", detalle));
    const etiquetas = elemento("div", "etiquetas");
    for (const [metodo, posicion] of Object.entries(fuente.posiciones || {})) {
      etiquetas.appendChild(elemento("span", "etiqueta", NOMBRES_MODO[metodo] + " #" + posicion));
    }
    etiquetas.appendChild(elemento("span", "etiqueta", "chunk " + fuente.orden));
    tarjeta.appendChild(etiquetas);
    tarjeta.appendChild(elemento("p", "", fuente.texto));
    const acciones = elemento("div", "acciones");
    const expandir = elemento("button", "", "Ver todo");
    expandir.type = "button";
    expandir.addEventListener("click", () => {
      tarjeta.classList.toggle("abierta");
      expandir.textContent = tarjeta.classList.contains("abierta") ? "Ver menos" : "Ver todo";
    });
    acciones.appendChild(expandir);
    if (fuente.url_pdf) {
      const enlace = elemento("a", "", "PDF original");
      enlace.href = fuente.url_pdf;
      enlace.target = "_blank";
      enlace.rel = "noopener";
      acciones.appendChild(enlace);
    }
    tarjeta.appendChild(acciones);
    $fuentes.appendChild(tarjeta);
  }
}

function agregarMensaje(rol, texto) {
  const bienvenida = $mensajes.querySelector(".bienvenida");
  if (bienvenida) bienvenida.remove();
  const nodo = elemento("div", "mensaje " + rol);
  const cuerpo = elemento("span", "cuerpo", texto);
  nodo.appendChild(cuerpo);
  $mensajes.appendChild(nodo);
  $mensajes.scrollTop = $mensajes.scrollHeight;
  return nodo;
}

function formatearTiempos(tiempos) {
  const partes = [];
  if (tiempos.recuperacion_ms != null) partes.push("búsqueda " + Math.round(tiempos.recuperacion_ms) + " ms");
  if (tiempos.primer_token_ms != null) partes.push("1.er token " + (tiempos.primer_token_ms / 1000).toFixed(1) + " s");
  if (tiempos.total_ms != null) partes.push("total " + (tiempos.total_ms / 1000).toFixed(1) + " s");
  return partes.join(" · ");
}

async function preguntar(texto) {
  if (estado.ocupado) return;
  estado.ocupado = true;
  $enviar.disabled = true;
  estado.mensajes.push({ rol: "usuario", contenido: texto });
  agregarMensaje("usuario", texto);
  const respuesta = agregarMensaje("asistente", "Buscando…");
  const cuerpo = respuesta.querySelector(".cuerpo");
  let acumulado = "";
  try {
    const peticion = await fetch("/api/preguntar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mensajes: estado.mensajes,
        modo: estado.modo,
        k: Number($k.value),
        filtros: { pais: $pais.value || null },
      }),
    });
    if (!peticion.ok) throw new Error("el servidor respondió " + peticion.status);
    const lector = peticion.body.getReader();
    const decodificador = new TextDecoder();
    let pendiente = "";
    while (true) {
      const { value, done } = await lector.read();
      if (done) break;
      pendiente += decodificador.decode(value, { stream: true });
      const lineas = pendiente.split("\n");
      pendiente = lineas.pop();
      for (const linea of lineas) {
        if (!linea.trim()) continue;
        const evento = JSON.parse(linea);
        if (evento.tipo === "fuentes") {
          pintarFuentes(evento.fuentes);
          $tiempos.textContent = formatearTiempos(evento.tiempos);
          cuerpo.textContent = "";
        } else if (evento.tipo === "texto") {
          acumulado += evento.delta;
          pintarConCitas(cuerpo, acumulado);
          $mensajes.scrollTop = $mensajes.scrollHeight;
        } else if (evento.tipo === "fin") {
          $tiempos.textContent = formatearTiempos(evento.tiempos);
          respuesta.appendChild(elemento("span", "meta", NOMBRES_MODO[estado.modo] + " · " + formatearTiempos(evento.tiempos)));
        } else if (evento.tipo === "error") {
          throw new Error(evento.mensaje);
        }
      }
    }
    estado.mensajes.push({ rol: "asistente", contenido: acumulado });
  } catch (error) {
    respuesta.classList.add("error");
    cuerpo.textContent = "Error: " + error.message;
    estado.mensajes.pop();
  } finally {
    estado.ocupado = false;
    $enviar.disabled = false;
    $pregunta.focus();
  }
}

$formulario.addEventListener("submit", (evento) => {
  evento.preventDefault();
  const texto = $pregunta.value.trim();
  if (!texto) return;
  $pregunta.value = "";
  preguntar(texto);
});

$pregunta.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter" && !evento.shiftKey) {
    evento.preventDefault();
    $formulario.requestSubmit();
  }
});

for (const boton of document.querySelectorAll(".segmentado button")) {
  boton.setAttribute("aria-checked", boton.classList.contains("activo"));
  boton.addEventListener("click", () => {
    estado.modo = boton.dataset.modo;
    for (const otro of document.querySelectorAll(".segmentado button")) {
      otro.classList.toggle("activo", otro === boton);
      otro.setAttribute("aria-checked", otro === boton);
    }
  });
}

for (const ejemplo of document.querySelectorAll(".ejemplos button")) {
  ejemplo.addEventListener("click", () => preguntar(ejemplo.textContent));
}

document.getElementById("nuevo").addEventListener("click", () => {
  estado.mensajes = [];
  location.reload();
});

async function cargarEstado() {
  try {
    const datos = await (await fetch("/api/estado")).json();
    if (!datos.motor) {
      $estado.textContent = "motor BD2 sin conexión";
      $estado.classList.add("mal");
      return;
    }
    $estado.textContent = datos.articulos + " artículos · " + datos.chunks + " chunks · " + datos.llm;
    const paises = await (await fetch("/api/paises")).json();
    for (const pais of paises) {
      const opcion = elemento("option", "", pais.nombre + " (" + pais.articulos + ")");
      opcion.value = pais.codigo;
      $pais.appendChild(opcion);
    }
  } catch (error) {
    $estado.textContent = "sin conexión";
    $estado.classList.add("mal");
  }
}

cargarEstado();
