from flask import Flask, render_template, request, redirect, url_for, session, flash
import random
import csv
import re
import json
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "clave_secreta_quiz"

# rutas absolutas para no tener el problema del "archivo no encontrado"
# cuando se corre desde otra carpeta. Lo aprendimos a las malas lol
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CSV  = os.path.join(BASE_DIR, "jugadores.csv")
USUARIOS_CSV = os.path.join(BASE_DIR, "usuarios.csv")

# columnas de cada csv (tienen que coincidir exacto o se rompe todo)
CAMPOS_CSV  = ["nombre", "genero", "correo", "puntaje_quiz", "puntaje_minijuego", "fecha"]
CAMPOS_USER = ["nombre", "correo", "password", "genero", "fecha_registro"]
GENEROS     = ["Mujer", "Hombre", "No-binario", "Otro"]

# cargamos las preguntas una sola vez al arrancar la app
with open(os.path.join(BASE_DIR, "preguntas.json"), encoding="utf-8") as f:
    preguntas_completas = json.load(f)

# también cargamos la retroalimentación para mostrarla en el panel lateral
# si el archivo no existe simplemente usamos un diccionario vacío y no explota
_retro_path = os.path.join(BASE_DIR, "retroalimentacion.json")
if os.path.exists(_retro_path):
    with open(_retro_path, encoding="utf-8") as f:
        retroalimentacion = json.load(f)
else:
    retroalimentacion = {}

# cada respuesta correcta del quiz vale 250 puntos
PUNTOS_POR_PREGUNTA = 250


# ---- VALIDACIONES ----
# funciones para verificar que el usuario no meta cualquier cosa en los campos

def nombre_valido(nombre):
    if not nombre.strip():
        return "Por favor, escribe tu nombre."
    # solo letras y espacios, sin números ni caracteres raros
    if not re.fullmatch(r"[A-Za-záéíóúÁÉÍÓÚüÜñÑ ]+", nombre.strip()):
        return "El nombre solo puede tener letras y espacios."
    return ""

def correo_valido(correo):
    if not correo.strip():
        return "Por favor, escribe tu correo."
    # formato básico nombre@dominio.com
    if not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo.strip()):
        return "El correo debe tener el formato: nombre@dominio.com"
    return ""

def password_valida(pw):
    # minimo 6 caracteres, nada más por ahora
    if not pw or len(pw) < 6:
        return "La contraseña debe tener al menos 6 caracteres."
    return ""


# ---- MANEJO DE USUARIOS ----
# usamos un csv en vez de base de datos porque es más simple para el profe

