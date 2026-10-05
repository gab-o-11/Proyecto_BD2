import csv
import os
import random
import sys
from datetime import date, timedelta

salida = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo")
os.makedirs(salida, exist_ok=True)
rng = random.Random(20261005)

DISTRITOS = [
    ("Cercado", -12.0464, -77.0428, 6), ("Miraflores", -12.1211, -77.0297, 5), ("San Isidro", -12.0977, -77.0365, 4),
    ("Surco", -12.1459, -76.9915, 7), ("La Molina", -12.0786, -76.9408, 4), ("San Borja", -12.1074, -77.0018, 4),
    ("Barranco", -12.1494, -77.0219, 2), ("Lince", -12.0858, -77.0365, 2), ("Jesus Maria", -12.0718, -77.0446, 3),
    ("Pueblo Libre", -12.0745, -77.0631, 3), ("Magdalena", -12.0912, -77.0716, 2), ("San Miguel", -12.0776, -77.0897, 4),
    ("Brena", -12.0577, -77.0525, 2), ("Rimac", -12.0294, -77.0428, 3), ("SJL", -11.9844, -77.0058, 9),
    ("Los Olivos", -11.9686, -77.0739, 6), ("SMP", -12.0050, -77.0757, 8), ("Comas", -11.9373, -77.0617, 6),
    ("Ate", -12.0256, -76.9175, 6), ("Chorrillos", -12.1693, -77.0244, 5), ("VES", -12.2131, -76.9367, 6),
    ("SJM", -12.1567, -76.9711, 5), ("Callao", -12.0566, -77.1181, 5), ("Independencia", -11.9935, -77.0546, 3),
    ("Santa Anita", -12.0430, -76.9708, 3),
]
PESOS = [d[3] for d in DISTRITOS]

NOMBRES = ["Ana", "Luis", "Rosa", "Jorge", "Maria", "Carlos", "Lucia", "Pedro", "Elena", "Diego", "Sofia", "Miguel",
           "Valeria", "Andres", "Camila", "Jose", "Daniela", "Raul", "Paula", "Victor", "Carmen", "Hugo", "Gabriela",
           "Martin", "Fiorella", "Renzo", "Milagros", "Cesar", "Patricia", "Oscar"]
APELLIDOS = ["Quispe", "Flores", "Sanchez", "Rojas", "Garcia", "Diaz", "Torres", "Chavez", "Ramos", "Vargas",
             "Castillo", "Mendoza", "Huaman", "Mamani", "Gutierrez", "Espinoza", "Romero", "Cruz", "Salazar", "Ruiz",
             "Herrera", "Medina", "Aguilar", "Cardenas", "Paredes"]
CATEGORIAS = {
    "Lacteos": ["Leche", "Yogurt", "Queso", "Mantequilla"],
    "Bebidas": ["Agua", "Gaseosa", "Jugo", "Te helado"],
    "Abarrotes": ["Arroz", "Azucar", "Fideos", "Aceite", "Atun"],
    "Limpieza": ["Detergente", "Lejia", "Jabon", "Suavizante"],
    "Panaderia": ["Pan molde", "Galletas", "Keke", "Tostadas"],
    "Snacks": ["Papas", "Chocolate", "Mani", "Caramelos"],
    "Carnes": ["Pollo", "Res", "Cerdo", "Pescado"],
    "Frutas": ["Platano", "Manzana", "Naranja", "Mango", "Palta"],
}
MARCAS = ["Andina", "Pacifico", "Inka", "Sierra", "Costa", "Selva", "Lima", "Norte", "Sur", "Alpaca"]
MEDIDAS = ["250g", "500g", "1kg", "2kg", "500ml", "1L", "2L", "6un", "12un"]
TIPOS_TIENDA = ["bodega", "minimarket", "supermercado", "express"]
ESTADOS = ["entregado", "entregado", "entregado", "en_camino", "cancelado"]
VEHICULOS = ["moto", "moto", "bicicleta", "auto"]

INICIO = date(2025, 1, 1)
DIAS = (date(2026, 9, 30) - INICIO).days


def punto():
    nombre, lat, lon, _ = rng.choices(DISTRITOS, weights=PESOS)[0]
    return nombre, round(rng.gauss(lat, 0.009), 6), round(rng.gauss(lon, 0.009), 6)


def fecha():
    return (INICIO + timedelta(days=rng.randrange(DIAS))).isoformat()


def escribir(nombre, cabecera, filas):
    ruta = os.path.join(salida, nombre)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecera)
        w.writerows(filas)
    for fila in filas:
        for valor in fila:
            assert len(str(valor).encode()) <= 32 or str(valor).startswith("POINT"), (nombre, valor)
    print(f"{nombre}: {len(filas)} filas")


N = 10000
clientes = []
for i in range(1, N + 1):
    distrito, lat, lon = punto()
    clientes.append([i, rng.choice(NOMBRES), rng.choice(APELLIDOS), distrito, rng.randint(18, 80), fecha(), f"POINT({lat}, {lon})"])
rng.shuffle(clientes)
escribir("clientes.csv", ["id", "nombre", "apellido", "distrito", "edad", "fecha_registro", "ubicacion"], clientes)

productos = []
precios = {}
for i in range(1, N + 1):
    categoria = rng.choice(list(CATEGORIAS))
    nombre = f"{rng.choice(CATEGORIAS[categoria])} {rng.choice(MARCAS)} {rng.choice(MEDIDAS)}"
    precio = round(rng.uniform(1.5, 120), 2)
    precios[i] = precio
    productos.append([i, nombre, categoria, precio, rng.randint(0, 500)])
rng.shuffle(productos)
escribir("productos.csv", ["id", "nombre", "categoria", "precio", "stock"], productos)

tiendas = []
for i in range(1, N + 1):
    distrito, lat, lon = punto()
    tipo = rng.choice(TIPOS_TIENDA)
    tiendas.append([i, f"{tipo.capitalize()} {distrito} {i}"[:32], distrito, tipo, f"POINT({lat}, {lon})"])
escribir("tiendas.csv", ["id", "nombre", "distrito", "tipo", "ubicacion"], tiendas)

ubicacion_cliente = {fila[0]: fila[6] for fila in clientes}
detalle = []
pedidos = []
siguiente_detalle = 1
for i in range(1, N + 1):
    items = 2 if rng.random() < 0.2 else 1
    total = 0.0
    for _ in range(items):
        producto = rng.randint(1, N)
        cantidad = rng.randint(1, 6)
        total += cantidad * precios[producto]
        detalle.append([siguiente_detalle, i, producto, cantidad, precios[producto]])
        siguiente_detalle += 1
    pedidos.append([i, rng.randint(1, N), rng.randint(1, N), fecha(), rng.choice(ESTADOS), round(total, 2)])
escribir("pedidos.csv", ["id", "cliente_id", "tienda_id", "fecha", "estado", "total"], pedidos)
escribir("detalle_pedidos.csv", ["id", "pedido_id", "producto_id", "cantidad", "precio_unitario"], detalle)

repartos = []
for pedido in pedidos:
    if pedido[4] == "cancelado":
        continue
    lat, lon = map(float, ubicacion_cliente[pedido[1]][6:-1].split(","))
    destino = f"POINT({round(lat + rng.gauss(0, 0.0015), 6)}, {round(lon + rng.gauss(0, 0.0015), 6)})"
    repartos.append([len(repartos) + 1, pedido[0], f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}", rng.choice(VEHICULOS), pedido[3], destino])
escribir("repartos.csv", ["id", "pedido_id", "repartidor", "vehiculo", "fecha", "destino"], repartos)
