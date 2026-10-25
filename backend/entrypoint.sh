#!/bin/sh
set -e

if [ ! -f /app/data/demo/clientes.csv ]; then
    python data/generar_demo.py /app/data/demo
fi

exec uvicorn api.main:app --app-dir backend --host 0.0.0.0 --port 8000
