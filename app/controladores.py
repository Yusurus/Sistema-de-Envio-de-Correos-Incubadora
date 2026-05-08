from functools import wraps
import unicodedata

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from . import db
from .models import Evento, Notificacion, Participacion, Participante


controladores = Blueprint("controladores", __name__, url_prefix="/admin")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Debes iniciar sesión primero")
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)

    return wrapper


def _clean_text(value):
    return (value or "").strip()


def _participant_lookup_key(value):
    normalized = unicodedata.normalize("NFKD", _clean_text(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.lower().split())


def _delete_event_dependencies(evento_id):
    participaciones = Participacion.query.filter_by(evento_id=evento_id).all()
    for participacion in participaciones:
        Notificacion.query.filter_by(participacion_id=participacion.id).delete(synchronize_session=False)
        db.session.delete(participacion)


def _delete_participant_dependencies(participante_id):
    participaciones = Participacion.query.filter_by(participante_id=participante_id).all()
    for participacion in participaciones:
        Notificacion.query.filter_by(participacion_id=participacion.id).delete(synchronize_session=False)
        db.session.delete(participacion)


def _get_or_create_participante(nombre_completo, email, telefono):
    participante = None

    if email:
        participante = Participante.query.filter(db.func.lower(Participante.email) == email.lower()).first()

    if not participante and nombre_completo:
        participante = Participante.query.filter(
            db.func.lower(Participante.nombre_completo) == _participant_lookup_key(nombre_completo)
        ).first()

    if participante:
        participante.nombre_completo = nombre_completo or participante.nombre_completo
        participante.email = email or participante.email
        participante.telefono = telefono or participante.telefono
        return participante, False

    participante = Participante(
        nombre_completo=nombre_completo,
        email=email,
        telefono=telefono,
    )
    db.session.add(participante)
    return participante, True


@controladores.route("/")
@login_required
def index():
    return redirect(url_for("controladores.listar_eventos"))


@controladores.route("/eventos")
@login_required
def listar_eventos():
    eventos = Evento.query.order_by(Evento.id.desc()).all()
    return render_template("controladores/eventos_list.html", eventos=eventos)


@controladores.route("/eventos/nuevo", methods=["GET", "POST"])
@login_required
def crear_evento():
    if request.method == "POST":
        nombre_evento = _clean_text(request.form.get("nombre_evento"))
        fecha_evento = _clean_text(request.form.get("fecha_evento"))
        resolucion = _clean_text(request.form.get("resolucion"))

        if not nombre_evento:
            flash("El nombre del evento es obligatorio")
            return render_template("controladores/evento_form.html", evento=None)

        if Evento.query.filter_by(nombre_evento=nombre_evento).first():
            flash("Ya existe un evento con ese nombre")
            return render_template("controladores/evento_form.html", evento=None)

        evento = Evento(
            nombre_evento=nombre_evento,
            fecha_evento=fecha_evento,
            resolucion=resolucion,
        )
        db.session.add(evento)
        db.session.commit()
        flash("Evento creado correctamente")
        return redirect(url_for("controladores.listar_eventos"))

    return render_template("controladores/evento_form.html", evento=None)


@controladores.route("/eventos/<int:evento_id>/editar", methods=["GET", "POST"])
@login_required
def editar_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == "POST":
        nombre_evento = _clean_text(request.form.get("nombre_evento"))
        fecha_evento = _clean_text(request.form.get("fecha_evento"))
        resolucion = _clean_text(request.form.get("resolucion"))

        if not nombre_evento:
            flash("El nombre del evento es obligatorio")
            return render_template("controladores/evento_form.html", evento=evento)

        evento_existente = Evento.query.filter_by(nombre_evento=nombre_evento).first()
        if evento_existente and evento_existente.id != evento.id:
            flash("Ya existe otro evento con ese nombre")
            return render_template("controladores/evento_form.html", evento=evento)

        evento.nombre_evento = nombre_evento
        evento.fecha_evento = fecha_evento
        evento.resolucion = resolucion
        db.session.commit()
        flash("Evento actualizado correctamente")
        return redirect(url_for("controladores.listar_eventos"))

    return render_template("controladores/evento_form.html", evento=evento)


@controladores.route("/eventos/<int:evento_id>/eliminar", methods=["POST"])
@login_required
def eliminar_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    try:
        _delete_event_dependencies(evento.id)
        db.session.delete(evento)
        db.session.commit()
        flash("Evento eliminado correctamente")
    except Exception as exc:
        db.session.rollback()
        flash(f"No se pudo eliminar el evento: {exc}")

    return redirect(url_for("controladores.listar_eventos"))


@controladores.route("/eventos/<int:evento_id>/participantes", methods=["GET", "POST"])
@login_required
def gestionar_participantes_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)

    if request.method == "POST":
        action = request.form.get("action", "asignar")

        try:
            if action == "crear_y_asignar":
                nombre_completo = _clean_text(request.form.get("nombre_completo"))
                email = _clean_text(request.form.get("email"))
                telefono = _clean_text(request.form.get("telefono"))
                rol = _clean_text(request.form.get("rol"))
                horas_academicas = _clean_text(request.form.get("horas_academicas"))

                if not nombre_completo:
                    flash("El nombre completo es obligatorio")
                else:
                    participante, creado = _get_or_create_participante(
                        nombre_completo,
                        email,
                        telefono,
                    )
                    db.session.flush()

                    participacion = Participacion.query.filter_by(
                        participante_id=participante.id,
                        evento_id=evento.id,
                    ).first()

                    if participacion:
                        db.session.commit()
                        flash("Ese participante ya está asociado a este evento")
                    else:
                        participacion = Participacion(
                            participante_id=participante.id,
                            evento_id=evento.id,
                            rol=rol,
                            horas_academicas=horas_academicas,
                            estado_certificado="Generado",
                            estado="PENDIENTE",
                        )
                        db.session.add(participacion)
                        db.session.commit()
                        flash(
                            f"Participante {'creado y ' if creado else ''}asignado correctamente al evento"
                        )

                return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento.id))

            selected_ids = request.form.getlist("participante_ids")
            rol = _clean_text(request.form.get("rol"))
            horas_academicas = _clean_text(request.form.get("horas_academicas"))

            if not selected_ids:
                flash("Selecciona al menos un participante")
                return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento.id))

            participant_ids = [int(participant_id) for participant_id in selected_ids]
            participantes = Participante.query.filter(Participante.id.in_(participant_ids)).all()

            existing_ids = {
                participacion.participante_id
                for participacion in Participacion.query.filter_by(evento_id=evento.id).all()
            }

            created_count = 0
            skipped_count = 0
            for participante in participantes:
                if participante.id in existing_ids:
                    skipped_count += 1
                    continue

                db.session.add(
                    Participacion(
                        participante_id=participante.id,
                        evento_id=evento.id,
                        rol=rol,
                        horas_academicas=horas_academicas,
                        estado_certificado="Generado",
                        estado="PENDIENTE",
                    )
                )
                created_count += 1

            db.session.commit()

            if created_count:
                flash(f"Se asignaron {created_count} participante(s) al evento")
            if skipped_count:
                flash(f"Se omitieron {skipped_count} participante(s) ya asociados")

            return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento.id))

        except Exception as exc:
            db.session.rollback()
            flash(f"No se pudieron guardar las asignaciones: {exc}")
            return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento.id))

    participantes_asignados = (
        db.session.query(Participacion, Participante)
        .join(Participante)
        .filter(Participacion.evento_id == evento.id)
        .order_by(Participante.nombre_completo.asc(), Participante.email.asc())
        .all()
    )

    assigned_ids = [participante.id for _, participante in participantes_asignados]
    participantes_disponibles = Participante.query.order_by(Participante.nombre_completo.asc(), Participante.email.asc()).all()

    return render_template(
        "controladores/evento_participantes.html",
        evento=evento,
        participantes_asignados=participantes_asignados,
        participantes_disponibles=participantes_disponibles,
        assigned_ids=assigned_ids,
    )


