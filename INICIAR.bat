@echo off
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
