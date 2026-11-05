import os
import csv
import io
import shutil
import webbrowser
import subprocess
import math
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from sqlalchemy import func
import atexit

# Asegurar que el directorio de trabajo sea siempre la carpeta del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ferreteria.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True

def leer_version_app():
    """Lee la versión desde un archivo simple para mantenerla editable."""
    try:
        with open(os.path.join(BASE_DIR, 'version.json'), encoding='utf-8') as archivo:
            return json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return {'version': '0.1.0', 'release_url': 'https://github.com/thiago141400-alt/xq7m-4v9k-2p8r/releases/latest'}

VERSION_APP = leer_version_app()

@app.context_processor
def contexto_version_app():
    return {'version_app': VERSION_APP.get('version', '0.1.0')}

def formato_numero_es_ar(valor, decimales=2):
    """Formato visual argentino: punto para miles y coma decimal."""
    try:
        return f"{float(valor):,.{int(decimales)}f}".replace(',', '\0').replace('.', ',').replace('\0', '.')
    except (TypeError, ValueError):
        return f"{0:,.{int(decimales)}f}".replace(',', '\0').replace('.', ',').replace('\0', '.')

app.jinja_env.filters['numero_ar'] = formato_numero_es_ar

db = SQLAlchemy(app)

# =====================================================================
# MODELOS
# =====================================================================

class Articulo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    codigo_barra = db.Column(db.String(50), unique=True, nullable=True, index=True)
    tipo_venta = db.Column(db.String(10), nullable=False, default='Unidad')  # "Unidad" o "Metro"
    precio_compra = db.Column(db.Float, nullable=False)
    precio_venta_manual = db.Column(db.Float, nullable=True)
    cantidad = db.Column(db.Integer, default=0)
    etiquetas_pendientes = db.Column(db.Integer, nullable=False, default=0)
    margen = db.Column(db.Float, default=0.60)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    alerta_stock = db.Column(db.Integer, nullable=False, default=5)
    lleva_etiqueta = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    ventas = db.relationship('Venta', backref='articulo', lazy=True)
    reposiciones = db.relationship('Reposicion', backref='articulo', lazy=True)

    @property
    def precio_venta(self):
        if self.precio_venta_manual:
            return self.precio_venta_manual
        return self.precio_compra * (1 + self.margen)

    @property
    def stock_actual(self):
        vendido = db.session.query(func.sum(Venta.cantidad)).filter(Venta.articulo_id == self.id).scalar() or 0
        repuesto = db.session.query(func.sum(Reposicion.cantidad)).filter(Reposicion.articulo_id == self.id).scalar() or 0
        return self.cantidad + repuesto - vendido
    
    @property
    def estado(self):
        return "REPONER" if self.stock_actual <= self.alerta_stock else "OK"

class VentaTransaccion(db.Model):
    """Agrupa varios renglones de Venta en una sola 'compra'. El número
    de compra (numero_dia) se reinicia todos los días."""
    id = db.Column(db.Integer, primary_key=True)
    numero_dia = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    total = db.Column(db.Float, nullable=False)
    costo = db.Column(db.Float, nullable=False)
    ganancia = db.Column(db.Float, nullable=False)

    items = db.relationship('Venta', backref='transaccion', lazy=True)

class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    articulo_id = db.Column(db.Integer, db.ForeignKey('articulo.id'), nullable=False)
    transaccion_id = db.Column(db.Integer, db.ForeignKey('venta_transaccion.id'), nullable=True)
    tipo_venta = db.Column(db.String(10), nullable=False)  # "Unidad" o "Metro"
    cantidad = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    ganancia = db.Column(db.Float, nullable=False)
    costo = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)

class ReposicionTransaccion(db.Model):
    """Agrupa varios renglones de Reposicion en una sola carga. El número
    (numero_dia) se reinicia todos los días, igual que en VentaTransaccion."""
    id = db.Column(db.Integer, primary_key=True)
    numero_dia = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)

    items = db.relationship('Reposicion', backref='transaccion', lazy=True)

class Reposicion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    articulo_id = db.Column(db.Integer, db.ForeignKey('articulo.id'), nullable=False)
    transaccion_id = db.Column(db.Integer, db.ForeignKey('reposicion_transaccion.id'), nullable=True)
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)

# =====================================================================
# MIGRACIÓN AUTOMÁTICA DE LA BASE DE DATOS
# =====================================================================

