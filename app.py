# app.py
import os, logging
from logging.handlers import RotatingFileHandler

from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, redirect, url_for, session
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

from pdf_service import (
    DATA_PATH,
    process_all_pdfs,
    clear_database,
)

from rag_service import ask_gemini, debug_rag_search  # <== tu servicio RAG

# ================== CONFIG LOGGING ==================
def setup_logging():
    if not os.path.exists("logs"):
        os.makedirs("logs")

    fmt = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )

    fh = RotatingFileHandler(
        'logs/app_gemini.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=3
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    logger.addHandler(ch)


# ================== CONFIG FLASK ==================
setup_logging()
app = Flask(__name__)
app.secret_key = "8ac0bba19e90196449cba5be82d79bb0a2a2855eb0f3263754d24fe193a3db72"  # puedes cambiarla si quieres

# ================== CONFIG BD MYSQL ==================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "asistente_voz",
    "port": 3306,
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def get_active_prompt_text() -> str:
    """
    Devuelve el contenido del prompt activo desde la tabla `prompts`.
    Si no hay ninguno, lanza una excepción.
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT contenido
            FROM prompts
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            raise RuntimeError("No hay ningún prompt activo en la tabla 'prompts'.")
        return row["contenido"]
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =============== MIDDLEWARE: PROTEGER RUTAS ===============
@app.before_request
def require_login():
    # Rutas públicas (no requieren login)
    public_endpoints = {
        "login",
        "register",
        "static",
        "rag_endpoint",    # <== /rag
        "debug_rag",       # <== /_debug_rag
    }

    # Si no sabemos el endpoint (None), no forzamos nada
    if request.endpoint is None:
        return

    if request.endpoint in public_endpoints:
        return

    # También dejamos fuera favicon
    if request.path.startswith("/static") or request.path.startswith("/favicon"):
        return

    # Si no hay usuario en sesión, mandar al login
    if not session.get("user_id") and request.endpoint not in {"login", "register"}:
        return redirect(url_for("login"))


# ================== RUTAS AUTH ==================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm", "").strip()

        if not username or not email or not password:
            return render_template("register.html", error="Todos los campos son obligatorios.")

        if password != confirm:
            return render_template("register.html", error="Las contraseñas no coinciden.")

        # Hash de contraseña
        password_hash = generate_password_hash(password)

        try:
            conn = get_db()
            cur = conn.cursor()
            # Verificar si ya existe usuario o correo
            cur.execute(
                "SELECT id FROM users WHERE username = %s OR email = %s",
                (username, email)
            )
            existing = cur.fetchone()
            if existing:
                return render_template("register.html", error="El usuario o email ya están registrados.")

            # Guardar el HASH en la columna password
            cur.execute(
                """
                INSERT INTO users (username, email, password)
                VALUES (%s, %s, %s)
                """,
                (username, email, password_hash)
            )
            conn.commit()
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username_or_email or not password:
            return render_template("login.html", error="Ingrese usuario/email y contraseña.")

        try:
            conn = get_db()
            cur = conn.cursor(dictionary=True)
            # Permitir login con username O email
            cur.execute(
                """
                SELECT id, username, email, password, is_active
                FROM users
                WHERE username = %s OR email = %s
                """,
                (username_or_email, username_or_email)
            )
            user = cur.fetchone()
        finally:
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        if not user:
            return render_template("login.html", error="Usuario no encontrado.")

        if not user["is_active"]:
            return render_template("login.html", error="Usuario inactivo, contacte al administrador.")

        if not check_password_hash(user["password"], password):
            return render_template("login.html", error="Contraseña incorrecta.")

        # Guardar sesión
        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================== RUTAS GESTOR DE PDF (PROTEGIDAS) ==================

@app.route("/")
def index():
    # solo llega aquí si está logueado
    files = os.listdir(DATA_PATH)
    files = [f for f in files if f.lower().endswith(".pdf")]
    total_size = sum(os.path.getsize(os.path.join(DATA_PATH, f)) for f in files)
    username = session.get("username", "Usuario")

    # ✅ OBTENER PREGUNTAS PARA "PREGUNTAS FRECUENTES"
    preguntas = []
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id, texto, fecha_creacion
            FROM preguntas
            ORDER BY fecha_creacion DESC
            LIMIT 50
        """)
        preguntas = cur.fetchall()
    except Exception as e:
        app.logger.exception("Error al obtener preguntas desde la BD")
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # Prompts (para Configuración)
    prompts = []
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id, nombre, contenido, is_active, created_at
            FROM prompts
            ORDER BY created_at DESC
        """)
        prompts = cur.fetchall()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    return render_template(
        "main.html",
        files=files,
        total_size=total_size,
        username=username,
        preguntas=preguntas,
        prompts=prompts,    # 👈 se usa en Configuración
    )


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "msg": "No se recibió archivo"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "msg": "Nombre de archivo vacío"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"ok": False, "msg": "Solo se permiten PDF"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(DATA_PATH, filename)
    file.save(save_path)

    process_all_pdfs()

    return jsonify({"ok": True, "filename": filename})


@app.route("/delete/<filename>", methods=["DELETE"])
def delete_file(filename):
    filename = secure_filename(filename)
    filepath = os.path.join(DATA_PATH, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        clear_database()
        process_all_pdfs()
        return jsonify({"ok": True})
    else:
        return jsonify({"ok": False, "msg": "Archivo no encontrado"}), 404


@app.route("/rebuild", methods=["POST"])
def rebuild():
    try:
        from pdf_service import clear_database, process_all_pdfs

        clear_database()
        process_all_pdfs()

        return jsonify({"ok": True, "msg": "La base de datos fue reconstruida."})

    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})


@app.route("/files/<filename>")
def serve_file(filename):
    return send_from_directory(DATA_PATH, filename)


# =============== RUTAS PARA GESTIONAR PROMPTS ===============

@app.route("/prompts/create", methods=["POST"])
def create_prompt():
    nombre = (request.form.get("nombre") or "").strip()
    contenido = (request.form.get("contenido") or "").strip()
    activar = request.form.get("activar")  # checkbox "on" o None

    if not nombre or not contenido:
        # podrías usar flash si activas mensajes
        return redirect(url_for("index"))  # vuelve al dashboard

    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # si se marca "activar", desactivar todos los demás
        if activar:
            cur.execute("UPDATE prompts SET is_active = 0")

        cur.execute(
            "INSERT INTO prompts (nombre, contenido, is_active) VALUES (%s, %s, %s)",
            (nombre, contenido, 1 if activar else 0)
        )
        conn.commit()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return redirect(url_for("index"))


@app.route("/prompts/<int:prompt_id>/activate", methods=["POST"])
def activate_prompt(prompt_id):
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        # desactivar todos
        cur.execute("UPDATE prompts SET is_active = 0")
        # activar el seleccionado
        cur.execute("UPDATE prompts SET is_active = 1 WHERE id = %s", (prompt_id,))
        conn.commit()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return redirect(url_for("index"))


@app.route("/prompts/<int:prompt_id>/update", methods=["POST"])
def update_prompt(prompt_id):
    nombre = (request.form.get("nombre") or "").strip()
    contenido = (request.form.get("contenido") or "").strip()

    if not nombre or not contenido:
        return redirect(url_for("index"))

    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE prompts SET nombre = %s, contenido = %s WHERE id = %s",
            (nombre, contenido, prompt_id)
        )
        conn.commit()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return redirect(url_for("index"))


@app.route("/prompts/<int:prompt_id>/delete", methods=["POST"])
def delete_prompt(prompt_id):
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM prompts WHERE id = %s", (prompt_id,))
        conn.commit()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return redirect(url_for("index"))




# ================== RUTAS RAG (GEMINI) ==================

@app.route("/_debug_rag", methods=["GET"])
def debug_rag():
    q = (request.args.get("q") or "").strip()
    data = debug_rag_search(q)
    return jsonify(data)


@app.route("/rag", methods=["GET", "POST", "OPTIONS"])
def rag_endpoint():
    # Preflight CORS
    if request.method == "OPTIONS":
        return ("", 204)

    if request.method == "GET":
        pregunta = (request.args.get("q") or "").strip()
    else:  # POST
        data = request.get_json(silent=True) or {}
        pregunta = (data.get("pregunta") or "").strip()

    if not pregunta:
        return jsonify({"error": "Se requiere 'q' (GET) o 'pregunta' (POST)"}), 400

    # ✅ Guardar la pregunta en la tabla `preguntas`
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO preguntas (texto) VALUES (%s)",
            (pregunta,)
        )
        conn.commit()
    except Exception as e:
        app.logger.exception("Error al guardar la pregunta en la BD")
        # si falla el guardado, seguimos igual con la respuesta
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # ✅ Procesar con Gemini usando el prompt de la BD
    try:
        prompt_template = get_active_prompt_text()   # 👈 viene de MySQL
        respuesta = ask_gemini(pregunta, prompt_template=prompt_template)
        return jsonify({"pregunta": pregunta, "respuesta": respuesta})
    except Exception as e:
        app.logger.exception("Error en /rag")
        return jsonify({"error": f"Error al procesar la pregunta: {str(e)}"}), 500


# ================== CORS GLOBAL ==================
@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    return response


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    app.run(host="0.0.0.0", port=5000, debug=True)
