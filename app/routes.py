from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from .models import db, Evento, Participacion, Notificacion, Participante
from .services import process_notifications, process_single_notification
from sqlalchemy import func, case
import os
import re
import pymysql

main = Blueprint('main', __name__)

@main.route('/')
def index():
    if session.get('logged_in'):
        return redirect(url_for('controladores.listar_eventos'))
    return redirect(url_for('main.login'))

@main.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('controladores.listar_eventos'))

    if request.method == 'POST':
        if request.form.get('username') == 'admin' and request.form.get('password') == 'admin':
            session['logged_in'] = True
            session['username'] = 'admin'
            return redirect(url_for('controladores.listar_eventos'))
        else:
            flash('Credenciales incorrectas')
    return render_template('login.html')

@main.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente')
    return redirect(url_for('main.login'))

@main.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
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

# ---Detalle del Evento y Lista de Participantes ---
@main.route('/evento/<int:event_id>')
def evento_detalle(event_id):
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
    evento = Evento.query.get_or_404(event_id)
    
    # Obtenemos participantes con datos de sus notificaciones
    # Hacemos un Outer Join porque puede que no tengan notificaciones aun
    
    # Esta consulta trae: Participacion, Participante, y el conteo de notificaciones
    query = db.session.query(
        Participacion, 
        Participante,
        func.count(Notificacion.id).label('count_notificaciones')
    ).join(Participante).outerjoin(Notificacion).filter(
        Participacion.evento_id == event_id
    ).group_by(Participacion.id, Participante.id).all()
    
    lista_participantes = []
    for p, part, count_notif in query:
        lista_participantes.append({
            'participacion_id': p.id,
            'nombre': part.nombre_completo or part.email,
            'email': part.email,
            'estado_certificado': p.estado_certificado, # Impreso, Generado, etc
            'estado': p.estado,         # PENDIENTE / ENTREGADO
            'num_notificaciones': count_notif
        })
        
    return render_template('evento_detalle.html', evento=evento, participantes=lista_participantes)

# ---Cambiar estado de entrega ---
@main.route('/marcar_entregado/<int:participacion_id>')
def marcar_entregado(participacion_id):
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
    participacion = Participacion.query.get_or_404(participacion_id)
    
    # Toggle logic (opcional) o solo marcar entregado
    if participacion.estado == 'PENDIENTE':
        participacion.estado = 'ENTREGADO'
        flash(f"Certificado entregado a {participacion.participante.nombre_completo or participacion.participante.email}. Ya no recibirá notificaciones.")
    else:
        participacion.estado = 'PENDIENTE'
        flash(f"Estado revertido a Pendiente para {participacion.participante.nombre_completo or participacion.participante.email}.")
        
    db.session.commit()
    # Redirigir de vuelta al detalle del evento
    return redirect(url_for('main.evento_detalle', event_id=participacion.evento_id))

@main.route('/send_notifications/<int:event_id>', methods=['POST'])
def send_notifications_route(event_id):
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
    results = process_notifications(event_id)
    flash(f"Proceso completado. Enviados: {results['success']}, Fallidos: {results['failed']}. (Los ya entregados fueron ignorados)")
    return redirect(url_for('main.dashboard'))


@main.route('/resend_notifications/<int:event_id>', methods=['POST'])
def resend_notifications_route(event_id):
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
    # Reenvía correos incluso a quienes ya fueron notificados previamente
    results = process_notifications(event_id, force=True)
    flash(f"Reenvío completado. Enviados: {results['success']}, Fallidos: {results['failed']}. Se incluyeron notificados previos.")
    return redirect(url_for('main.evento_detalle', event_id=event_id))


@main.route('/resend_notification/participacion/<int:participacion_id>', methods=['POST'])
def resend_notification_participacion_route(participacion_id):
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
    # Determinar el evento para redirigir correctamente
    participacion = Participacion.query.get_or_404(participacion_id)
    result = process_single_notification(participacion_id, force=True)
    if result.get('success'):
        flash(f"Notificación reenviada a {participacion.participante.nombre_completo or participacion.participante.email} ({participacion.participante.email}).")
    else:
        flash(f"No se pudo enviar a {participacion.participante.nombre_completo or participacion.participante.email}: {result.get('error')}")
    return redirect(url_for('main.evento_detalle', event_id=participacion.evento_id))


@main.route('/configuracion', methods=['GET'])
def configuracion():
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
    # Conexión directa a la BD para obtener los valores actuales
    try:
        connection = pymysql.connect(
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME'],
            port=int(current_app.config['DB_PORT']),
            cursorclass=pymysql.cursors.DictCursor
        )
        with connection.cursor() as cursor:
            # Usamos el nombre de tabla y columna que pusiste en tu Config
            cursor.execute("SELECT * FROM configuraciones WHERE idconfiguracion = 1")
            db_config = cursor.fetchone()
            
            if db_config:
                gmail_user = db_config.get('gmail_user', '')
                gmail_password = db_config.get('gmail_app_password', '')
                email_remitente = db_config.get('email_remitente_real', '')
                direccion_recojo = db_config.get('direccion_recojo', '')
            else:
                # Si no hay nada en la BD, mostramos vacío
                gmail_user = gmail_password = email_remitente = direccion_recojo = ""
        connection.close()
    except Exception as e:
        flash(f"Error al cargar configuración desde la base de datos: {e}")
        gmail_user = gmail_password = email_remitente = direccion_recojo = ""

    return render_template('configuracion.html', 
                         gmail_user=gmail_user,
                         gmail_password=gmail_password,
                         email_remitente=email_remitente,
                         direccion_recojo=direccion_recojo)


@main.route('/configuracion/actualizar', methods=['POST'])
def actualizar_configuracion():
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    
    # Captura de datos del formulario
    gmail_user = request.form.get('gmail_user', '').strip()
    gmail_password = request.form.get('gmail_password', '').strip()
    email_remitente = request.form.get('email_remitente', '').strip()
    direccion_recojo = request.form.get('direccion_recojo', '').strip()
    
    if not gmail_user or not gmail_password:
        flash('El usuario y contraseña de Gmail son obligatorios')
        return redirect(url_for('main.configuracion'))

    # Conexión directa a la BD usando los parámetros de Config
    try:
        connection = pymysql.connect(
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME'],
            port=int(current_app.config['DB_PORT'])
        )
        
        with connection.cursor() as cursor:
            # SQL para actualizar la fila 1. 
            # Usamos INSERT ... ON DUPLICATE KEY UPDATE por si el ID 1 no existe aún.
            sql = """
                INSERT INTO configuraciones (idconfiguracion, gmail_user, gmail_app_password, email_remitente_real, direccion_recojo)
                VALUES (1, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    gmail_user=%s, 
                    gmail_app_password=%s, 
                    email_remitente_real=%s, 
                    direccion_recojo=%s
            """
            valores = (
                gmail_user, gmail_password, email_remitente, direccion_recojo, # Para el INSERT
                gmail_user, gmail_password, email_remitente, direccion_recojo  # Para el UPDATE
            )
            
            cursor.execute(sql, valores)
            connection.commit()

        # Actualizar la configuración en memoria para que el cambio sea inmediato
        current_app.config['MAIL_USERNAME'] = gmail_user
        current_app.config['MAIL_PASSWORD'] = gmail_password
        current_app.config['MAIL_DEFAULT_SENDER'] = email_remitente
        current_app.config['DIRECCION_RECOJO'] = direccion_recojo
        
        flash('Configuración actualizada en la base de datos.')
        
    except Exception as e:
        flash(f'Error de conexión o SQL: {str(e)}')
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()
    
    return redirect(url_for('main.configuracion'))