def migrar_db():
    """Migra una DB SQLite creada con el esquema viejo de Articulo
    (unidad, precio_unitario, precio_metro -- 'unidad' y 'precio_unitario' eran
    NOT NULL) al esquema nuevo (tipo_venta, precio_compra, precio_venta_manual).
    Reconstruye la tabla porque SQLite no permite quitar una restricción NOT NULL
    con ALTER TABLE. No toca las tablas de ventas ni reposiciones."""
    inspector = db.inspect(db.engine)

    if 'articulo' in inspector.get_table_names():
        columnas = {c['name'] for c in inspector.get_columns('articulo')}

        if {'unidad', 'precio_unitario'} & columnas:
            with db.engine.connect() as conn:
                filas = conn.execute(db.text(
                    "SELECT id, nombre, unidad, precio_unitario, precio_metro, "
                    "cantidad, margen, created_at FROM articulo"
                )).fetchall()

                conn.execute(db.text("DROP TABLE IF EXISTS articulo_nuevo"))
                conn.execute(db.text("""
                    CREATE TABLE articulo_nuevo (
                        id INTEGER PRIMARY KEY,
                        nombre VARCHAR(100) NOT NULL UNIQUE,
                        tipo_venta VARCHAR(10) NOT NULL,
                        precio_compra FLOAT NOT NULL,
                        precio_venta_manual FLOAT,
                        cantidad INTEGER,
                        margen FLOAT,
                        created_at DATETIME
                    )
                """))

                for (articulo_id, nombre, unidad_vieja, precio_unitario_viejo,
                     precio_metro_viejo, cantidad, margen, created_at) in filas:
                    unidad_vieja = (unidad_vieja or '').strip().lower()
                    if 'metro' in unidad_vieja:
                        tipo = 'Metro'
                        precio_compra = precio_metro_viejo if precio_metro_viejo else precio_unitario_viejo
                    else:
                        tipo = 'Unidad'
                        precio_compra = precio_unitario_viejo

                    conn.execute(db.text("""
                        INSERT INTO articulo_nuevo
                            (id, nombre, tipo_venta, precio_compra, precio_venta_manual, cantidad, margen, created_at)
                        VALUES
                            (:id, :nombre, :tipo, :precio_compra, NULL, :cantidad, :margen, :created_at)
                    """), {
                        'id': articulo_id, 'nombre': nombre, 'tipo': tipo,
                        'precio_compra': precio_compra, 'cantidad': cantidad,
                        'margen': margen, 'created_at': created_at
                    })

                conn.execute(db.text("DROP TABLE articulo"))
                conn.execute(db.text("ALTER TABLE articulo_nuevo RENAME TO articulo"))
                conn.commit()

    db.create_all()

    # Agrupar ventas en "compras" (VentaTransaccion): agrega la columna
    # transaccion_id a Venta si falta, y agrupa las ventas viejas que
    # todavía no pertenecen a ninguna compra (cada una pasa a ser su
    # propia compra de 1 producto, respetando el orden cronológico).
    inspector = db.inspect(db.engine)
    if 'venta' in inspector.get_table_names():
        columnas_venta = {c['name'] for c in inspector.get_columns('venta')}
        if 'transaccion_id' not in columnas_venta:
            with db.engine.connect() as conn:
                conn.execute(db.text(
                    "ALTER TABLE venta ADD COLUMN transaccion_id INTEGER REFERENCES venta_transaccion(id)"
                ))
                conn.commit()

        ventas_sin_transaccion = Venta.query.filter(
            Venta.transaccion_id.is_(None)
        ).order_by(Venta.fecha.asc()).all()

        if ventas_sin_transaccion:
            contador_por_dia = {}
            for v in ventas_sin_transaccion:
                dia = v.fecha.date()
                contador_por_dia[dia] = contador_por_dia.get(dia, 0) + 1
                transaccion = VentaTransaccion(
                    numero_dia=contador_por_dia[dia],
                    fecha=v.fecha,
                    total=v.total,
                    costo=v.costo,
                    ganancia=v.ganancia
                )
                db.session.add(transaccion)
                db.session.flush()
                v.transaccion_id = transaccion.id
            db.session.commit()

    # Agrupar reposiciones en "cargas" (ReposicionTransaccion), mismo patrón.
    inspector = db.inspect(db.engine)
    if 'reposicion' in inspector.get_table_names():
        columnas_reposicion = {c['name'] for c in inspector.get_columns('reposicion')}
        if 'transaccion_id' not in columnas_reposicion:
            with db.engine.connect() as conn:
                conn.execute(db.text(
                    "ALTER TABLE reposicion ADD COLUMN transaccion_id INTEGER REFERENCES reposicion_transaccion(id)"
                ))
                conn.commit()

        reposiciones_sin_transaccion = Reposicion.query.filter(
            Reposicion.transaccion_id.is_(None)
        ).order_by(Reposicion.fecha.asc()).all()

        if reposiciones_sin_transaccion:
            contador_por_dia = {}
            for r in reposiciones_sin_transaccion:
                dia = r.fecha.date()
                contador_por_dia[dia] = contador_por_dia.get(dia, 0) + 1
                transaccion = ReposicionTransaccion(
                    numero_dia=contador_por_dia[dia],
                    fecha=r.fecha
                )
                db.session.add(transaccion)
                db.session.flush()
                r.transaccion_id = transaccion.id
            db.session.commit()

    # Agrega 'activo' (dar de baja artículos), 'alerta_stock' (umbral de
    # stock bajo) y 'codigo_barra' (para automatización con escáner) si faltan.
    inspector = db.inspect(db.engine)
    if 'articulo' in inspector.get_table_names():
        columnas_articulo = {c['name'] for c in inspector.get_columns('articulo')}
        with db.engine.connect() as conn:
            if 'activo' not in columnas_articulo:
                conn.execute(db.text("ALTER TABLE articulo ADD COLUMN activo BOOLEAN NOT NULL DEFAULT 1"))
                conn.commit()
            if 'alerta_stock' not in columnas_articulo:
                conn.execute(db.text("ALTER TABLE articulo ADD COLUMN alerta_stock INTEGER NOT NULL DEFAULT 5"))
                conn.commit()
            if 'codigo_barra' not in columnas_articulo:
                conn.execute(db.text("ALTER TABLE articulo ADD COLUMN codigo_barra VARCHAR(50)"))
                conn.commit()
                try:
                    conn.execute(db.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_articulo_codigo_barra ON articulo(codigo_barra)"))
                    conn.commit()
                except Exception:
                    pass
            if 'etiquetas_pendientes' not in columnas_articulo:
                conn.execute(db.text("ALTER TABLE articulo ADD COLUMN etiquetas_pendientes INTEGER NOT NULL DEFAULT 0"))
                conn.commit()
            if 'lleva_etiqueta' not in columnas_articulo:
                conn.execute(db.text("ALTER TABLE articulo ADD COLUMN lleva_etiqueta BOOLEAN NOT NULL DEFAULT 1"))
                conn.commit()

def generar_codigo_unico():
    """Genera un código de barras interno único (formato numérico 779XXXXXXXX)
    para artículos que no tienen código de fábrica. Compatible 100% con
    lectores láser y térmicas en formato Code128 / EAN."""
    import random
    while True:
        max_id = db.session.query(func.max(Articulo.id)).scalar() or 0
        siguiente = max_id + random.randint(1, 9999)
        candidato = f"779{siguiente:08d}"
        if not Articulo.query.filter_by(codigo_barra=candidato).first():
            return candidato

# =====================================================================
# RUTAS
# =====================================================================

@app.route('/')
def index():
    return redirect(url_for('inventario'))

@app.route('/inventario')
def inventario():
    articulos = Articulo.query.all()
    return render_template('inventario.html', articulos=articulos)

@app.route('/etiquetas')
def etiquetas():
    articulos = Articulo.query.filter_by(activo=True, lleva_etiqueta=True).order_by(Articulo.nombre.asc()).all()
    return render_template('etiquetas.html', articulos=articulos)

@app.route('/barcode/<codigo>.svg')
def barcode_svg(codigo):
    """Genera dinámicamente un código de barras vectorial SVG (Code128).
    Ideal para impresión en etiquetas térmicas o planchas A4 sin pérdida de calidad."""
    import barcode
    from barcode.writer import SVGWriter
    try:
        code_obj = barcode.get('code128', str(codigo).strip(), writer=SVGWriter())
        buffer = io.BytesIO()
        code_obj.write(buffer, options={
            'write_text': True,
            'font_size': 10,
            'text_distance': 3.5,
            'quiet_zone': 2.0,
            'module_height': 14.0,
            'module_width': 0.28
        })
        return Response(buffer.getvalue(), mimetype='image/svg+xml')
    except Exception as e:
        svg_error = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="180" height="45">'
            f'<rect width="100%" height="100%" fill="#f8d7da" stroke="#f5c6cb"/>'
            f'<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#721c24" font-size="12">{codigo}</text>'
            f'</svg>'
        )
        return Response(svg_error, mimetype='image/svg+xml')

