import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { registrarPersona } from './api';
import Boton from './Boton';
import Captura from './Captura';
import { colores } from './tema';

const TOMAS = [
  'De frente',
  'Gira un poco a la izquierda',
  'Gira un poco a la derecha',
  'Mira un poco hacia arriba',
  'Mira un poco hacia abajo',
];

export default function Registrar({ onCancelar, onListo, onProbar }) {
  const [nombre, setNombre] = useState('');
  const [fotos, setFotos] = useState(TOMAS.map(() => null));
  const [tomando, setTomando] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const [creada, setCreada] = useState(null);

  function guardarFoto(uri) {
    const nuevas = [...fotos];
    nuevas[tomando] = uri;
    setFotos(nuevas);
    const siguiente = nuevas.findIndex((foto) => foto === null);
    setTomando(siguiente === -1 ? null : siguiente);
  }

  async function enviar() {
    setEnviando(true);
    setError(null);
    try {
      setCreada(await registrarPersona(nombre, fotos));
    } catch (e) {
      setError(e.message);
      if (e.datos?.foto) {
        const nuevas = [...fotos];
        nuevas[e.datos.foto - 1] = null;
        setFotos(nuevas);
      }
    } finally {
      setEnviando(false);
    }
  }

  if (tomando !== null) {
    return (
      <Captura
        instruccion={`Foto ${tomando + 1} de ${TOMAS.length}: ${TOMAS[tomando]}`}
        onFoto={guardarFoto}
        onCancelar={() => setTomando(null)}
      />
    );
  }

  if (creada) {
    return (
      <View style={estilos.centro}>
        <Text style={estilos.titulo}>{`${creada.nombre} quedó registrado con ${creada.fotos.length} fotos.`}</Text>
        <Boton titulo="Probar reconocimiento" onPress={onProbar} />
        <Boton titulo="Volver a Mis rostros" onPress={onListo} />
      </View>
    );
  }

  const faltante = fotos.findIndex((foto) => foto === null);
  const completo = faltante === -1 && nombre.trim().length > 0;

  return (
    <ScrollView style={estilos.raiz} contentContainerStyle={estilos.contenido}>
      <Text style={estilos.titulo}>Registrar persona</Text>
      <TextInput
        value={nombre}
        onChangeText={setNombre}
        placeholder="Nombre"
        placeholderTextColor={colores.tenue}
        autoCapitalize="words"
        maxLength={60}
        style={estilos.entrada}
      />
      <View style={estilos.grilla}>
        {TOMAS.map((toma, indice) => (
          <Pressable key={toma} style={estilos.casilla} onPress={() => setTomando(indice)}>
            {fotos[indice] ? (
              <Image source={{ uri: fotos[indice] }} style={estilos.foto} />
            ) : (
              <Text style={estilos.numero}>{indice + 1}</Text>
            )}
            <Text style={estilos.pie} numberOfLines={2}>{toma}</Text>
          </Pressable>
        ))}
      </View>
      {error && <Text style={estilos.error}>{error}</Text>}
      {faltante !== -1 && <Boton titulo="Tomar fotos" onPress={() => setTomando(faltante)} />}
      <Boton titulo={enviando ? 'Registrando…' : 'Registrar'} onPress={enviar} desactivado={!completo || enviando} />
      <Boton titulo="Cancelar" peligro onPress={onCancelar} />
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  raiz: { flex: 1, backgroundColor: colores.fondo },
  contenido: { padding: 12, gap: 12 },
  centro: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24, backgroundColor: colores.fondo },
  titulo: { color: colores.texto, fontSize: 20, fontWeight: '700', textAlign: 'center' },
  entrada: { color: colores.texto, backgroundColor: colores.panel, borderRadius: 8, padding: 12, fontSize: 16 },
  grilla: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  casilla: {
    width: '31%',
    aspectRatio: 0.8,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: colores.panel,
    alignItems: 'center',
    justifyContent: 'center',
  },
  foto: { ...StyleSheet.absoluteFillObject },
  numero: { color: colores.tenue, fontSize: 28, fontWeight: '700' },
  pie: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    color: '#fff',
    backgroundColor: '#000a',
    fontSize: 11,
    padding: 4,
    textAlign: 'center',
  },
  error: { color: colores.peligro },
});
