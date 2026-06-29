# ── RUTA NUEVA: Tablero de clasificación ──────────────────────────────────────
# Agrega esto en app.py, justo antes del bloque `if __name__ == "__main__":`

@app.route("/leaderboard")
@login_requerido
def leaderboard():
    jugador = session.get("jugador", {})

    # leer todas las partidas del csv
    partidas = []
    try:
        with open(ARCHIVO_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                partidas.append(row)
    except FileNotFoundError:
        pass

    # ordenar: convertir "X/Y" a número entero de aciertos para comparar
    def puntaje_numerico(p):
        try:
            return int(p["puntaje"].split("/")[0])
        except Exception:
            return 0

    partidas.sort(key=puntaje_numerico, reverse=True)

    # calcular el récord absoluto
    mejor = puntaje_numerico(partidas[0]) if partidas else 0

    return render_template(
        "leaderboard.html",
        jugadores=partidas,
        jugador_actual=jugador,
        mejor_puntaje=f"{mejor}/{partidas[0]['puntaje'].split('/')[1]}" if partidas else "—",
    )