@app.route('/api/articulos')
def api_articulos():
    incluir_inactivos = request.args.get('incluir_inactivos') == '1'
    query = Articulo.query
    if not incluir_inactivos:
        query = query.filter_by(activo=True)
    articulos = query.all()
    return jsonify([{
        'id': a.id,
        'nombre': a.nombre,
        'codigo_barra': a.codigo_barra,
        'tipo_venta': a.tipo_venta,
        'precio_compra': a.precio_compra,
        'margen_porcentaje': round(a.margen * 100, 2),
        'precio_venta_manual': a.precio_venta_manual,
        'precio_venta': a.precio_venta,
        'stock_actual': a.stock_actual,
        'estado': a.estado,
        'cantidad': a.cantidad,
        'activo': a.activo,
        'alerta_stock': a.alerta_stock,
        'lleva_etiqueta': a.lleva_etiqueta
    } for a in articulos])

@app.route('/api/articulo/buscar_codigo/<path:codigo>')
def buscar_articulo_por_codigo(codigo):
    """Búsqueda ultra rápida para el lector de código de barras.
    Busca por coincidencia exacta con codigo_barra o por ID si es numérico."""
    codigo_limpio = str(codigo).strip()
    articulo = Articulo.query.filter(
        Articulo.codigo_barra == codigo_limpio,
        Articulo.activo == True
    ).first()

    if not articulo and codigo_limpio.isdigit():
        articulo = Articulo.query.filter(
            Articulo.id == int(codigo_limpio),
            Articulo.activo == True
        ).first()

    if not articulo:
        return jsonify({'success': False, 'error': f"Código '{codigo_limpio}' no encontrado"}), 404

    return jsonify({
        'success': True,
        'articulo': {
            'id': articulo.id,
            'nombre': articulo.nombre,
            'codigo_barra': articulo.codigo_barra,
            'tipo_venta': articulo.tipo_venta,
            'precio_compra': articulo.precio_compra,
            'precio_venta': articulo.precio_venta,
            'stock_actual': articulo.stock_actual,
            'estado': articulo.estado
        }
    })

