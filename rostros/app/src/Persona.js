import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { agregarFotos, eliminarPersona, eliminarRostro, urlFoto, verPersona } from './api';
import Boton from './Boton';
import Captura from './Captura';
import { colores } from './tema';

export default function Persona({ id, onVolver }) {
  const [persona, setPersona] = useState(null);
  const [error, setError] = useState(null);
  const [tomando, setTomando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setPersona(await verPersona(id));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function borrarFoto(foto) {
    try {
      const respuesta = await eliminarRostro(foto.id);
      if (respuesta.persona_eliminada) {
        onVolver();
      } else {
        cargar();
      }
    } catch (e) {
      setError(e.message);
    }
  }

  function confirmarFoto(foto) {
    const ultima = persona.fotos.length === 1;
    Alert.alert(
      ultima ? 'Eliminar persona' : 'Borrar foto',
      ultima ? `Es la última foto de ${persona.nombre}; se eliminará la persona.` : '¿Borrar esta foto?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Borrar', style: 'destructive', onPress: () => borrarFoto(foto) },
      ],
    );
  }

  function confirmarPersona() {
    Alert.alert('Eliminar persona', `¿Eliminar a ${persona.nombre} y todas sus fotos?`, [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'Eliminar',
        style: 'destructive',
        onPress: async () => {
          try {
            await eliminarPersona(id);
            onVolver();
          } catch (e) {
            setError(e.message);
          }
        },
      },
    ]);
  }

  async function agregar(uri) {
    setTomando(false);
    setOcupado(true);
    try {
      setPersona(await agregarFotos(id, [uri]));
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setOcupado(false);
    }
  }

  if (tomando) {
    return <Captura instruccion="Foto nueva: mira de frente" onFoto={agregar} onCancelar={() => setTomando(false)} />;
  }

  if (!persona) {
    return (
      <View style={estilos.centro}>
        {error ? <Text style={estilos.error}>{error}</Text> : <ActivityIndicator color={colores.acento} />}
        <Boton titulo="Volver" onPress={onVolver} />
      </View>
    );
  }

  return (
    <ScrollView style={estilos.raiz} contentContainerStyle={estilos.contenido}>
      <View style={estilos.cabecera}>
        <Boton chico titulo="← Volver" onPress={onVolver} />
        <Text style={estilos.titulo} numberOfLines={1}>{persona.nombre}</Text>
        <Boton chico peligro titulo="Eliminar" onPress={confirmarPersona} />
      </View>
      {error && <Text style={estilos.error}>{error}</Text>}
      <View style={estilos.grilla}>
        {persona.fotos.map((foto) => (
          <View key={foto.id} style={estilos.casilla}>
            <Image source={{ uri: urlFoto(foto.archivo) }} style={estilos.foto} />
            <Pressable style={estilos.borrar} onPress={() => confirmarFoto(foto)}>
              <Text style={estilos.textoBorrar}>✕</Text>
            </Pressable>
          </View>
        ))}
        <Pressable style={[estilos.casilla, estilos.agregar]} onPress={() => setTomando(true)} disabled={ocupado}>
          <Text style={estilos.texto}>{ocupado ? 'Guardando…' : '+ foto'}</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  raiz: { flex: 1, backgroundColor: colores.fondo },
  contenido: { padding: 12, gap: 12 },
  centro: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, backgroundColor: colores.fondo },
  cabecera: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  titulo: { flex: 1, color: colores.texto, fontSize: 20, fontWeight: '700', textAlign: 'center' },
  grilla: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  casilla: { width: '31%', aspectRatio: 1, borderRadius: 8, overflow: 'hidden', backgroundColor: colores.panel },
  foto: { width: '100%', height: '100%' },
  borrar: {
    position: 'absolute',
    top: 4,
    right: 4,
    backgroundColor: '#000a',
    borderRadius: 12,
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  textoBorrar: { color: '#fff', fontWeight: '700' },
  agregar: { alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colores.borde, borderStyle: 'dashed' },
  texto: { color: colores.texto },
  error: { color: colores.peligro },
});