@controladores.route("/eventos/<int:evento_id>/participaciones/<int:participacion_id>/eliminar", methods=["POST"])
@login_required
def eliminar_participacion_evento(evento_id, participacion_id):
    participacion = Participacion.query.get_or_404(participacion_id)

    if participacion.evento_id != evento_id:
        flash("La participación no pertenece a este evento")
        return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento_id))

    try:
        Notificacion.query.filter_by(participacion_id=participacion.id).delete(synchronize_session=False)
        db.session.delete(participacion)
        db.session.commit()
        flash("Participante desasociado del evento")
    except Exception as exc:
        db.session.rollback()
        flash(f"No se pudo eliminar la asociación: {exc}")

    return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento_id))


@controladores.route("/eventos/<int:evento_id>/participaciones/<int:participacion_id>/editar", methods=["GET", "POST"])
@login_required
def editar_participacion_evento(evento_id, participacion_id):
    participacion = Participacion.query.get_or_404(participacion_id)
    evento = Evento.query.get_or_404(evento_id)

    if participacion.evento_id != evento_id:
        flash("La participación no pertenece a este evento")
        return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento_id))

    if request.method == "POST":
        try:
            participacion.rol = _clean_text(request.form.get("rol"))
            participacion.horas_academicas = _clean_text(request.form.get("horas_academicas"))
            participacion.certificado_url = _clean_text(request.form.get("certificado_url"))
            participacion.qr_token = _clean_text(request.form.get("qr_token"))
            participacion.estado_certificado = _clean_text(request.form.get("estado_certificado")) or "Generado"
            participacion.estado = _clean_text(request.form.get("estado")) or "PENDIENTE"

            db.session.commit()
            flash("Participación actualizada correctamente")
            return redirect(url_for("controladores.gestionar_participantes_evento", evento_id=evento_id))
        except Exception as exc:
            db.session.rollback()
            flash(f"No se pudo actualizar la participación: {exc}")

    return render_template(
        "controladores/participacion_edit.html",
        evento=evento,
        participacion=participacion,
    )