@app.route('/api/articulo/asociar_codigo', methods=['POST'])
def asociar_codigo_articulo():
    """Asocia un código de barras recién escaneado con un artículo existente."""
    data = request.json or {}
    articulo_id = data.get('articulo_id')
    codigo_barra = str(data.get('codigo_barra', '')).strip()

    if not articulo_id or not codigo_barra:
        return jsonify({'success': False, 'error': 'Falta articulo_id o codigo_barra'}), 400

    articulo = db.session.get(Articulo, articulo_id)
    if not articulo:
        return jsonify({'success': False, 'error': 'Artículo no encontrado'}), 404

    existente = Articulo.query.filter(Articulo.codigo_barra == codigo_barra, Articulo.id != articulo_id).first()
    if existente:
        return jsonify({'success': False, 'error': f"Ese código ya está asignado a '{existente.nombre}'"}), 400

    articulo.codigo_barra = codigo_barra
    db.session.commit()
    return jsonify({'success': True, 'codigo_barra': codigo_barra})

@app.route('/api/articulo/<int:id>/generar_codigo', methods=['POST'])
def generar_codigo_articulo(id):
    """Genera y guarda un código de barras interno para un artículo."""
    articulo = db.session.get(Articulo, id)
    if not articulo:
        return jsonify({'success': False, 'error': 'Artículo no encontrado'}), 404

    nuevo_codigo = generar_codigo_unico()
    articulo.codigo_barra = nuevo_codigo
    db.session.commit()
    return jsonify({'success': True, 'codigo_barra': nuevo_codigo})

@app.route('/api/articulos/generar_todos_codigos', methods=['POST'])
def generar_todos_codigos():
    """Asigna automáticamente código de barras único a todos los artículos
    que todavía no tengan uno."""
    sin_codigo = Articulo.query.filter(
        (Articulo.codigo_barra.is_(None)) | (Articulo.codigo_barra == '')
    ).all()
    generados = 0
    for a in sin_codigo:
        a.codigo_barra = generar_codigo_unico()
        generados += 1
    db.session.commit()
    return jsonify({'success': True, 'generados': generados})

@app.route('/api/ventas/ultimo_ticket')
def api_ultimo_ticket():
    """Devuelve los datos del último ticket de venta para impresión automática."""
    transaccion_id = request.args.get('id', type=int)
    consulta = VentaTransaccion.query
    if transaccion_id is not None:
        consulta = consulta.filter_by(id=transaccion_id)
    transaccion = consulta.order_by(VentaTransaccion.id.desc()).first()
    if not transaccion:
        return jsonify({'success': False, 'error': 'No hay ventas registradas'}), 404
    return jsonify({
        'success': True,
        'id': transaccion.id,
        'numero_dia': transaccion.numero_dia,
        'fecha': transaccion.fecha.strftime('%d/%m/%Y %H:%M'),
        'total': transaccion.total,
        'items': [{
            'articulo': v.articulo.nombre if v.articulo else 'Artículo',
            'cantidad': v.cantidad,
            'tipo_venta': v.tipo_venta,
            'precio_unitario': (v.total / v.cantidad) if v.cantidad else 0,
            'total': v.total
        } for v in transaccion.items]
    })

@app.route('/api/articulo/crear', methods=['POST'])
def crear_articulo():
    data = request.json
    codigo_barra = str(data.get('codigo_barra', '')).strip() or None

    # Si no ingresó código, se autogenera 100% de forma automática
    if not codigo_barra:
        codigo_barra = generar_codigo_unico()

    if codigo_barra:
        existente = Articulo.query.filter_by(codigo_barra=codigo_barra).first()
        if existente:
            return jsonify({'success': False, 'error': f"El código de barras ya pertenece a '{existente.nombre}'"}), 400

    articulo = Articulo(
        nombre=data['nombre'],
        codigo_barra=codigo_barra,
        tipo_venta=data['tipo_venta'],
        precio_compra=float(data['precio_compra']),
        margen=float(data['margen_porcentaje']) / 100,
        precio_venta_manual=float(data['precio_venta_manual']) if data.get('precio_venta_manual') else None,
        cantidad=int(data['cantidad']),
        etiquetas_pendientes=int(data['cantidad']) if data.get('lleva_etiqueta', True) else 0,
        lleva_etiqueta=bool(data.get('lleva_etiqueta', True)),
        alerta_stock=int(data['alerta_stock']) if data.get('alerta_stock') else 5
    )
    db.session.add(articulo)
    db.session.commit()
    return jsonify({'success': True, 'id': articulo.id, 'codigo_barra': articulo.codigo_barra})