def leer_usuarios():
    # lee todos los usuarios del csv y los devuelve como lista de dicts
    usuarios = []
    try:
        with open(USUARIOS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                usuarios.append(row)
    except FileNotFoundError:
        # primera vez que corre, el archivo todavía no existe
        pass
    return usuarios

def guardar_usuario(nombre, correo, password, genero):
    # revisar si el archivo está vacío para saber si hay que escribir el encabezado
    escribir_cabecera = False
    try:
        with open(USUARIOS_CSV, "r", encoding="utf-8") as f:
            if not f.read(1):
                escribir_cabecera = True
    except FileNotFoundError:
        escribir_cabecera = True

    # modo "a" para agregar sin borrar lo que ya había
    with open(USUARIOS_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_USER)
        if escribir_cabecera:
            writer.writeheader()
        writer.writerow({
            "nombre":         nombre,
            "correo":         correo.lower(),  # guardamos todo en minúscula para comparar fácil
            "password":       password,
            "genero":         genero,
            "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

def buscar_usuario(correo):
    # busca un usuario por correo, devuelve None si no lo encuentra
    for u in leer_usuarios():
        if u["correo"] == correo.lower():
            return u
    return None

def correo_registrado(correo):
    # helper rápido para saber si el correo ya está en uso
    return buscar_usuario(correo) is not None


# ---- GUARDAR PARTIDAS ----
# un solo registro por jugador (por correo).
# si juega de nuevo, solo se actualiza si supera su puntaje anterior.

def leer_partidas():
    partidas = []
    try:
        with open(ARCHIVO_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # convertir puntajes a int, si están vacíos o raros ponemos 0
                try:
                    row["puntaje_quiz"]      = int(row.get("puntaje_quiz", 0) or 0)
                    row["puntaje_minijuego"] = int(row.get("puntaje_minijuego", 0) or 0)
                except (ValueError, KeyError):
                    row["puntaje_quiz"]      = 0
                    row["puntaje_minijuego"] = 0
                partidas.append(row)
    except FileNotFoundError:
        pass
    return partidas

def escribir_partidas(partidas):
    # sobreescribe el csv completo con la lista actualizada
    with open(ARCHIVO_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
        writer.writeheader()
        writer.writerows(partidas)

def guardar_partida(nombre, genero, correo, puntos, fuente="quiz"):
    partidas = leer_partidas()
    correo   = correo.lower()

    # buscar si ya jugó antes
    registro = next((p for p in partidas if p["correo"] == correo), None)

    if registro is None:
        # nunca había jugado: creamos su fila
        registro = {
            "nombre":            nombre,
            "genero":            genero,
            "correo":            correo,
            "puntaje_quiz":      0,
            "puntaje_minijuego": 0,
            "fecha":             datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        partidas.append(registro)

    # elegir el campo correcto según de dónde viene el puntaje
    campo = "puntaje_quiz" if fuente == "quiz" else "puntaje_minijuego"

    # solo actualizamos si el nuevo puntaje es mejor (no queremos bajarle el puntaje)
    if int(puntos) > int(registro[campo]):
        registro[campo] = int(puntos)
        registro["fecha"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    escribir_partidas(partidas)


# ---- DECORADOR DE LOGIN ----
# esto protege las rutas que requieren estar logueado
# si no estás logueado, te manda al login

def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_logueado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ---- AUTENTICACIÓN ----

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        correo   = request.form.get("correo", "").strip()
        password = request.form.get("password", "").strip()
        usuario  = buscar_usuario(correo)

        # verificar que exista y que la contraseña coincida
        if not usuario or usuario["password"] != password:
            error = "Correo o contraseña incorrectos."
        else:
            session["usuario_logueado"] = True
            session["jugador"] = {
                "nombre": usuario["nombre"],
                "genero": usuario["genero"],
                "correo": usuario["correo"],
            }
            return redirect(url_for("registro"))

    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    errores = {}
    datos   = {}

    if request.method == "POST":
        nombre   = request.form.get("nombre", "").strip()
        correo   = request.form.get("correo", "").strip()
        password = request.form.get("password", "").strip()
        genero   = request.form.get("genero", "").strip()

        # validar cada campo y guardar el error si hay
        errores["nombre"]   = nombre_valido(nombre)
        errores["correo"]   = correo_valido(correo)
        errores["password"] = password_valida(password)
        if not genero:
            errores["genero"] = "Por favor, elige tu género."

        # verificar si el correo ya está ocupado (solo si el formato era válido)
        if correo and not errores["correo"] and correo_registrado(correo):
            errores["correo"] = "Este correo ya está registrado."

        # para volver a llenar el formulario si hay errores
        datos = {"nombre": nombre, "correo": correo}

        # si no hay ningún error, guardamos y logueamos al usuario
        if not any(errores.values()):
            guardar_usuario(nombre, correo, password, genero)
            session["usuario_logueado"] = True
            session["jugador"] = {"nombre": nombre, "genero": genero, "correo": correo}
            return redirect(url_for("registro"))

    return render_template("register.html", errores=errores, datos=datos, generos=GENEROS)


@app.route("/logout")
def logout():
    # borramos todo de la sesión y mandamos al login
    session.clear()
    return redirect(url_for("login"))


# ---- RUTAS DEL JUEGO ----

@app.route("/", methods=["GET", "POST"])
@login_requerido
def registro():
    # esta es la pantalla de inicio del quiz (después del login)
    jugador     = session.get("jugador", {})
    error_extra = ""

    if request.method == "POST":
        # elegir 10 preguntas al azar y mezclar las opciones de cada una
        preguntas = random.sample(preguntas_completas, min(10, len(preguntas_completas)))
        for p in preguntas:
            opciones = p["opciones"][:]
            random.shuffle(opciones)
            p["opciones_mezcladas"] = opciones

        # guardar en sesión para ir avanzando pregunta a pregunta
        session["preguntas"] = preguntas
        session["indice"]    = 0
        session["puntaje"]   = 0
        return redirect(url_for("juego"))

    return render_template("registro.html", jugador=jugador, generos=GENEROS,
                           error_extra=error_extra)


@app.route("/juego", methods=["GET", "POST"])
@login_requerido
def juego():
    preguntas = session.get("preguntas", [])
    indice    = session.get("indice", 0)

    # si no hay preguntas o ya terminó, ir al resultado
    if not preguntas or indice >= len(preguntas):
        return redirect(url_for("resultado"))

    error = ""
    if request.method == "POST":
        respuesta       = request.form.get("respuesta", "")
        pregunta_actual = preguntas[indice]

        if not respuesta:
            error = "Elige una opción antes de continuar."
        else:
            if respuesta == pregunta_actual["correcta"]:
                # sumar los puntos correspondientes
                session["puntaje"] = session.get("puntaje", 0) + PUNTOS_POR_PREGUNTA
            # avanzar a la siguiente pregunta
            session["indice"] = indice + 1
            return redirect(url_for("juego"))

    pregunta_actual = preguntas[indice]
    return render_template("juego.html",
                           pregunta=pregunta_actual,
                           numero=indice + 1,
                           total=len(preguntas),
                           error=error,
                           retroalimentacion=retroalimentacion)


@app.route("/resultado")
@login_requerido
def resultado():
    jugador = session.get("jugador", {})
    puntos  = session.get("puntaje", 0)
    total   = len(session.get("preguntas", []))

    # cuántas preguntas acertó (para mostrar en la pantalla de resultado)
    aciertos = puntos // PUNTOS_POR_PREGUNTA

    if jugador:
        guardar_partida(jugador["nombre"], jugador["genero"],
                        jugador["correo"], puntos, fuente="quiz")

    # limpiar los datos del quiz de la sesión pero dejar el login activo
    session.pop("preguntas", None)
    session.pop("indice",    None)
    session.pop("puntaje",   None)

    return render_template("resultado.html", jugador=jugador,
                           puntaje=puntos, aciertos=aciertos, total=total)


@app.route("/minijuego")
@login_requerido
def minijuego():
    return render_template("juego_minijuego.html")


@app.route("/guardar_minijuego", methods=["POST"])
@login_requerido
def guardar_minijuego():
    # el minijuego llama esto con fetch para guardar el puntaje sin recargar
    jugador = session.get("jugador", {})
    puntos  = request.form.get("puntos", 0, type=int)
    if jugador:
        guardar_partida(jugador["nombre"], jugador["genero"],
                        jugador["correo"], puntos, fuente="minijuego")
    return ("", 204)  # 204 = éxito sin contenido


@app.route("/leaderboard")
@login_requerido
def leaderboard():
    jugador  = session.get("jugador", {})
    partidas = leer_partidas()

    # sumar quiz + minijuego para el puntaje total y ordenar de mayor a menor
    for p in partidas:
        p["puntaje_total"] = p["puntaje_quiz"] + p["puntaje_minijuego"]
    partidas.sort(key=lambda p: p["puntaje_total"], reverse=True)

    mejor = partidas[0]["puntaje_total"] if partidas else 0

    return render_template(
        "leaderboard.html",
        jugadores=partidas,
        jugador_actual=jugador,
        mejor_puntaje=mejor,
    )


# ---- PANEL DE ADMINISTRADOR ----
# las credenciales del admin son fijas aquí, no están en el csv de usuarios
# usuario: admin  |  contraseña: 2014
ADMIN_USER = "admin"
ADMIN_PASS = "2014"

def admin_requerido(f):
    # igual que login_requerido pero para el panel de administrador
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logueado"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        usuario  = request.form.get("usuario", "").strip()
        password = request.form.get("password", "").strip()
        if usuario == ADMIN_USER and password == ADMIN_PASS:
            session["admin_logueado"] = True
            return redirect(url_for("admin_panel"))
        error = "Credenciales incorrectas."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logueado", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_requerido
def admin_panel():
    partidas = leer_partidas()
    # calcular puntaje total para mostrar en la tabla del panel
    for p in partidas:
        p["puntaje_total"] = p["puntaje_quiz"] + p["puntaje_minijuego"]
    partidas.sort(key=lambda p: p["puntaje_total"], reverse=True)
    flash_msg = session.pop("admin_flash", None)
    return render_template("admin.html", jugadores=partidas, flash_msg=flash_msg)


@app.route("/admin/editar/<correo>", methods=["POST"])
@admin_requerido
def admin_editar(correo):
    partidas = leer_partidas()
    correo   = correo.lower()
    registro = next((p for p in partidas if p["correo"] == correo), None)

    if registro:
        nuevo_nombre    = request.form.get("nombre", "").strip()
        nuevo_minijuego = request.form.get("puntaje_minijuego", "").strip()

        if nuevo_nombre:
            registro["nombre"] = nuevo_nombre
        if nuevo_minijuego.isdigit():
            registro["puntaje_minijuego"] = int(nuevo_minijuego)

        escribir_partidas(partidas)
        session["admin_flash"] = f"Jugador '{registro['nombre']}' actualizado correctamente."
    else:
        session["admin_flash"] = "Jugador no encontrado."

    return redirect(url_for("admin_panel"))


@app.route("/admin/eliminar/<correo>", methods=["POST"])
@admin_requerido
def admin_eliminar(correo):
    partidas = leer_partidas()
    correo   = correo.lower()
    antes    = len(partidas)
    partidas = [p for p in partidas if p["correo"] != correo]

    if len(partidas) < antes:
        escribir_partidas(partidas)
        session["admin_flash"] = "Jugador eliminado del ranking."
    else:
        session["admin_flash"] = "Jugador no encontrado."

    return redirect(url_for("admin_panel"))


if __name__ == "__main__":
    app.run(debug=True)
