import { Pressable, StyleSheet, Text } from 'react-native';

import { colores } from './tema';

export default function Boton({ titulo, onPress, chico = false, peligro = false, desactivado = false }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={desactivado}
      style={({ pressed }) => [
        estilos.boton,
        chico && estilos.chico,
        peligro && estilos.peligro,
        (pressed || desactivado) && estilos.apagado,
      ]}
    >
      <Text style={estilos.texto}>{titulo}</Text>
    </Pressable>
  );
}

const estilos = StyleSheet.create({
  boton: { backgroundColor: colores.acento, borderRadius: 8, paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center' },
  chico: { paddingVertical: 6, paddingHorizontal: 10 },
  peligro: { backgroundColor: colores.peligro },
  apagado: { opacity: 0.5 },
  texto: { color: '#fff', fontWeight: '600' },
});