@app.route('/api/articulo/<int:id>', methods=['PUT'])
def actualizar_articulo(id):
    articulo = db.session.get(Articulo, id)
    if not articulo:
        return jsonify({'success': False, 'error': 'No encontrado'}), 404

    data = request.json
    if 'lleva_etiqueta' in data:
        nuevo_estado_etiqueta = bool(data['lleva_etiqueta'])
        if nuevo_estado_etiqueta and not articulo.lleva_etiqueta:
            articulo.etiquetas_pendientes = max(0, int(articulo.stock_actual))
        elif not nuevo_estado_etiqueta:
            articulo.etiquetas_pendientes = 0
        articulo.lleva_etiqueta = nuevo_estado_etiqueta
    if 'codigo_barra' in data:
        cb = str(data['codigo_barra']).strip() if data['codigo_barra'] else None
        if cb:
            existente = Articulo.query.filter(Articulo.codigo_barra == cb, Articulo.id != id).first()
            if existente:
                return jsonify({'success': False, 'error': f"El código ya pertenece a '{existente.nombre}'"}), 400
        articulo.codigo_barra = cb
    if 'cantidad' in data:
        nueva_cantidad = int(data['cantidad'])
        diferencia = nueva_cantidad - articulo.cantidad
        articulo.cantidad = nueva_cantidad
        if diferencia > 0 and articulo.lleva_etiqueta:
            articulo.etiquetas_pendientes += diferencia
    if 'tipo_venta' in data:
        articulo.tipo_venta = data['tipo_venta']
    if 'precio_compra' in data:
        articulo.precio_compra = float(data['precio_compra'])
    if 'margen_porcentaje' in data:
        articulo.margen = float(data['margen_porcentaje']) / 100
    if 'precio_venta_manual' in data:
        articulo.precio_venta_manual = float(data['precio_venta_manual']) if data['precio_venta_manual'] else None
    if 'alerta_stock' in data:
        articulo.alerta_stock = int(data['alerta_stock'])
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/articulo/<int:id>/baja', methods=['POST'])
def dar_de_baja_articulo(id):
    articulo = db.session.get(Articulo, id)
    if not articulo:
        return jsonify({'success': False, 'error': 'No encontrado'}), 404
    articulo.activo = False
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/articulo/<int:id>/activar', methods=['POST'])
def reactivar_articulo(id):
    articulo = db.session.get(Articulo, id)
    if not articulo:
        return jsonify({'success': False, 'error': 'No encontrado'}), 404
    articulo.activo = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/venta')
def venta():
    articulos = Articulo.query.all()
    return render_template('venta.html', articulos=articulos)

def _siguiente_numero_de_compra():
    """Numera las compras del día 1, 2, 3... y se reinicia cada día."""
    hoy = date.today()
    maximo = db.session.query(func.max(VentaTransaccion.numero_dia)).filter(
        func.date(VentaTransaccion.fecha) == hoy
    ).scalar()
    return (maximo or 0) + 1

@app.route('/api/venta/crear', methods=['POST'])
def crear_venta():
    data = request.get_json(silent=True) or {}
    articulo = db.session.get(Articulo, data.get('articulo_id'))
    if not articulo or not articulo.activo:
        return jsonify({'success': False, 'error': 'Artículo no disponible'}), 400
    try:
        cantidad = float(data.get('cantidad', 0))
    except (TypeError, ValueError):
        cantidad = 0
    if not math.isfinite(cantidad) or cantidad <= 0:
        return jsonify({'success': False, 'error': 'La cantidad debe ser mayor que cero'}), 400

    total = cantidad * articulo.precio_venta
    costo = cantidad * articulo.precio_compra
    ganancia = total - costo

    transaccion = VentaTransaccion(
        numero_dia=_siguiente_numero_de_compra(),
        total=total,
        costo=costo,
        ganancia=ganancia
    )
    db.session.add(transaccion)
    db.session.flush()

    venta = Venta(
        articulo_id=articulo.id,
        transaccion_id=transaccion.id,
        tipo_venta=articulo.tipo_venta,
        cantidad=cantidad,
        total=total,
        ganancia=ganancia,
        costo=costo
    )

    db.session.add(venta)
    db.session.commit()

    return jsonify({
        'success': True,
        'venta_id': venta.id,
        'numero_dia': transaccion.numero_dia,
        'total': total,
        'ganancia': ganancia
    })

