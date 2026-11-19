import { useCallback, useEffect, useState } from 'react';
import { FlatList, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { listarPersonas, urlFoto } from './api';
import Boton from './Boton';
import { colores } from './tema';

export default function MisRostros({ onAbrir, onRegistrar }) {
  const [personas, setPersonas] = useState(null);
  const [error, setError] = useState(null);
  const [cargando, setCargando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      setPersonas(await listarPersonas());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <View style={estilos.raiz}>
      <View style={estilos.cabecera}>
        <Text style={estilos.titulo}>Mis rostros</Text>
        {onRegistrar && <Boton chico titulo="+ Persona" onPress={onRegistrar} />}
      </View>
      {error && <Text style={estilos.error}>{error}</Text>}
      <FlatList
        data={personas ?? []}
        keyExtractor={(persona) => String(persona.id)}
        refreshing={cargando}
        onRefresh={cargar}
        contentContainerStyle={estilos.lista}
        ListEmptyComponent={personas && <Text style={estilos.tenue}>Todavía no registraste a nadie.</Text>}
        renderItem={({ item }) => (
          <Pressable style={estilos.fila} onPress={() => onAbrir(item.id)}>
            {item.portada ? (
              <Image source={{ uri: urlFoto(item.portada) }} style={estilos.miniatura} />
            ) : (
              <View style={estilos.miniatura} />
            )}
            <Text style={estilos.nombre}>{item.nombre}</Text>
            <Text style={estilos.tenue}>{item.fotos === 1 ? '1 foto' : `${item.fotos} fotos`}</Text>
          </Pressable>
        )}
      />
    </View>
  );
}

const estilos = StyleSheet.create({
  raiz: { flex: 1, backgroundColor: colores.fondo },
  cabecera: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 12 },
  titulo: { color: colores.texto, fontSize: 22, fontWeight: '700' },
  lista: { paddingHorizontal: 12, gap: 8 },
  fila: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colores.panel, borderRadius: 8, padding: 10 },
  miniatura: { width: 52, height: 52, borderRadius: 6, backgroundColor: colores.borde },
  nombre: { flex: 1, color: colores.texto, fontSize: 16, fontWeight: '600' },
  tenue: { color: colores.tenue },
  error: { color: colores.peligro, paddingHorizontal: 12 },
});
