"""
Avisa por email cuando un portal usado por una alerta activa lleva sin una corrida
`ok` más tiempo del esperado (ej. bloqueo anti-bot persistente).

La alerta se envía una sola vez por episodio: mientras el portal sigue
desactualizado no se repite, y al recuperarse se avisa que volvió a andar.
Estado en silver.health_alerts (ver sql/003_health_alerts.sql). Un aviso solo se
da por enviado si Apprise lo aceptó; si no, se reintenta en el próximo ciclo y el
paso termina con error para que la falla se vea.

Si este script no puede ni conectarse a la base (ej. corte de DNS, o la base
llena y rechazando conexiones), la lógica de arriba no corre — pero igual hay
que avisar, porque check_health es el único paso pensado para eso. Ese caso
usa un marcador en disco (no en la base, que es justo lo que no anda) para no
repetir el aviso cada 10 minutos mientras el corte persiste.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

from app.alerts import build_notifier, send
from app.searches import SALE_ONLY_PORTALS, Config, Operation, SearchConfigError, load_config

DATABASE_URL = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    try:
        from app.config import NEON_DATABASE_URL as DATABASE_URL
    except ImportError:
        sys.exit("No se encontró DATABASE_URL ni app.config.NEON_DATABASE_URL")

# Minutos sin una corrida ok a partir de los cuales se avisa, por fuente.
THRESHOLDS_MIN = {
    "zonaprop": 90,
    "argenprop": 90,
    "mashogares": 90,
    "mercadolibre": 150,
}

# Marcador en disco (no en la base) para el caso "ni siquiera pude conectarme".
DB_UNREACHABLE_MARKER = Path(__file__).parent / ".check_health_db_unreachable"


def _send(config: Config, title: str, body: str) -> bool:
    # El notificador se arma en cada envío y no al arrancar: una configuración de
    # Apprise rota no debe impedir ni tapar el aviso de que la base no responde.
    try:
        notifier = build_notifier(config.apprise.services)
    except SearchConfigError as exc:
        print(f"  no se pudo armar el envío por email: {exc}")
        return False
    return send(notifier, title, body)


def _alert_db_unreachable(config: Config, exc: Exception) -> None:
    was_alerted = DB_UNREACHABLE_MARKER.exists()
    print(f"No se pudo completar el chequeo de salud: {exc}")
    if was_alerted:
        print("  (ya se había avisado este corte, no se repite)")
        return
    sent = _send(
        config,
        "No se pudo chequear la salud",
        f"No se pudo conectar o consultar la base de datos:\n\n`{exc}`\n\n"
        "No hay forma de saber el estado real de los portales hasta que esto se resuelva.",
    )
    if sent:
        DB_UNREACHABLE_MARKER.touch()
    else:
        print("  tampoco se pudo avisar por email")


def _alert_recovered(config: Config) -> None:
    if not DB_UNREACHABLE_MARKER.exists():
        return
    sent = _send(
        config,
        "La base volvió a responder",
        "El chequeo de salud pudo volver a conectarse a la base de datos.",
    )
    if sent:
        DB_UNREACHABLE_MARKER.unlink(missing_ok=True)
    else:
        print("  no se pudo avisar la recuperación por email")


def get_last_ok(cur: psycopg2.extensions.cursor, fuente: str) -> dict | None:
    cur.execute(
        """
        SELECT finalizado_en, now() - finalizado_en AS antiguedad
        FROM raw.pipeline_runs
        WHERE fuente = %s AND estado = 'ok'
        ORDER BY finalizado_en DESC
        LIMIT 1
        """,
        (fuente,),
    )
    return cur.fetchone()


def already_alerted(cur: psycopg2.extensions.cursor, fuente: str) -> bool:
    cur.execute("SELECT 1 FROM silver.health_alerts WHERE fuente = %s", (fuente,))
    return cur.fetchone() is not None


def mark_alerted(cur: psycopg2.extensions.cursor, fuente: str) -> None:
    cur.execute(
        "INSERT INTO silver.health_alerts (fuente) VALUES (%s) ON CONFLICT DO NOTHING",
        (fuente,),
    )


def clear_alert(cur: psycopg2.extensions.cursor, fuente: str) -> None:
    cur.execute("DELETE FROM silver.health_alerts WHERE fuente = %s", (fuente,))


def _watched_portals(config: Config) -> list[str]:
    # Un portal apagado en alerts.yaml no tiene por qué tener corridas, ni uno solo
    # de venta cuando todas las alertas activas son de alquiler.
    sale_alerts = any(search.active and search.operation == Operation.SALE for search in config.searches)
    return [
        portal
        for portal in THRESHOLDS_MIN
        if portal in config.portals and (sale_alerts or portal not in SALE_ONLY_PORTALS)
    ]


def _check(config: Config) -> int:
    """Chequea cada portal vigilado. Devuelve cuántos avisos no se pudieron enviar."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    failed_sends = 0

    _alert_recovered(config)
    print("Chequeando salud de fuentes...")

    for fuente in _watched_portals(config):
        threshold_min = THRESHOLDS_MIN[fuente]
        last_ok = get_last_ok(cur, fuente)
        age_min = last_ok["antiguedad"].total_seconds() / 60 if last_ok else None
        is_stale = age_min is None or age_min > threshold_min

        if is_stale and not already_alerted(cur, fuente):
            detail = "nunca tuvo una corrida exitosa" if last_ok is None else f"hace {int(age_min)} min"
            sent = _send(
                config,
                f"{fuente} sin datos nuevos",
                f"**{fuente}** lleva sin una corrida exitosa ({detail}; umbral: {threshold_min} min).\n\n"
                "No vas a recibir alertas de este portal hasta que se recupere.",
            )
            if sent:
                mark_alerted(cur, fuente)
                conn.commit()
                print(f"  {fuente}: ALERTA enviada ({detail})")
            else:
                failed_sends += 1
                print(f"  {fuente}: desactualizado ({detail}), no se pudo avisar; se reintenta en el próximo ciclo")
        elif not is_stale and already_alerted(cur, fuente):
            sent = _send(
                config,
                f"{fuente} volvió a funcionar",
                f"**{fuente}** volvió a tener corridas exitosas.",
            )
            if sent:
                clear_alert(cur, fuente)
                conn.commit()
                print(f"  {fuente}: recuperado")
            else:
                failed_sends += 1
                print(f"  {fuente}: recuperado, no se pudo avisar; se reintenta en el próximo ciclo")
        else:
            print(f"  {fuente}: ok" if not is_stale else f"{fuente}: sigue desactualizado, ya alertado")

    cur.close()
    conn.close()
    return failed_sends


def main() -> None:
    try:
        config = load_config()
    except SearchConfigError as exc:
        sys.exit(f"Configuración de alertas inválida: {exc}")
    if not config.health.enabled:
        print("Los avisos de salud están desactivados en alerts.yaml (health.enabled).")
        return

    try:
        failed_sends = _check(config)
    except Exception as exc:
        _alert_db_unreachable(config, exc)
        raise  # que quede como Failed en Prefect tambien, no solo por email
    if failed_sends:
        sys.exit(1)


if __name__ == "__main__":
    main()
