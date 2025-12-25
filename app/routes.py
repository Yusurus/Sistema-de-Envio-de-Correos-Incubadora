from flask import Blueprint, render_template, request, redirect, url_for, flash
from .models import db, Evento, Participacion, Notificacion, Participante
from .services import process_notifications, process_single_notification
from sqlalchemy import func, case

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return redirect(url_for('main.login'))

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == 'admin' and request.form.get('password') == 'admin':
            return redirect(url_for('main.dashboard'))
        else:
            flash('Credenciales incorrectas')
    return render_template('login.html')

@main.route('/dashboard')
def dashboard():
    # --- Métricas Generales ---
    total_eventos = Evento.query.count()
    total_participaciones = Participacion.query.count()
    
    # --- Datos por Evento (Lógica Optimizada) ---
    eventos_data = []
    all_eventos = Evento.query.all()
    
    for e in all_eventos:
        # 1. Total Participantes
        total = Participacion.query.filter_by(evento_id=e.id).count()
        
        # 2. Total Notificados Exitosamente (Join con Notificacion)
        notified = db.session.query(Participacion).join(Notificacion).filter(
            Participacion.evento_id == e.id,
            Notificacion.estado == 'Enviado'
        ).distinct().count() # distinct por si se envió 2 veces por error
        
        # 3. Total Entregados (Físicamente)
        entregados = Participacion.query.filter_by(
            evento_id=e.id, 
            estado='ENTREGADO'
        ).count()
        
        # 4. Pendientes de Notificar (La lógica compleja)
        # (Impreso + No Entregado + No Notificado)
        sent_subquery = db.session.query(Notificacion.participacion_id).filter(
            Notificacion.estado == 'Enviado'
        ).subquery()

        pendientes_notificar = Participacion.query.filter(
            Participacion.evento_id == e.id,
            # el estado puede estar impreso, generado o firmado
            Participacion.estado_certificado.in_(['Impreso', 'Generado', 'Firmado', 'Por Imprimir']),
            Participacion.estado != 'ENTREGADO', # Si ya se entregó, no cuenta como pendiente
            ~Participacion.id.in_(sent_subquery)
        ).count()

        eventos_data.append({
            'id': e.id,
            'nombre': e.nombre_evento,
            'fecha': e.fecha_evento,
            'total_participantes': total,
            'total_notificados': notified,
            'total_entregados': entregados,
            'pendientes_notificar': pendientes_notificar
        })

    return render_template('dashboard.html', 
                           metrics={'total_eventos': total_eventos, 'total_participaciones': total_participaciones},
                           eventos=eventos_data)

# --- NUEVA RUTA: Detalle del Evento y Lista de Participantes ---
@main.route('/evento/<int:event_id>')
def evento_detalle(event_id):
    evento = Evento.query.get_or_404(event_id)
    
    # Obtenemos participantes con datos de sus notificaciones
    # Hacemos un Outer Join porque puede que no tengan notificaciones aun
    
    # Esta consulta trae: Participacion, Participante, y el estado de la ultima notificacion si existe
    query = db.session.query(
        Participacion, 
        Participante,
        func.max(Notificacion.fecha_envio).label('ultima_notif'),
        func.max(Notificacion.estado).label('estado_notif') # Simplificacion
    ).join(Participante).outerjoin(Notificacion).filter(
        Participacion.evento_id == event_id
    ).group_by(Participacion.id, Participante.id).all()
    
    lista_participantes = []
    for p, part, ult_fecha, est_notif in query:
        lista_participantes.append({
            'participacion_id': p.id,
            'nombre': part.nombre_normalizado,
            'email': part.email,
            'estado_certificado': p.estado_certificado, # Impreso, Generado, etc
            'estado': p.estado,         # PENDIENTE / ENTREGADO
            'notificado': 'SI' if est_notif == 'Enviado' else 'NO'
        })
        
    return render_template('evento_detalle.html', evento=evento, participantes=lista_participantes)

# --- NUEVA RUTA: Cambiar estado de entrega ---
@main.route('/marcar_entregado/<int:participacion_id>')
def marcar_entregado(participacion_id):
    participacion = Participacion.query.get_or_404(participacion_id)
    
    # Toggle logic (opcional) o solo marcar entregado
    if participacion.estado == 'PENDIENTE':
        participacion.estado = 'ENTREGADO'
        flash(f'Certificado entregado a {participacion.participante.nombre_normalizado}. Ya no recibirá notificaciones.')
    else:
        participacion.estado = 'PENDIENTE'
        flash(f'Estado revertido a Pendiente para {participacion.participante.nombre_normalizado}.')
        
    db.session.commit()
    # Redirigir de vuelta al detalle del evento
    return redirect(url_for('main.evento_detalle', event_id=participacion.evento_id))

@main.route('/send_notifications/<int:event_id>', methods=['POST'])
def send_notifications_route(event_id):
    results = process_notifications(event_id)
    flash(f"Proceso completado. Enviados: {results['success']}, Fallidos: {results['failed']}. (Los ya entregados fueron ignorados)")
    return redirect(url_for('main.dashboard'))


@main.route('/resend_notifications/<int:event_id>', methods=['POST'])
def resend_notifications_route(event_id):
    # Reenvía correos incluso a quienes ya fueron notificados previamente
    results = process_notifications(event_id, force=True)
    flash(f"Reenvío completado. Enviados: {results['success']}, Fallidos: {results['failed']}. Se incluyeron notificados previos.")
    return redirect(url_for('main.evento_detalle', event_id=event_id))


@main.route('/resend_notification/participacion/<int:participacion_id>', methods=['POST'])
def resend_notification_participacion_route(participacion_id):
    # Determinar el evento para redirigir correctamente
    participacion = Participacion.query.get_or_404(participacion_id)
    result = process_single_notification(participacion_id, force=True)
    if result.get('success'):
        flash(f"Notificación reenviada a {participacion.participante.nombre_normalizado} ({participacion.participante.email}).")
    else:
        flash(f"No se pudo enviar a {participacion.participante.nombre_normalizado}: {result.get('error')}")
    return redirect(url_for('main.evento_detalle', event_id=participacion.evento_id))