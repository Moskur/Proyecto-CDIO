from flask import Flask, render_template, request, redirect, url_for, session
import random
import csv
import re
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "clave_secreta_quiz"

ARCHIVO_CSV = "jugadores.csv"
CAMPOS_CSV  = ["nombre", "genero", "correo", "puntaje", "fecha"]
GENEROS     = ["Mujer", "Hombre", "No-binario", "Otro"]

# Cargar preguntas desde el archivo JSON
with open("preguntas.json", encoding="utf-8") as f:
    preguntas_completas = json.load(f)


# VALIDACIONES


def nombre_valido(nombre):
    if not nombre.strip():
        return "Por favor, escribe tu nombre."
    if not re.fullmatch(r"[A-Za-záéíóúÁÉÍÓÚüÜñÑ ]+", nombre.strip()):
        return "El nombre solo puede tener letras y espacios, sin números ni símbolos."
    return ""

def correo_valido(correo):
    if not correo.strip():
        return "Por favor, escribe tu correo."
    if not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", correo.strip()):
        return "El correo debe tener el formato: nombre@dominio.com"
    return ""


# GUARDAR EN CSV


def guardar_jugador(nombre, genero, correo, puntaje, total):
    escribir_cabecera = False
    try:
        with open(ARCHIVO_CSV, "r", encoding="utf-8") as f:
            if not f.read(1):
                escribir_cabecera = True
    except FileNotFoundError:
        escribir_cabecera = True

    with open(ARCHIVO_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_CSV)
        if escribir_cabecera:
            writer.writeheader()
        writer.writerow({
            "nombre":  nombre,
            "genero":  genero,
            "correo":  correo,
            "puntaje": f"{puntaje}/{total}",
            "fecha":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        })


# RUTAS


@app.route("/", methods=["GET", "POST"])
def registro():
    error_nombre = ""
    error_correo = ""
    datos = {}

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        genero = request.form.get("genero", "").strip()
        correo = request.form.get("correo", "").strip()

        error_nombre = nombre_valido(nombre)
        error_correo = correo_valido(correo)

        if not genero:
            datos = {"nombre": nombre, "correo": correo}
            return render_template("registro.html", generos=GENEROS,
                                    error_genero="Por favor, elige tu género.",
                                    datos=datos)

        if not error_nombre and not error_correo:
            session["jugador"] = {"nombre": nombre, "genero": genero, "correo": correo}

            preguntas = random.sample(preguntas_completas, min(10, len(preguntas_completas)))
            for p in preguntas:
                opciones = p["opciones"][:]
                random.shuffle(opciones)
                p["opciones_mezcladas"] = opciones
            session["preguntas"] = preguntas
            session["indice"]    = 0
            session["puntaje"]   = 0

            return redirect(url_for("juego"))

        datos = {"nombre": nombre, "correo": correo}

    return render_template("registro.html", generos=GENEROS,
                            error_nombre=error_nombre,
                            error_correo=error_correo,
                            datos=datos)


@app.route("/juego", methods=["GET", "POST"])
def juego():
    preguntas = session.get("preguntas", [])
    indice    = session.get("indice", 0)

    if not preguntas or indice >= len(preguntas):
        return redirect(url_for("resultado"))

    error = ""

    if request.method == "POST":
        respuesta = request.form.get("respuesta", "")
        pregunta_actual = preguntas[indice]

        if not respuesta:
            error = "Elige una opción antes de continuar."
        else:
            if respuesta == pregunta_actual["correcta"]:
                session["puntaje"] = session.get("puntaje", 0) + 1
            session["indice"] = indice + 1
            return redirect(url_for("juego"))

    pregunta_actual = preguntas[indice]
    total = len(preguntas)

    return render_template("juego.html",
                            pregunta=pregunta_actual,
                            numero=indice + 1,
                            total=total,
                            error=error)


@app.route("/resultado")
def resultado():
    jugador  = session.get("jugador", {})
    puntaje  = session.get("puntaje", 0)
    total    = len(session.get("preguntas", []))

    if jugador:
        guardar_jugador(jugador["nombre"], jugador["genero"],
                        jugador["correo"], puntaje, total)

    session.clear()
    return render_template("resultado.html", jugador=jugador,
                            puntaje=puntaje, total=total)


if __name__ == "__main__":
    app.run(debug=True)