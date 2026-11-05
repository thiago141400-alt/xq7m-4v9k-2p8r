#!/bin/bash

# Asegurar que el script se ejecute siempre desde su propia carpeta
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "============================================================"
echo "FERRETERÍA - SISTEMA DE GESTIÓN"
echo "============================================================"

# Verificar y crear el entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "Configurando entorno virtual por primera vez..."
    python3 -m venv venv
    "$DIR/venv/bin/pip" install -r requirements.txt
fi

# Si falta Flask en el entorno virtual, instalar dependencias
if [ ! -f "venv/bin/flask" ]; then
    echo "Instalando dependencias necesarias..."
    "$DIR/venv/bin/pip" install -r requirements.txt
fi

echo "Abriendo Ferretería como aplicación..."
echo "Ventana de la app: http://localhost:5000"
echo "Presiona Ctrl+C en esta terminal para detener."

# Ejecutar la aplicación usando el Python del entorno virtual
exec "$DIR/venv/bin/python3" "$DIR/app.py"