@app.route('/api/venta/crear_multiple', methods=['POST'])
def crear_venta_multiple():
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])

    if not items:
        return jsonify({'success': False, 'error': 'No hay artículos para vender'}), 400

    detalles = []
    total_general = 0
    costo_general = 0
    ganancia_general = 0

    for item in items:
        articulo = db.session.get(Articulo, item.get('articulo_id'))
        if not articulo or not articulo.activo:
            return jsonify({'success': False, 'error': 'Uno de los artículos no está disponible'}), 400
        try:
            cantidad = float(item.get('cantidad', 0))
        except (TypeError, ValueError):
            cantidad = 0
        if not math.isfinite(cantidad) or cantidad <= 0:
            return jsonify({'success': False, 'error': f'Cantidad inválida para {articulo.nombre}'}), 400

        total = cantidad * articulo.precio_venta
        costo = cantidad * articulo.precio_compra
        ganancia = total - costo

        detalles.append((articulo, cantidad, total, costo, ganancia))
        total_general += total
        costo_general += costo
        ganancia_general += ganancia

    transaccion = VentaTransaccion(
        numero_dia=_siguiente_numero_de_compra(),
        total=total_general,
        costo=costo_general,
        ganancia=ganancia_general
    )
    db.session.add(transaccion)
    db.session.flush()

    for articulo, cantidad, total, costo, ganancia in detalles:
        db.session.add(Venta(
            articulo_id=articulo.id,
            transaccion_id=transaccion.id,
            tipo_venta=articulo.tipo_venta,
            cantidad=cantidad,
            total=total,
            ganancia=ganancia,
            costo=costo
        ))

    db.session.commit()

    return jsonify({
        'success': True,
        'transaccion_id': transaccion.id,
        'numero_dia': transaccion.numero_dia,
        'total': total_general,
        'costo': costo_general,
        'ganancia': ganancia_general
    })

@app.route('/api/ventas/transacciones')
def api_ventas_transacciones():
    fecha_str = request.args.get('fecha')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        fecha = date.today()

    transacciones = VentaTransaccion.query.filter(
        func.date(VentaTransaccion.fecha) == fecha
    ).order_by(VentaTransaccion.numero_dia.desc()).all()

    return jsonify([{
        'id': t.id,
        'numero_dia': t.numero_dia,
        'hora': t.fecha.strftime('%H:%M'),
        'total': t.total,
        'costo': t.costo,
        'ganancia': t.ganancia,
        'cantidad_items': len(t.items)
    } for t in transacciones])

@app.route('/api/ventas/transaccion/<int:id>')
def api_venta_transaccion_detalle(id):
    transaccion = db.session.get(VentaTransaccion, id)
    if not transaccion:
        return jsonify({'error': 'No encontrada'}), 404

    return jsonify({
        'id': transaccion.id,
        'numero_dia': transaccion.numero_dia,
        'fecha': transaccion.fecha.strftime('%d/%m/%Y %H:%M'),
        'total': transaccion.total,
        'costo': transaccion.costo,
        'ganancia': transaccion.ganancia,
        'items': [{
            'id': v.id,
            'articulo': v.articulo.nombre,
            'tipo_venta': v.tipo_venta,
            'cantidad': v.cantidad,
            'total': v.total,
            'ganancia': v.ganancia
        } for v in transaccion.items]
    })

@app.route('/api/venta/<int:id>', methods=['DELETE'])
def eliminar_venta(id):
    venta = db.session.get(Venta, id)
    if not venta:
        return jsonify({'success': False, 'error': 'No encontrada'}), 404

    # Anular una venta devuelve el stock automáticamente, porque stock_actual
    # se calcula restando la suma de ventas vigentes: al borrar esta fila,
    # deja de descontarse. Los totales de la transacción se ajustan acá;
    # si queda sin artículos, se borra la transacción entera.
    transaccion = venta.transaccion
    if transaccion:
        transaccion.total -= venta.total
        transaccion.costo -= venta.costo
        transaccion.ganancia -= venta.ganancia

    db.session.delete(venta)
    db.session.flush()

    if transaccion and len(transaccion.items) == 0:
        db.session.delete(transaccion)

    db.session.commit()
    return jsonify({'success': True})

@app.route('/reposicion')
def reposicion():
    articulos = Articulo.query.all()
    return render_template('reposicion.html', articulos=articulos)

def _siguiente_numero_de_reposicion():
    """Numera las cargas de reposición del día 1, 2, 3... y se reinicia cada día."""
    hoy = date.today()
    maximo = db.session.query(func.max(ReposicionTransaccion.numero_dia)).filter(
        func.date(ReposicionTransaccion.fecha) == hoy
    ).scalar()
    return (maximo or 0) + 1

@app.route('/api/reposicion/crear', methods=['POST'])
def crear_reposicion():
    data = request.json

    transaccion = ReposicionTransaccion(numero_dia=_siguiente_numero_de_reposicion())
    db.session.add(transaccion)
    db.session.flush()

    reposicion = Reposicion(
        articulo_id=data['articulo_id'],
        transaccion_id=transaccion.id,
        cantidad=int(data['cantidad'])
    )
    db.session.add(reposicion)
    articulo = db.session.get(Articulo, int(data['articulo_id']))
    if articulo and articulo.lleva_etiqueta:
        articulo.etiquetas_pendientes += int(data['cantidad'])
    db.session.commit()
    return jsonify({'success': True, 'numero_dia': transaccion.numero_dia})

