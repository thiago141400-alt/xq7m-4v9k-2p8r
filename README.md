# 🔧 Ferretería Manager - Sistema de Gestión

Una aplicación de escritorio para gestionar el inventario, ventas y reposición de stock de tu ferretería. Está hecha con Flask y HTML/CSS/JavaScript: la ventana de trabajo se abre sin pestañas ni barra de direcciones y el código queda disponible para modificar.

## ✨ Características

- 📦 **Inventario**: Gestiona todos tus artículos con precios unitarios y por metro
- 📷 **Lector de Código de Barras**: Escanea productos en mostrador con detección automática y sonido BEEP de confirmación
- 🏷️ **Impresión de Etiquetas**: Genera códigos de barras Code128 y prepara etiquetas para impresoras térmicas (50x30mm, 60x40mm) o planchas A4
- 💰 **Ventas (POS)**: Registra ventas rápidamente con carrito multi-producto y cálculo automático de ganancia
- 📥 **Reposición**: Controla las entradas de stock por escaneo o manual
- 📊 **Reportes**: Visualiza ganancias diarias y artículos con bajo stock
- 💾 **Base de Datos**: Almacena todo en SQLite (ferreteria.db) con copias de seguridad automáticas
- 🎨 **Interfaz Moderna**: Diseño limpio y responsivo

## 📋 Requisitos

- Python 3.7 o superior
- pip (gestor de paquetes Python)

## 🚀 Instalación

### 1. Descargar o clonar el proyecto
```bash
cd ruta/de/tu/proyecto
```

### 2. Crear un entorno virtual (opcional pero recomendado)
```bash
python -m venv venv
```

**Activar el entorno:**
- En Windows:
  ```bash
  venv\Scripts\activate
  ```
- En Mac/Linux:
  ```bash
  source venv/bin/activate
  ```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

## ▶️ Abrir la Aplicación

- **Linux:** ejecuta `INICIAR.sh`.
- **Windows:** ejecuta `INICIAR.bat`.

La aplicación abre una ventana propia con Chromium o Chrome. Si no encuentra un navegador compatible, abre el navegador predeterminado. La base de datos local y los archivos de la app siguen siendo editables.

## 🔔 Aviso de nuevas versiones

Al abrir la app, se compara `version.json` con la versión publicada en la rama `main` del repositorio. Cada publicación de cambios en `main` genera una versión nueva automáticamente y prepara un ZIP con el código editable. Las instalaciones anteriores mostrarán el aviso y un botón para ir a descargarla.

El aviso requiere que el repositorio sea público, que GitHub Actions tenga permiso para publicar versiones y que el dispositivo tenga internet. La actualización se descarga y aplica manualmente para no reemplazar la base de datos local. El ZIP de la app no incluye la base de datos ni las copias de seguridad.

## 📖 Cómo Usar

### 📦 **Inventario**
1. Haz clic en **"+ Agregar Artículo"**
2. Completa:
   - **Nombre**: Ej "Tornillo 8x1"
   - **Unidad**: Ej "unidad", "metro", "kg"
   - **Precio Unitario**: El costo que te costó
   - **Precio x Metro** (opcional): Si lo vendés por metro
   - **Cantidad Inicial**: Stock que tenés ahora
3. Haz clic en **"Guardar Artículo"**

El sistema calculará automáticamente los precios de venta con el margen (60% por defecto).

### 📷 **Uso del Lector de Códigos de Barra en Ventas**
1. En la pantalla **Ventas (POS)**, el lector siempre está activo (o presiona `F2` para enfocar).
2. Pasa el producto por el lector láser o inalámbrico:
   - Si el artículo existe: sonará un **BEEP** y se sumará al carrito automáticamente.
   - Si disparas varias veces sobre el mismo producto, sumará +1 a la cantidad.
   - Si el producto no tiene código registrado, el sistema te ofrecerá asociarlo al instante.
3. Haz clic en **"✓ Confirmar Venta"**.

### 🏷️ **Impresión de Etiquetas para Pegar en Productos**
1. Ve a la pestaña **"🏷️ Etiquetas y Códigos"**.
2. Configura tu impresora:
   - **Rollo Térmico 50x30 mm o 60x40 mm** (para impresoras de etiquetas tipo Zebra, Xprinter, etc.).
   - **Hoja A4 autoadhesiva** (para impresoras estándar de oficina).
3. Selecciona los productos y la cantidad de etiquetas que necesitas (ej: 10 etiquetas para 10 bolsas de tornillos).
4. Si un producto no tiene código de barras, pulsa **"⚡ Generar Código"** y el sistema creará uno único automáticamente.
5. Haz clic en **"🖨️ Imprimir Etiquetas (Ctrl + P)"**:
   - En el cuadro de diálogo de impresión, selecciona tu impresora de etiquetas y en márgenes elige **"Ninguno"**.
   - Pega las etiquetas directamente en los gaveteros, bolsitas o productos.

### 💰 **Registrar una Venta Manual**
1. Ve a la pestaña **"Ventas"**
2. Selecciona el **Artículo** del desplegable
3. Elige si lo vendés por **"Unidad"** o **"Metro"**
4. Ingresa la **Cantidad**
5. El **Total a Cobrar** y la **Ganancia** se calculan solos
6. Haz clic en **"✓ Registrar Venta"**

El stock se descuenta automáticamente.

### 📥 **Reponer Stock**
1. Ve a **"Reposición"**
2. Selecciona el artículo que repusiste
3. Ingresa la cantidad que recibiste
4. Haz clic en **"✓ Registrar Reposición"**

El stock se suma automáticamente.

### 📊 **Ver Reportes**
1. Ve a **"Reportes"**
2. Verás:
   - **Resumen del día**: Total vendido, invertido y ganancia
   - **Artículos para reponer**: Los que tienen stock bajo
   - **Consulta por fecha**: Selecciona cualquier fecha anterior

## 🗄️ Base de Datos

Todos los datos se guardan automáticamente en `ferreteria.db` (SQLite).

Si quieres empezar de cero, simplemente elimina ese archivo y ejecuta `python app.py` nuevamente.

## 🎯 Configuración del Margen

El margen por defecto es del **60%**. Para modificarlo, edita `app.py` en la línea:
```python
margen = db.Column(db.Float, default=0.60)
```

Cambia `0.60` por el porcentaje que uses (ej: `0.40` para 40%).

## 🔧 Solución de Problemas

### "ModuleNotFoundError: No module named 'flask'"
**Solución**: Ejecuta `pip install -r requirements.txt`

### "Address already in use"
**Solución**: El puerto 5000 está ocupado. Modifica el puerto en la última línea de `app.py`:
```python
app.run(debug=True, use_reloader=False, port=5001)  # Cambia 5000 por otro número
```

### "No se abre el navegador automáticamente"
**Solución**: Abre manualmente `http://localhost:5000` en tu navegador

## 📞 Soporte

Si encontrás problemas, asegúrate de:
1. Tener Python 3.7+ instalado: `python --version`
2. Haber instalado las dependencias: `pip install -r requirements.txt`
3. Ejecutar desde la carpeta correcta

## 🎨 Personalización

Todos los estilos están en `templates/base.html` dentro de `<style>`. Puedes modificar colores, fuentes y diseño fácilmente.

---

**¡Listo para usar!** 🎉 Cualquier duda, consultá el código — está bien comentado.
