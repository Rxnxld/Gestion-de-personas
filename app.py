import sqlite3, os, csv, io, hashlib, secrets
from datetime import timedelta
from flask import Flask, g, request, jsonify, send_from_directory, session, Response, send_file
from flask_cors import CORS

app = Flask(__name__, static_folder='.')
app.secret_key = secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(hours=8)
CORS(app, supports_credentials=True)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grupo.db')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.config')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()
app.teardown_appcontext(close_db)

def init_config():
    if not os.path.exists(CONFIG_PATH):
        pw = 'admin123'
        with open(CONFIG_PATH, 'w') as f:
            f.write(f'PASSWORD={hashlib.sha256(pw.encode()).hexdigest()}\n')
        print(f"  ── Config creada: password por defecto = {pw}")

def check_password(pw):
    try:
        with open(CONFIG_PATH) as f:
            for line in f:
                if line.startswith('PASSWORD='):
                    stored = line.strip().split('=', 1)[1]
                    return stored == hashlib.sha256(pw.encode()).hexdigest()
    except: return False
    return False

def set_password(pw):
    with open(CONFIG_PATH, 'w') as f:
        f.write(f'PASSWORD={hashlib.sha256(pw.encode()).hexdigest()}\n')

def login_required(fn):
    def wrapper(*a, **kw):
        if not session.get('logged_in'):
            return jsonify({'error':'No autenticado'}), 401
        return fn(*a, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper

def init_db():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS miembros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            apodo TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS fechas_tablas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS asistencias (
            miembro_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            valor INTEGER DEFAULT 0,
            PRIMARY KEY (miembro_id, fecha),
            FOREIGN KEY (miembro_id) REFERENCES miembros(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bingos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT UNIQUE NOT NULL,
            monto REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fechas_rifa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rifas (
            miembro_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            valor INTEGER DEFAULT 0,
            PRIMARY KEY (miembro_id, fecha),
            FOREIGN KEY (miembro_id) REFERENCES miembros(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS meses_ahorro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            orden INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ahorros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK(tipo IN ('normal','cumple','rifa')),
            miembro_id INTEGER NOT NULL,
            mes_id INTEGER NOT NULL,
            valor REAL DEFAULT 0,
            UNIQUE(tipo, miembro_id, mes_id),
            FOREIGN KEY (miembro_id) REFERENCES miembros(id) ON DELETE CASCADE,
            FOREIGN KEY (mes_id) REFERENCES meses_ahorro(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS cumple_meses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT UNIQUE NOT NULL,
            orden INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cumple_aportes (
            cumple_mes_id INTEGER NOT NULL,
            miembro_id INTEGER NOT NULL,
            valor INTEGER DEFAULT 0,
            PRIMARY KEY (cumple_mes_id, miembro_id),
            FOREIGN KEY (cumple_mes_id) REFERENCES cumple_meses(id) ON DELETE CASCADE,
            FOREIGN KEY (miembro_id) REFERENCES miembros(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS cumple_fechas (
            miembro_id INTEGER PRIMARY KEY,
            fecha TEXT NOT NULL,
            FOREIGN KEY (miembro_id) REFERENCES miembros(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS prestamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            miembro_id INTEGER NOT NULL,
            monto REAL NOT NULL,
            obs TEXT DEFAULT '',
            FOREIGN KEY (miembro_id) REFERENCES miembros(id) ON DELETE CASCADE
        );
        INSERT OR IGNORE INTO meses_ahorro (id, nombre, orden) VALUES
            (1,'ENERO',1),(2,'FEBRERO',2),(3,'MARZO',3),(4,'ABRIL',4),
            (5,'MAYO',5),(6,'JUNIO',6),(7,'JULIO',7),(8,'AGOSTO',8),
            (9,'SEPTIEMBRE',9),(10,'OCTUBRE',10),(11,'NOVIEMBRE',11),(12,'DICIEMBRE',12);
        INSERT OR IGNORE INTO cumple_meses (id, clave, orden) VALUES
            (1,'ENERO (2)',1),(2,'FEBRERO (4)',2),(3,'MARZO(2)',3),
            (4,'ABRIL(1)',4),(5,'MAYO(2)',5),(6,'OCTUBRE(4)',6),(7,'DICIEMBRE(3)',7);
    ''')
    db.commit(); db.close()

# ═══════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════

@app.route('/api/auth/status')
def auth_status():
    configurado = os.path.exists(CONFIG_PATH)
    return jsonify({'logged_in': session.get('logged_in', False), 'configurado': configurado})

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    pw = request.json.get('password', '')
    if not check_password(pw):
        return jsonify({'error':'Contraseña incorrecta'}), 401
    session.permanent = True
    session['logged_in'] = True
    return jsonify({'ok': True})

@app.route('/api/auth/setup', methods=['POST'])
def auth_setup():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                if 'PASSWORD=' in f.read() and session.get('logged_in'):
                    pass
                else:
                    return jsonify({'error':'Ya configurado. Inicia sesión primero.'}), 400
        except: pass
    pw = request.json.get('password', '')
    if len(pw) < 4: return jsonify({'error':'Mínimo 4 caracteres'}), 400
    set_password(pw)
    session.permanent = True
    session['logged_in'] = True
    return jsonify({'ok': True})

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def auth_change():
    old = request.json.get('old', '')
    new = request.json.get('new', '')
    if not check_password(old): return jsonify({'error':'Contraseña actual incorrecta'}), 400
    if len(new) < 4: return jsonify({'error':'Mínimo 4 caracteres'}), 400
    set_password(new)
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  MIEMBROS
# ═══════════════════════════════════════════

@app.route('/api/miembros', methods=['GET'])
@login_required
def get_miembros():
    return jsonify([dict(r) for r in get_db().execute("SELECT id, nombre, apodo FROM miembros ORDER BY id").fetchall()])

@app.route('/api/miembros', methods=['POST'])
@login_required
def add_miembro():
    data = request.json
    nombre = data.get('nombre', '').strip().upper()
    if not nombre: return jsonify({'error':'Nombre requerido'}), 400
    try:
        c = get_db().execute("INSERT INTO miembros (nombre, apodo) VALUES (?, ?)", (nombre, data.get('apodo','').strip()))
        get_db().commit()
        return jsonify({'id': c.lastrowid, 'nombre': nombre}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error':'El miembro ya existe'}), 409

@app.route('/api/miembros/<int:id>', methods=['DELETE'])
@login_required
def delete_miembro(id):
    get_db().execute("DELETE FROM miembros WHERE id=?", (id,))
    get_db().commit()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  TABLAS / ASISTENCIAS
# ═══════════════════════════════════════════

@app.route('/api/tablas/fechas', methods=['GET'])
@login_required
def get_fechas_tablas():
    return jsonify([r['fecha'] for r in get_db().execute("SELECT fecha FROM fechas_tablas ORDER BY fecha").fetchall()])

@app.route('/api/tablas/fechas', methods=['POST'])
@login_required
def add_fecha_tablas():
    fecha = request.json.get('fecha')
    if not fecha: return jsonify({'error':'Fecha requerida'}), 400
    try:
        get_db().execute("INSERT INTO fechas_tablas (fecha) VALUES (?)", (fecha,))
        get_db().commit()
        return jsonify({'ok': True}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error':'La fecha ya existe'}), 409

@app.route('/api/tablas/asistencias', methods=['GET'])
@login_required
def get_asistencias():
    rows = get_db().execute("SELECT m.nombre, a.fecha, a.valor FROM asistencias a JOIN miembros m ON a.miembro_id = m.id").fetchall()
    r = {}
    for row in rows:
        if row['nombre'] not in r: r[row['nombre']] = {}
        r[row['nombre']][row['fecha']] = row['valor']
    return jsonify(r)

@app.route('/api/tablas/asistencias', methods=['POST'])
@login_required
def set_asistencia():
    data = request.json
    db = get_db()
    miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (data['nombre'],)).fetchone()
    if not miembro: return jsonify({'error':'Miembro no encontrado'}), 404
    db.execute("INSERT INTO asistencias (miembro_id, fecha, valor) VALUES (?, ?, ?) ON CONFLICT(miembro_id, fecha) DO UPDATE SET valor=excluded.valor",
               (miembro['id'], data['fecha'], int(data.get('valor', 0))))
    db.commit()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  BINGOS
# ═══════════════════════════════════════════

@app.route('/api/bingos', methods=['GET'])
@login_required
def get_bingos():
    return jsonify([dict(r) for r in get_db().execute("SELECT id, fecha, monto FROM bingos ORDER BY fecha").fetchall()])

@app.route('/api/bingos', methods=['POST'])
@login_required
def add_bingo():
    data = request.json
    try:
        get_db().execute("INSERT INTO bingos (fecha, monto) VALUES (?, ?)", (data['fecha'], float(data['monto'])))
        get_db().commit()
        return jsonify({'ok': True}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error':'La fecha ya existe'}), 409

@app.route('/api/bingos/<int:id>', methods=['DELETE'])
@login_required
def delete_bingo(id):
    get_db().execute("DELETE FROM bingos WHERE id=?", (id,))
    get_db().commit()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  RIFA
# ═══════════════════════════════════════════

@app.route('/api/rifa/fechas', methods=['GET'])
@login_required
def get_fechas_rifa():
    return jsonify([r['fecha'] for r in get_db().execute("SELECT fecha FROM fechas_rifa ORDER BY fecha").fetchall()])

@app.route('/api/rifa/fechas', methods=['POST'])
@login_required
def add_fecha_rifa():
    fecha = request.json.get('fecha')
    if not fecha: return jsonify({'error':'Fecha requerida'}), 400
    try:
        get_db().execute("INSERT INTO fechas_rifa (fecha) VALUES (?)", (fecha,))
        get_db().commit()
        return jsonify({'ok': True}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error':'La fecha ya existe'}), 409

@app.route('/api/rifa', methods=['GET'])
@login_required
def get_rifas():
    rows = get_db().execute("SELECT m.nombre, r.fecha, r.valor FROM rifas r JOIN miembros m ON r.miembro_id = m.id").fetchall()
    r = {}
    for row in rows:
        if row['nombre'] not in r: r[row['nombre']] = {}
        r[row['nombre']][row['fecha']] = row['valor']
    return jsonify(r)

@app.route('/api/rifa', methods=['POST'])
@login_required
def set_rifa():
    data = request.json
    db = get_db()
    miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (data['nombre'],)).fetchone()
    if not miembro: return jsonify({'error':'Miembro no encontrado'}), 404
    db.execute("INSERT INTO rifas (miembro_id, fecha, valor) VALUES (?, ?, ?) ON CONFLICT(miembro_id, fecha) DO UPDATE SET valor=excluded.valor",
               (miembro['id'], data['fecha'], int(data.get('valor', 0))))
    db.commit()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  AHORROS
# ═══════════════════════════════════════════

@app.route('/api/ahorros/<tipo>', methods=['GET'])
@login_required
def get_ahorros(tipo):
    if tipo not in ('normal','cumple','rifa'): return jsonify({'error':'Tipo inválido'}), 400
    rows = get_db().execute("SELECT m.nombre, ma.nombre as mes, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo=?", (tipo,)).fetchall()
    r = {}
    for row in rows:
        if row['nombre'] not in r: r[row['nombre']] = {}
        r[row['nombre']][row['mes']] = row['valor']
    return jsonify(r)

@app.route('/api/ahorros/<tipo>', methods=['POST'])
@login_required
def set_ahorro(tipo):
    if tipo not in ('normal','cumple','rifa'): return jsonify({'error':'Tipo inválido'}), 400
    data = request.json
    db = get_db()
    miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (data['nombre'],)).fetchone()
    if not miembro: return jsonify({'error':'Miembro no encontrado'}), 404
    mes_row = db.execute("SELECT id FROM meses_ahorro WHERE nombre=?", (data['mes'],)).fetchone()
    if not mes_row: return jsonify({'error':'Mes inválido'}), 400
    db.execute("INSERT INTO ahorros (tipo, miembro_id, mes_id, valor) VALUES (?, ?, ?, ?) ON CONFLICT(tipo, miembro_id, mes_id) DO UPDATE SET valor=excluded.valor",
               (tipo, miembro['id'], mes_row['id'], float(data.get('valor', 0))))
    db.commit()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  CUMPLEAÑOS
# ═══════════════════════════════════════════

@app.route('/api/cumple/meses', methods=['GET'])
@login_required
def get_cumple_meses():
    return jsonify([r['clave'] for r in get_db().execute("SELECT clave FROM cumple_meses ORDER BY orden").fetchall()])

@app.route('/api/cumple/aportes', methods=['GET'])
@login_required
def get_cumple_aportes():
    rows = get_db().execute("SELECT cm.clave, m.nombre, ca.valor FROM cumple_aportes ca JOIN cumple_meses cm ON ca.cumple_mes_id = cm.id JOIN miembros m ON ca.miembro_id = m.id").fetchall()
    r = {}
    for row in rows:
        if row['clave'] not in r: r[row['clave']] = {}
        r[row['clave']][row['nombre']] = row['valor']
    return jsonify(r)

@app.route('/api/cumple/aportes', methods=['POST'])
@login_required
def set_cumple_aporte():
    data = request.json
    db = get_db()
    miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (data['nombre'],)).fetchone()
    if not miembro: return jsonify({'error':'Miembro no encontrado'}), 404
    cm = db.execute("SELECT id FROM cumple_meses WHERE clave=?", (data['clave'],)).fetchone()
    if not cm: return jsonify({'error':'Mes inválido'}), 400
    db.execute("INSERT INTO cumple_aportes (cumple_mes_id, miembro_id, valor) VALUES (?, ?, ?) ON CONFLICT(cumple_mes_id, miembro_id) DO UPDATE SET valor=excluded.valor",
               (cm['id'], miembro['id'], int(data.get('valor', 0))))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/cumple/fechas', methods=['GET'])
@login_required
def get_cumple_fechas():
    rows = get_db().execute("SELECT m.nombre, cf.fecha FROM cumple_fechas cf JOIN miembros m ON cf.miembro_id = m.id").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/cumple/fechas', methods=['POST'])
@login_required
def add_cumple_fecha():
    data = request.json
    miembro = get_db().execute("SELECT id FROM miembros WHERE nombre=?", (data['nombre'],)).fetchone()
    if not miembro: return jsonify({'error':'Miembro no encontrado'}), 404
    try:
        get_db().execute("INSERT INTO cumple_fechas (miembro_id, fecha) VALUES (?, ?)", (miembro['id'], data['fecha']))
        get_db().commit()
        return jsonify({'ok': True}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error':'El miembro ya tiene fecha'}), 409

@app.route('/api/cumple/fechas/<int:id>', methods=['DELETE'])
@login_required
def delete_cumple_fecha(id):
    get_db().execute("DELETE FROM cumple_fechas WHERE miembro_id=?", (id,))
    get_db().commit()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  PRESTAMOS
# ═══════════════════════════════════════════

@app.route('/api/prestamos', methods=['GET'])
@login_required
def get_prestamos():
    return jsonify([dict(r) for r in get_db().execute("SELECT p.id, m.nombre, p.monto, p.obs FROM prestamos p JOIN miembros m ON p.miembro_id = m.id ORDER BY p.id").fetchall()])

@app.route('/api/prestamos', methods=['POST'])
@login_required
def add_prestamo():
    data = request.json
    miembro = get_db().execute("SELECT id FROM miembros WHERE nombre=?", (data['nombre'],)).fetchone()
    if not miembro: return jsonify({'error':'Miembro no encontrado'}), 404
    c = get_db().execute("INSERT INTO prestamos (miembro_id, monto, obs) VALUES (?, ?, ?)", (miembro['id'], float(data['monto']), data.get('obs', '')))
    get_db().commit()
    return jsonify({'id': c.lastrowid}), 201

@app.route('/api/prestamos/<int:id>', methods=['DELETE'])
@login_required
def delete_prestamo(id):
    get_db().execute("DELETE FROM prestamos WHERE id=?", (id,))
    get_db().commit()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════
#  DATOS COMPLETOS
# ═══════════════════════════════════════════

@app.route('/api/datos/completos', methods=['GET'])
@login_required
def get_datos_completos():
    db = get_db()
    miembros = [dict(r) for r in db.execute("SELECT id, nombre, apodo FROM miembros ORDER BY id").fetchall()]
    fechas_tablas = [r['fecha'] for r in db.execute("SELECT fecha FROM fechas_tablas ORDER BY fecha").fetchall()]

    as_raw = db.execute("SELECT m.nombre, a.fecha, a.valor FROM asistencias a JOIN miembros m ON a.miembro_id = m.id").fetchall()
    asistencias = {}
    for r in as_raw:
        if r['nombre'] not in asistencias: asistencias[r['nombre']] = {}
        asistencias[r['nombre']][r['fecha']] = r['valor']

    bingos = [dict(r) for r in db.execute("SELECT id, fecha, monto FROM bingos ORDER BY fecha").fetchall()]
    fechas_rifa = [r['fecha'] for r in db.execute("SELECT fecha FROM fechas_rifa ORDER BY fecha").fetchall()]

    ri_raw = db.execute("SELECT m.nombre, r.fecha, r.valor FROM rifas r JOIN miembros m ON r.miembro_id = m.id").fetchall()
    rifas = {}
    for r in ri_raw:
        if r['nombre'] not in rifas: rifas[r['nombre']] = {}
        rifas[r['nombre']][r['fecha']] = r['valor']

    def gah(tipo):
        rows = db.execute("SELECT m.nombre, ma.nombre as mes, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo=?", (tipo,)).fetchall()
        r = {}
        for row in rows:
            if row['nombre'] not in r: r[row['nombre']] = {}
            r[row['nombre']][row['mes']] = row['valor']
        return r

    cm = [r['clave'] for r in db.execute("SELECT clave FROM cumple_meses ORDER BY orden").fetchall()]
    ca_raw = db.execute("SELECT cm.clave, m.nombre, ca.valor FROM cumple_aportes ca JOIN cumple_meses cm ON ca.cumple_mes_id = cm.id JOIN miembros m ON ca.miembro_id = m.id").fetchall()
    ca = {}
    for r in ca_raw:
        if r['clave'] not in ca: ca[r['clave']] = {}
        ca[r['clave']][r['nombre']] = r['valor']

    cf = [dict(r) for r in db.execute("SELECT m.nombre, cf.fecha FROM cumple_fechas cf JOIN miembros m ON cf.miembro_id = m.id").fetchall()]
    prestamos = [dict(r) for r in db.execute("SELECT p.id, m.nombre, p.monto, p.obs FROM prestamos p JOIN miembros m ON p.miembro_id = m.id ORDER BY p.id").fetchall()]

    return jsonify({
        'miembros': miembros, 'fechasTablas': fechas_tablas, 'asistencias': asistencias,
        'bingos': bingos, 'fechasRifa': fechas_rifa, 'rifas': rifas,
        'ahorroNormal': gah('normal'), 'ahorroCumple': gah('cumple'),
        'ahorroRifa': gah('rifa'), 'cumpleMeses': cm,
        'cumpleAportes': ca, 'cumpleFechas': cf, 'prestamos': prestamos
    })

# ═══════════════════════════════════════════
#  EXPORTAR
# ═══════════════════════════════════════════

def _rows_to_csv(rows, cols):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cols)
    for r in rows: w.writerow(r)
    out.seek(0)
    return out

@app.route('/api/export/csv/<tabla>')
@login_required
def export_csv(tabla):
    db = get_db()
    mapping = {
        'miembros': ("SELECT nombre, apodo FROM miembros ORDER BY id", ['nombre','apodo']),
        'asistencias': ("SELECT m.nombre, a.fecha, CASE WHEN a.valor=1 THEN 'Si' ELSE 'No' END FROM asistencias a JOIN miembros m ON a.miembro_id = m.id ORDER BY a.fecha,m.nombre", ['miembro','fecha','asistio']),
        'bingos': ("SELECT fecha, monto FROM bingos ORDER BY fecha", ['fecha','monto']),
        'rifas': ("SELECT m.nombre, r.fecha, r.valor FROM rifas r JOIN miembros m ON r.miembro_id = m.id ORDER BY r.fecha,m.nombre", ['miembro','fecha','cantidad']),
        'ahorro_normal': ("SELECT m.nombre, ma.nombre as mes, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo='normal' ORDER BY ma.orden,m.nombre", ['miembro','mes','monto']),
        'ahorro_cumple': ("SELECT m.nombre, ma.nombre as mes, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo='cumple' ORDER BY ma.orden,m.nombre", ['miembro','mes','monto']),
        'ahorro_rifa': ("SELECT m.nombre, ma.nombre as mes, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo='rifa' ORDER BY ma.orden,m.nombre", ['miembro','mes','monto']),
        'cumple_aportes': ("SELECT cm.clave, m.nombre, ca.valor FROM cumple_aportes ca JOIN cumple_meses cm ON ca.cumple_mes_id = cm.id JOIN miembros m ON ca.miembro_id = m.id ORDER BY cm.orden,m.nombre", ['mes','miembro','cantidad']),
        'cumple_fechas': ("SELECT m.nombre, cf.fecha FROM cumple_fechas cf JOIN miembros m ON cf.miembro_id = m.id ORDER BY cf.fecha", ['miembro','fecha']),
        'prestamos': ("SELECT m.nombre, p.monto, p.obs FROM prestamos p JOIN miembros m ON p.miembro_id = m.id ORDER BY p.id", ['miembro','monto','observacion']),
    }
    if tabla not in mapping: return jsonify({'error':'Tabla no encontrada'}), 404
    q, cols = mapping[tabla]
    rows = db.execute(q).fetchall()
    out = _rows_to_csv([tuple(r) for r in rows], cols)
    return Response(out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename={tabla}.csv'})

@app.route('/api/export/todo')
@login_required
def export_todo():
    import zipfile
    db = get_db()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for key, (q, cols) in {
            'miembros': ("SELECT nombre, apodo FROM miembros ORDER BY id", ['nombre','apodo']),
            'asistencias': ("SELECT m.nombre, a.fecha, CASE WHEN a.valor=1 THEN 'Si' ELSE 'No' END FROM asistencias a JOIN miembros m ON a.miembro_id = m.id ORDER BY a.fecha,m.nombre", ['miembro','fecha','asistio']),
            'bingos': ("SELECT fecha, monto FROM bingos ORDER BY fecha", ['fecha','monto']),
            'rifas': ("SELECT m.nombre, r.fecha, r.valor FROM rifas r JOIN miembros m ON r.miembro_id = m.id ORDER BY r.fecha,m.nombre", ['miembro','fecha','cantidad']),
            'ahorro_normal': ("SELECT m.nombre, ma.nombre, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo='normal' ORDER BY ma.orden,m.nombre", ['miembro','mes','monto']),
            'ahorro_cumple': ("SELECT m.nombre, ma.nombre, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo='cumple' ORDER BY ma.orden,m.nombre", ['miembro','mes','monto']),
            'ahorro_rifa': ("SELECT m.nombre, ma.nombre, a.valor FROM ahorros a JOIN miembros m ON a.miembro_id = m.id JOIN meses_ahorro ma ON a.mes_id = ma.id WHERE a.tipo='rifa' ORDER BY ma.orden,m.nombre", ['miembro','mes','monto']),
            'cumple_aportes': ("SELECT cm.clave, m.nombre, ca.valor FROM cumple_aportes ca JOIN cumple_meses cm ON ca.cumple_mes_id = cm.id JOIN miembros m ON ca.miembro_id = m.id ORDER BY cm.orden,m.nombre", ['mes','miembro','cantidad']),
            'cumple_fechas': ("SELECT m.nombre, cf.fecha FROM cumple_fechas cf JOIN miembros m ON cf.miembro_id = m.id ORDER BY cf.fecha", ['miembro','fecha']),
            'prestamos': ("SELECT m.nombre, p.monto, p.obs FROM prestamos p JOIN miembros m ON p.miembro_id = m.id ORDER BY p.id", ['miembro','monto','observacion']),
        }.items():
            rows = db.execute(q).fetchall()
            out = _rows_to_csv([tuple(r) for r in rows], cols)
            zf.writestr(f'{key}.csv', out.getvalue())
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='grupo_portoviejo_completo.zip')

# ═══════════════════════════════════════════
#  IMPORTAR DESDE EXCEL
# ═══════════════════════════════════════════

@app.route('/api/import/excel', methods=['POST'])
@login_required
def import_excel():
    if 'file' not in request.files:
        return jsonify({'error':'No se envió archivo'}), 400
    f = request.files['file']
    if not f.filename.endswith('.xlsx'):
        return jsonify({'error':'Solo archivos .xlsx'}), 400

    try:
        from openpyxl import load_workbook
    except ImportError:
        return jsonify({'error':'openpyxl no instalado'}), 500

    try:
        wb = load_workbook(f, data_only=True)
    except Exception as e:
        return jsonify({'error':f'Error al leer Excel: {str(e)}'}), 400

    db = get_db()
    resumen = {'miembros':0, 'asistencias':0, 'bingos':0, 'rifas':0, 'ahorros':0, 'cumple':0, 'prestamos':0}
    errores = []

    for ws in wb.worksheets:
        name = ws.title.strip().upper()
        rows_list = list(ws.iter_rows(values_only=True))
        if not rows_list: continue

        if 'MIEMBRO' in name or name == 'MIEMBROS':
            for row in rows_list[1:]:
                nom = str(row[0]).strip().upper() if row[0] else ''
                apo = str(row[1]).strip() if len(row)>1 and row[1] else ''
                if nom:
                    try:
                        db.execute("INSERT INTO miembros (nombre, apodo) VALUES (?, ?)", (nom, apo))
                        resumen['miembros'] += 1
                    except sqlite3.IntegrityError: pass
            db.commit()

        elif 'ASISTENCIA' in name or name == 'TABLAS':
            headers = [str(c) for c in rows_list[0]] if rows_list[0] else []
            for row in rows_list[1:]:
                nom = str(row[0]).strip().upper() if row[0] else ''
                if not nom: continue
                miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (nom,)).fetchone()
                if not miembro: continue
                for j, fecha_raw in enumerate(headers[1:], 1):
                    if j >= len(row): break
                    fecha = str(fecha_raw).strip() if fecha_raw else ''
                    val = 1 if row[j] and str(row[j]).strip() in ('1','Si','SI','si','x','X','✓') else 0
                    if fecha:
                        try:
                            db.execute("INSERT OR IGNORE INTO fechas_tablas (fecha) VALUES (?)", (fecha,))
                            db.execute("INSERT INTO asistencias (miembro_id, fecha, valor) VALUES (?, ?, ?) ON CONFLICT(miembro_id, fecha) DO UPDATE SET valor=excluded.valor",
                                       (miembro['id'], fecha, val))
                            resumen['asistencias'] += 1
                        except: pass
            db.commit()

        elif 'BINGO' in name:
            for row in rows_list[1:]:
                if not row[0] or not row[1]: continue
                try:
                    db.execute("INSERT OR IGNORE INTO bingos (fecha, monto) VALUES (?, ?)",
                               (str(row[0]).strip(), float(row[1])))
                    resumen['bingos'] += 1
                except: pass
            db.commit()

        elif 'RIFA' in name:
            headers = [str(c) for c in rows_list[0]] if rows_list[0] else []
            for row in rows_list[1:]:
                nom = str(row[0]).strip().upper() if row[0] else ''
                if not nom: continue
                miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (nom,)).fetchone()
                if not miembro: continue
                for j, fecha_raw in enumerate(headers[1:], 1):
                    if j >= len(row): break
                    fecha = str(fecha_raw).strip() if fecha_raw else ''
                    try: val = int(float(str(row[j]))) if row[j] else 0
                    except: val = 0
                    if fecha:
                        try:
                            db.execute("INSERT OR IGNORE INTO fechas_rifa (fecha) VALUES (?)", (fecha,))
                            db.execute("INSERT INTO rifas (miembro_id, fecha, valor) VALUES (?, ?, ?) ON CONFLICT(miembro_id, fecha) DO UPDATE SET valor=excluded.valor",
                                       (miembro['id'], fecha, val))
                            resumen['rifas'] += 1
                        except: pass
            db.commit()

        elif 'AHORRO' in name or 'AHORROS' in name:
            headers = [str(c).strip().upper() for c in rows_list[0]] if rows_list[0] else []
            tipo = 'normal'
            if 'CUMPLE' in name: tipo = 'cumple'
            if 'RIFA' in name: tipo = 'rifa'
            for row in rows_list[1:]:
                nom = str(row[0]).strip().upper() if row[0] else ''
                if not nom: continue
                miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (nom,)).fetchone()
                if not miembro: continue
                for j, h in enumerate(headers[1:], 1):
                    if j >= len(row): break
                    if h in ('TOTAL',''): continue
                    mes = h.capitalize()
                    try: val = float(row[j]) if row[j] else 0
                    except: val = 0
                    if val:
                        mes_row = db.execute("SELECT id FROM meses_ahorro WHERE nombre=?", (mes,)).fetchone()
                        if mes_row:
                            db.execute("INSERT INTO ahorros (tipo, miembro_id, mes_id, valor) VALUES (?, ?, ?, ?) ON CONFLICT(tipo, miembro_id, mes_id) DO UPDATE SET valor=excluded.valor",
                                       (tipo, miembro['id'], mes_row['id'], val))
                            resumen['ahorros'] += 1
            db.commit()

        elif 'CUMPLE' in name and ('APORTE' in name or 'MES' in name):
            headers = [str(c).strip() for c in rows_list[0]] if rows_list[0] else []
            for row in rows_list[1:]:
                nom = str(row[0]).strip().upper() if row[0] else ''
                if not nom: continue
                miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (nom,)).fetchone()
                if not miembro: continue
                for j, h in enumerate(headers[1:], 1):
                    if j >= len(row): break
                    if h in ('TOTAL',''): continue
                    try: val = int(float(str(row[j]))) if row[j] else 0
                    except: val = 0
                    if val:
                        cm = db.execute("SELECT id FROM cumple_meses WHERE clave=?", (h.strip(),)).fetchone()
                        if cm:
                            db.execute("INSERT INTO cumple_aportes (cumple_mes_id, miembro_id, valor) VALUES (?, ?, ?) ON CONFLICT(cumple_mes_id, miembro_id) DO UPDATE SET valor=excluded.valor",
                                       (cm['id'], miembro['id'], val))
                            resumen['cumple'] += 1
            db.commit()

        elif 'PRESTAMO' in name:
            for row in rows_list[1:]:
                nom = str(row[0]).strip().upper() if row[0] else ''
                if not nom: continue
                try: monto = float(row[1]) if len(row)>1 and row[1] else 0
                except: monto = 0
                if not monto: continue
                obs = str(row[2]).strip() if len(row)>2 and row[2] else ''
                miembro = db.execute("SELECT id FROM miembros WHERE nombre=?", (nom,)).fetchone()
                if miembro:
                    db.execute("INSERT INTO prestamos (miembro_id, monto, obs) VALUES (?, ?, ?)", (miembro['id'], monto, obs))
                    resumen['prestamos'] += 1
            db.commit()

    db.commit()
    return jsonify({'ok': True, 'resumen': resumen, 'errores': errores})

# ═══════════════════════════════════════════
#  SPA
# ═══════════════════════════════════════════

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# ═══════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════

if __name__ == '__main__':
    init_db()
    init_config()
    print("=" * 50)
    print("  Grupo Calle Portoviejo - Servidor SQL")
    print(f"  DB: {DB_PATH}")
    print("  http://localhost:5000")
    print("  Password default: admin123")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