@app.route('/api/reposicion/crear_multiple', methods=['POST'])
def crear_reposicion_multiple():
    data = request.json
    items = data.get('items', [])

    if not items:
        return jsonify({'success': False, 'error': 'No hay artículos para reponer'}), 400

    transaccion = ReposicionTransaccion(numero_dia=_siguiente_numero_de_reposicion())
    db.session.add(transaccion)
    db.session.flush()

    for item in items:
        articulo = db.session.get(Articulo, int(item['articulo_id']))
        if articulo and articulo.lleva_etiqueta:
            articulo.etiquetas_pendientes += int(item['cantidad'])
        db.session.add(Reposicion(
            articulo_id=item['articulo_id'],
            transaccion_id=transaccion.id,
            cantidad=int(item['cantidad'])
        ))

    db.session.commit()
    return jsonify({'success': True, 'transaccion_id': transaccion.id, 'numero_dia': transaccion.numero_dia})

@app.route('/api/articulos/etiquetas/imprimir', methods=['POST'])
def registrar_etiquetas_impresas():
    datos = request.get_json(silent=True) or {}
    items = datos.get('items', [])
    for item in items:
        articulo = db.session.get(Articulo, item.get('articulo_id'))
        if not articulo:
            continue
        try:
            cantidad = max(0, int(item.get('cantidad', 0)))
        except (TypeError, ValueError):
            cantidad = 0
        articulo.etiquetas_pendientes = max(0, articulo.etiquetas_pendientes - cantidad)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/reposiciones/transacciones')
def api_reposiciones_transacciones():
    # Historial permanente: no se borra nada automáticamente. Se muestran
    # las últimas 200 cargas por prolijidad, pero todo queda guardado.
    transacciones = ReposicionTransaccion.query.order_by(
        ReposicionTransaccion.fecha.desc()
    ).limit(200).all()

    return jsonify([{
        'id': t.id,
        'numero_dia': t.numero_dia,
        'fecha': t.fecha.strftime('%d/%m/%Y %H:%M'),
        'cantidad_items': len(t.items)
    } for t in transacciones])

@app.route('/api/reposicion/transaccion/<int:id>')
def api_reposicion_transaccion_detalle(id):
    transaccion = db.session.get(ReposicionTransaccion, id)
    if not transaccion:
        return jsonify({'error': 'No encontrada'}), 404

    return jsonify({
        'id': transaccion.id,
        'numero_dia': transaccion.numero_dia,
        'fecha': transaccion.fecha.strftime('%d/%m/%Y %H:%M'),
        'items': [{
            'id': r.id,
            'articulo': r.articulo.nombre,
            'cantidad': r.cantidad,
            'tipo_venta': r.articulo.tipo_venta,
            'stock_actual': r.articulo.stock_actual
        } for r in transaccion.items]
    })

@app.route('/api/reposicion/<int:id>', methods=['DELETE'])
def eliminar_reposicion(id):
    reposicion = db.session.get(Reposicion, id)
    if not reposicion:
        return jsonify({'success': False, 'error': 'No encontrada'}), 404

    # Borrar el registro del historial es solo "prolijidad de datos": el
    # stock físico ya está repuesto en el local, así que no debe bajar.
    # La cantidad se absorbe en la base del artículo antes de borrar el log.
    articulo = reposicion.articulo
    articulo.cantidad += reposicion.cantidad

    db.session.delete(reposicion)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/reportes')
def reportes():
    hoy = date.today()
    ventas_hoy = db.session.query(func.sum(Venta.total), func.sum(Venta.ganancia), func.sum(Venta.costo)).filter(
        func.date(Venta.fecha) == hoy
    ).first()
    
    total_vendido_hoy = ventas_hoy[0] or 0
    ganancia_hoy = ventas_hoy[1] or 0
    costo_hoy = ventas_hoy[2] or 0
    
    articulos_bajo_stock = [a for a in Articulo.query.filter_by(activo=True).all() if a.stock_actual <= a.alerta_stock]
    
    return render_template('reportes.html', 
                         total_vendido_hoy=total_vendido_hoy,
                         ganancia_hoy=ganancia_hoy,
                         costo_hoy=costo_hoy,
                         articulos_bajo_stock=articulos_bajo_stock)

@app.route('/api/reportes/hoy')
def reportes_hoy():
    hoy = date.today()
    ventas = Venta.query.filter(func.date(Venta.fecha) == hoy).all()
    
    total_vendido = sum(v.total for v in ventas)
    ganancia_total = sum(v.ganancia for v in ventas)
    costo_total = sum(v.costo for v in ventas)
    
    return jsonify({
        'total_vendido': total_vendido,
        'ganancia_total': ganancia_total,
        'costo_total': costo_total,
        'cantidad_ventas': len(ventas)
    })

@app.route('/api/reportes/por-fecha')
def reportes_por_fecha():
    fecha_str = request.args.get('fecha')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except:
        fecha = date.today()
    
    ventas = Venta.query.filter(func.date(Venta.fecha) == fecha).all()
    
    total_vendido = sum(v.total for v in ventas)
    ganancia_total = sum(v.ganancia for v in ventas)
    costo_total = sum(v.costo for v in ventas)
    
    return jsonify({
        'vendido': total_vendido,
        'ganancia': ganancia_total,
        'invertido': costo_total,
        'cantidad_ventas': len(ventas)
    })