@controladores.route("/participantes")
@login_required
def listar_participantes():
    participantes = Participante.query.order_by(Participante.id.desc()).all()
    return render_template("controladores/participantes_list.html", participantes=participantes)


@controladores.route("/participantes/nuevo", methods=["GET", "POST"])
@login_required
def crear_participante():
    if request.method == "POST":
        nombre_completo = _clean_text(request.form.get("nombre_completo"))
        email = _clean_text(request.form.get("email"))
        telefono = _clean_text(request.form.get("telefono"))

        if not nombre_completo:
            flash("El nombre completo es obligatorio")
            return render_template("controladores/participante_form.html", participante=None)

        participante = Participante(
            nombre_completo=nombre_completo,
            email=email,
            telefono=telefono,
        )
        db.session.add(participante)
        db.session.commit()
        flash("Participante creado correctamente")
        return redirect(url_for("controladores.listar_participantes"))

    return render_template("controladores/participante_form.html", participante=None)


@controladores.route("/participantes/<int:participante_id>/editar", methods=["GET", "POST"])
@login_required
def editar_participante(participante_id):
    participante = Participante.query.get_or_404(participante_id)

    if request.method == "POST":
        nombre_completo = _clean_text(request.form.get("nombre_completo"))
        email = _clean_text(request.form.get("email"))
        telefono = _clean_text(request.form.get("telefono"))

        if not nombre_completo:
            flash("El nombre completo es obligatorio")
            return render_template("controladores/participante_form.html", participante=participante)

        participante.nombre_completo = nombre_completo
        participante.email = email
        participante.telefono = telefono
        db.session.commit()
        flash("Participante actualizado correctamente")
        return redirect(url_for("controladores.listar_participantes"))

    return render_template("controladores/participante_form.html", participante=participante)


@controladores.route("/participantes/<int:participante_id>/eliminar", methods=["POST"])
@login_required
def eliminar_participante(participante_id):
    participante = Participante.query.get_or_404(participante_id)

    try:
        _delete_participant_dependencies(participante.id)
        db.session.delete(participante)
        db.session.commit()
        flash("Participante eliminado correctamente")
    except Exception as exc:
        db.session.rollback()
        flash(f"No se pudo eliminar el participante: {exc}")

    return redirect(url_for("controladores.listar_participantes"))
