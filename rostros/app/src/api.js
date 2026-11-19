import Constants from 'expo-constants';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

function urlServicio() {
  if (process.env.EXPO_PUBLIC_ROSTROS_URL) {
    return process.env.EXPO_PUBLIC_ROSTROS_URL;
  }
  const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
  return `http://${host}:8200`;
}

export const URL_SERVICIO = urlServicio();

export function urlFoto(ruta) {
  return `${URL_SERVICIO}/fotos/${ruta}`;
}

export async function reducir(uri, ancho = 640) {
  const imagen = await ImageManipulator.manipulate(uri).resize({ width: ancho }).renderAsync();
  const resultado = await imagen.saveAsync({ compress: 0.7, format: SaveFormat.JPEG });
  return resultado.uri;
}

async function pedir(ruta, opciones = {}, limite = 15000) {
  const control = new AbortController();
  const temporizador = setTimeout(() => control.abort(), limite);
  try {
    const respuesta = await fetch(`${URL_SERVICIO}${ruta}`, { ...opciones, signal: control.signal });
    const datos = await respuesta.json();
    if (!respuesta.ok) {
      const error = new Error(datos.error ?? `el servicio respondió ${respuesta.status}`);
      error.datos = datos;
      throw error;
    }
    return datos;
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('el servicio tardó demasiado en responder');
    }
    if (error instanceof TypeError) {
      throw new Error(`no se pudo conectar con ${URL_SERVICIO}`);
    }
    throw error;
  } finally {
    clearTimeout(temporizador);
  }
}

function archivo(uri, nombre) {
  return { uri, name: nombre, type: 'image/jpeg' };
}

function formularioDeFotos(uris) {
  const formulario = new FormData();
  uris.forEach((uri, indice) => formulario.append('fotos', archivo(uri, `foto${indice + 1}.jpg`)));
  return formulario;
}

export function reconocer(uri, usarCache) {
  const formulario = new FormData();
  formulario.append('imagen', archivo(uri, 'cuadro.jpg'));
  return pedir(`/reconocer?cache=${usarCache}`, { method: 'POST', body: formulario }, 3000);
}

export function listarPersonas() {
  return pedir('/personas');
}

export function verPersona(id) {
  return pedir(`/personas/${id}`);
}

export function registrarPersona(nombre, uris) {
  const formulario = formularioDeFotos(uris);
  formulario.append('nombre', nombre.trim());
  return pedir('/personas', { method: 'POST', body: formulario }, 30000);
}

export function agregarFotos(id, uris) {
  return pedir(`/personas/${id}/fotos`, { method: 'POST', body: formularioDeFotos(uris) }, 30000);
}

export function eliminarPersona(id) {
  return pedir(`/personas/${id}`, { method: 'DELETE' });
}

export function eliminarRostro(id) {
  return pedir(`/rostros/${id}`, { method: 'DELETE' });
}
