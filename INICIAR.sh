#!/bin/bash

# Asegurar que el script se ejecute siempre desde su propia carpeta
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

URL="http://127.0.0.1:5000/venta"

abrir_ventana() {
    # Chromium/Brave abren la caja como ventana de aplicación y permiten
    # imprimir tickets sin mostrar el diálogo del navegador.
    for nav in /usr/bin/chromium /usr/bin/brave /opt/brave-bin/brave-browser; do
        if [ -x "$nav" ]; then
            nohup "$nav" --kiosk-printing --no-first-run \
                --user-data-dir="$DIR/instance/perfil_caja" \
                --app="$URL" >/dev/null 2>&1 </dev/null &
            return 0
        fi
    done

    if [ -x /usr/bin/firefox ]; then
        nohup /usr/bin/firefox "$URL" >/dev/null 2>&1 </dev/null &
        return 0
    fi

    nohup xdg-open "$URL" >/dev/null 2>&1 </dev/null &
}

# Si el servidor ya quedó corriendo por una apertura anterior, reutilizarlo.
# Así el acceso directo puede volver a abrir la ventana sin chocar con el
# puerto 5000 ni cerrar la sesión de ventas existente.
if curl --silent --show-error --fail --max-time 1 "$URL" 2>/dev/null | grep -qi 'Punto de Venta'; then
    echo "La aplicación ya está en marcha. Abriendo la ventana..."
    abrir_ventana
    exit 0
fi

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
