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

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_CSV  = os.path.join(BASE_DIR, "jugadores.csv")
USUARIOS_CSV = os.path.join(BASE_DIR, "usuarios.csv")

CAMPOS_CSV  = ["nombre", "genero", "correo", "puntaje_quiz", "puntaje_minijuego", "fecha"]
CAMPOS_USER = ["nombre", "correo", "password", "genero", "fecha_registro"]
GENEROS     = ["Mujer", "Hombre", "No-binario", "Otro"]

with open(os.path.join(BASE_DIR, "preguntas.json"), encoding="utf-8") as f:
    preguntas_completas = json.load(f)

PUNTOS_POR_PREGUNTA = 250   # puntos que vale cada respuesta correcta del quiz


# -- VALIDACIONES --

def nombre_valido(nombre):
    if not nombre.strip():
        return "Por favor, escribe tu nombre."
    if not re.fullmatch(r"[A-Za-záéíóúÁÉÍÓÚüÜñÑ ]+", nombre.strip()):
        return "El nombre solo puede tener letras y espacios."
    return ""

def correo_valido(correo):
    if not correo.strip():
        return "Por favor, escribe tu correo."
    if not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo.strip()):
        return "El correo debe tener el formato: nombre@dominio.com"
    return ""

def password_valida(pw):
    if not pw or len(pw) < 6:
        return "La contraseña debe tener al menos 6 caracteres."
    return ""


# -- MANEJO DE USUARIOS --

def leer_usuarios():
    usuarios = []
    try:
        with open(USUARIOS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                usuarios.append(row)
    except FileNotFoundError:
        pass
    return usuarios

def guardar_usuario(nombre, correo, password, genero):
    escribir_cabecera = False
    try:
        with open(USUARIOS_CSV, "r", encoding="utf-8") as f:
            if not f.read(1):
                escribir_cabecera = True
    except FileNotFoundError:
        escribir_cabecera = True

    with open(USUARIOS_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_USER)
        if escribir_cabecera:
            writer.writeheader()
        writer.writerow({
            "nombre":         nombre,
            "correo":         correo.lower(),
            "password":       password,
            "genero":         genero,
            "fecha_registro": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

def buscar_usuario(correo):
    for u in leer_usuarios():
        if u["correo"] == correo.lower():
            return u
    return None

def correo_registrado(correo):
    return buscar_usuario(correo) is not None


# -- GUARDAR PARTIDAS --
# Hay un registro por jugador (correo). Solo se actualiza el puntaje de la fuente
# correspondiente si el nuevo puntaje es mayor al que ya tenía.

def leer_partidas():
    partidas = []
    try:
        with open(ARCHIVO_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
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
    with open(ARCHIVO_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
        writer.writeheader()
        writer.writerows(partidas)

def guardar_partida(nombre, genero, correo, puntos, fuente="quiz"):
    partidas = leer_partidas()
    correo   = correo.lower()

    # buscar si ya existe un registro para este jugador
    registro = next((p for p in partidas if p["correo"] == correo), None)

    if registro is None:
        # primera vez: crear fila nueva
        registro = {
            "nombre":           nombre,
            "genero":           genero,
            "correo":           correo,
            "puntaje_quiz":     0,
            "puntaje_minijuego":0,
            "fecha":            datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        partidas.append(registro)

    # solo reemplazar si el nuevo puntaje es estrictamente mayor
    campo = "puntaje_quiz" if fuente == "quiz" else "puntaje_minijuego"
    if int(puntos) > int(registro[campo]):
        registro[campo] = int(puntos)
        registro["fecha"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    escribir_partidas(partidas)


# -- DECORADOR DE LOGIN --

def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_logueado"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# -- AUTENTICACIÓN --

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        correo   = request.form.get("correo", "").strip()
        password = request.form.get("password", "").strip()
        usuario  = buscar_usuario(correo)

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

        errores["nombre"]   = nombre_valido(nombre)
        errores["correo"]   = correo_valido(correo)
        errores["password"] = password_valida(password)
        if not genero:
            errores["genero"] = "Por favor, elige tu género."

        if correo and not errores["correo"] and correo_registrado(correo):
            errores["correo"] = "Este correo ya está registrado."

        datos = {"nombre": nombre, "correo": correo}

        if not any(errores.values()):
            guardar_usuario(nombre, correo, password, genero)
            session["usuario_logueado"] = True
            session["jugador"] = {"nombre": nombre, "genero": genero, "correo": correo}
            return redirect(url_for("registro"))

    return render_template("register.html", errores=errores, datos=datos, generos=GENEROS)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -- RUTAS DEL JUEGO --

@app.route("/", methods=["GET", "POST"])
@login_requerido
def registro():
    jugador     = session.get("jugador", {})
    error_extra = ""

    if request.method == "POST":
        preguntas = random.sample(preguntas_completas, min(10, len(preguntas_completas)))
        for p in preguntas:
            opciones = p["opciones"][:]
            random.shuffle(opciones)
            p["opciones_mezcladas"] = opciones
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
                # sumar 250 puntos por cada respuesta correcta
                session["puntaje"] = session.get("puntaje", 0) + PUNTOS_POR_PREGUNTA
            session["indice"] = indice + 1
            return redirect(url_for("juego"))

    pregunta_actual = preguntas[indice]
    return render_template("juego.html",
                           pregunta=pregunta_actual,
                           numero=indice + 1,
                           total=len(preguntas),
                           error=error)


@app.route("/resultado")
@login_requerido
def resultado():
    jugador = session.get("jugador", {})
    puntos  = session.get("puntaje", 0)
    total   = len(session.get("preguntas", []))

    # calcular cuántas preguntas acertó para mostrar en la UI
    aciertos = puntos // PUNTOS_POR_PREGUNTA

    if jugador:
        guardar_partida(jugador["nombre"], jugador["genero"],
                        jugador["correo"], puntos, fuente="quiz")

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
    jugador = session.get("jugador", {})
    puntos  = request.form.get("puntos", 0, type=int)
    if jugador:
        guardar_partida(jugador["nombre"], jugador["genero"],
                        jugador["correo"], puntos, fuente="minijuego")
    return ("", 204)


@app.route("/leaderboard")
@login_requerido
def leaderboard():
    jugador = session.get("jugador", {})

    partidas = leer_partidas()

    # calcular total combinado y ordenar de mayor a menor
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


# -- PANEL DE ADMINISTRADOR --
# Credenciales del admin (independientes de usuarios.csv)
ADMIN_USER = "admin"
ADMIN_PASS = "2014"

def admin_requerido(f):
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
    # calcular total para mostrar en la tabla
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
