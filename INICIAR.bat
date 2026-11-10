@echo off
cd /d "%~dp0"
set "APP_URL=http://127.0.0.1:5000/venta"

REM Si la aplicación ya está funcionando, abrir otra ventana sin iniciar
REM un segundo servidor en el mismo puerto.
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%' -TimeoutSec 2; if ($r.Content -match 'Punto de Venta') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    where chrome >nul 2>&1
    if not errorlevel 1 (
        start "" chrome --app="%APP_URL%"
    ) else (
        start "" "%APP_URL%"
    )
    exit /b 0
)

echo.
echo ============================================================
echo FERRETERIA - APLICACION DE ESCRITORIO
echo ============================================================
echo.

REM Verificar si existe el entorno virtual
if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv
)

REM Activar entorno virtual
call venv\Scripts\activate

REM Instalar/Actualizar dependencias
echo.
echo Instalando dependencias...
pip install -r requirements.txt > nul 2>&1

REM Ejecutar la aplicación
echo.
echo Abriendo Ferreteria como aplicacion...
echo.
python app.py

pause
