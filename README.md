# Proyecto_BD2 — MiniGestor de Base de Datos Multimodal

Monorepo del proyecto integrador de Base de Datos 2 (Ciclo 2026-2).

## Estructura

```
Proyecto_BD2/
├── backend/
│   ├── engine/
│   │   ├── storage/
│   │   │   ├── heap/            heapfile.py
│   │   │   └── sequential/      sequential_file.py
│   │   ├── hashing/            indice extendible + external hashing (group by / join)
│   │   └── common/             contrato compartido (RID, record, page)
│   ├── api/                    API REST (FastAPI)
│   └── requirements.txt
├── frontend/                   interfaz (React + Vite)
├── data/                       archivos binarios generados (ignorado por git)
└── README.md
```

## Backend

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload
```

API en http://localhost:8000 (health: `/api/health`, demo: `/api/hashing/demo`).

Demo del motor de hashing sin servidor:

```
cd backend
python -m engine.hashing.demo
```

## Frontend

```
cd frontend
npm install
npm run dev
```

Interfaz en http://localhost:5173 (proxy `/api` hacia el backend en el puerto 8000).