def _parsear_rango():
    desde_str = request.args.get('desde')
    hasta_str = request.args.get('hasta')
    try:
        desde = datetime.strptime(desde_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        desde = date.today()
    try:
        hasta = datetime.strptime(hasta_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        hasta = date.today()
    return desde, hasta

@app.route('/api/reportes/rango')
def reportes_por_rango():
    desde, hasta = _parsear_rango()

    ventas = Venta.query.filter(
        func.date(Venta.fecha) >= desde,
        func.date(Venta.fecha) <= hasta
    ).all()

    total_vendido = sum(v.total for v in ventas)
    ganancia_total = sum(v.ganancia for v in ventas)
    costo_total = sum(v.costo for v in ventas)

    return jsonify({
        'vendido': total_vendido,
        'ganancia': ganancia_total,
        'invertido': costo_total,
        'cantidad_ventas': len(ventas)
    })

@app.route('/api/reportes/exportar')
def exportar_reporte_csv():
    desde, hasta = _parsear_rango()

    ventas = Venta.query.filter(
        func.date(Venta.fecha) >= desde,
        func.date(Venta.fecha) <= hasta
    ).order_by(Venta.fecha.asc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(['Fecha', 'Hora', 'Articulo', 'Tipo', 'Cantidad', 'Total', 'Costo', 'Ganancia'])
    for v in ventas:
        writer.writerow([
            v.fecha.strftime('%d/%m/%Y'),
            v.fecha.strftime('%H:%M'),
            v.articulo.nombre if v.articulo else '',
            v.tipo_venta,
            v.cantidad,
            f'{v.total:.2f}',
            f'{v.costo:.2f}',
            f'{v.ganancia:.2f}'
        ])

    nombre_archivo = f'ventas_{desde.isoformat()}_a_{hasta.isoformat()}.csv'
    return Response(
        '﻿' + buffer.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{nombre_archivo}"'}
    )

# =====================================================================
# CREAR TABLAS E INICIAR APP
# =====================================================================

def backup_diario():
    """Copia ferreteria.db a backups/ferreteria_YYYY-MM-DD.db si todavía no
    existe el backup de hoy, y borra los backups de más de 30 días."""
    db_path = os.path.join(app.instance_path, 'ferreteria.db')
    if not os.path.exists(db_path):
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    backups_dir = os.path.join(base_dir, 'backups')
    os.makedirs(backups_dir, exist_ok=True)

    nombre_hoy = f'ferreteria_{date.today().isoformat()}.db'
    destino = os.path.join(backups_dir, nombre_hoy)
    if not os.path.exists(destino):
        shutil.copy2(db_path, destino)

    limite = date.today() - timedelta(days=30)
    for archivo in os.listdir(backups_dir):
        if archivo.startswith('ferreteria_') and archivo.endswith('.db'):
            fecha_str = archivo[len('ferreteria_'):-len('.db')]
            try:
                fecha_archivo = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except ValueError:
                continue
            if fecha_archivo < limite:
                try:
                    os.remove(os.path.join(backups_dir, archivo))
                except OSError:
                    pass

def abrir_navegador():
    url = 'http://localhost:5000/venta'

    # Iniciar una sesión de caja dedicada: Chromium manda window.print() a la
    # impresora predeterminada sin mostrar el diálogo cuando se activa el ticket.
    navegadores_linux = ['/usr/bin/chromium', '/usr/bin/brave', '/opt/brave-bin/brave-browser']
    for nav in navegadores_linux:
        if os.path.exists(nav):
            try:
                perfil_caja = os.path.join(BASE_DIR, 'instance', 'perfil_caja')
                subprocess.Popen([
                    nav, '--kiosk-printing', '--no-first-run',
                    f'--user-data-dir={perfil_caja}', f'--app={url}'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

    if os.path.exists('/usr/bin/firefox'):
        try:
            subprocess.Popen(['/usr/bin/firefox', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    # 2. En Windows, rutas típicas de Chrome
    rutas_chrome = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    ]

    for ruta in rutas_chrome:
        if os.path.exists(ruta):
            try:
                perfil_caja = os.path.join(BASE_DIR, 'instance', 'perfil_caja')
                subprocess.Popen([
                    ruta, '--kiosk-printing', '--no-first-run',
                    f'--user-data-dir={perfil_caja}', f'--app={url}'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

    # 3. Fallback genérico estándar
    try:
        webbrowser.open(url)
    except Exception:
        pass

if __name__ == '__main__':
    with app.app_context():
        migrar_db()
        backup_diario()

    # Abre el navegador automáticamente después de 1 segundo
    import threading
    timer = threading.Timer(1.0, abrir_navegador)
    timer.daemon = True
    timer.start()
    
    print("\n" + "="*60)
    print("FERRETERÍA - SISTEMA DE GESTIÓN")
    print("="*60)
    print("[OK] Servidor iniciado en http://localhost:5000")
    print("[OK] Base de datos: ferreteria.db")
    print("[OK] Presiona Ctrl+C para detener\n")
    
    app.run(debug=False, use_reloader=False, port=5000)
