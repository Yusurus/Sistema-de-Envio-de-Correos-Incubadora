from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, send_file
from .models import db, Evento, Participacion, Notificacion, Participante
from .services import process_notifications, process_single_notification
from sqlalchemy import func, case
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from io import BytesIO
from datetime import datetime
import os
import re
import pymysql

main = Blueprint('main', __name__)


def _require_login():
    if not session.get('logged_in'):
        flash('Debes iniciar sesión primero')
        return redirect(url_for('main.login'))
    return None


def _build_report_data():
    summary = {
        'total_eventos': Evento.query.count(),
        'total_participantes': Participante.query.count(),
        'total_participaciones': Participacion.query.count(),
        'total_notificaciones_enviadas': Notificacion.query.filter_by(estado='Enviado').count(),
        'total_certificados_entregados': Participacion.query.filter_by(estado='ENTREGADO').count(),
    }

    por_estado_certificado = db.session.query(
        Participacion.estado_certificado,
        func.count(Participacion.id)
    ).group_by(Participacion.estado_certificado).order_by(Participacion.estado_certificado).all()

    por_estado_entrega = db.session.query(
        Participacion.estado,
        func.count(Participacion.id)
    ).group_by(Participacion.estado).order_by(Participacion.estado).all()

    notificaciones_por_estado = db.session.query(
        Notificacion.estado,
        func.count(Notificacion.id)
    ).group_by(Notificacion.estado).order_by(Notificacion.estado).all()

    eventos = []
    for evento in Evento.query.order_by(Evento.nombre_evento.asc()).all():
        total_participantes = Participacion.query.filter_by(evento_id=evento.id).count()
        entregados = Participacion.query.filter_by(evento_id=evento.id, estado='ENTREGADO').count()
        notificados = db.session.query(Participacion).join(Notificacion).filter(
            Participacion.evento_id == evento.id,
            Notificacion.estado == 'Enviado'
        ).distinct().count()
        certificados_generados = Participacion.query.filter(
            Participacion.evento_id == evento.id,
            Participacion.estado_certificado.in_(['Generado', 'Impreso', 'Firmado', 'Escaneado'])
        ).count()

        eventos.append({
            'id': evento.id,
            'nombre': evento.nombre_evento,
            'fecha': evento.fecha_evento,
            'resolucion': evento.resolucion,
            'total_participantes': total_participantes,
            'entregados': entregados,
            'notificados': notificados,
            'certificados_generados': certificados_generados,
        })

    top_eventos = sorted(eventos, key=lambda item: item['total_participantes'], reverse=True)[:8]

    participaciones = db.session.query(
        Participacion,
        Participante,
        Evento
    ).join(Participante).join(Evento).order_by(Participacion.fecha_registro.desc()).all()

    return {
        'summary': summary,
        'eventos': eventos,
        'top_eventos': top_eventos,
        'por_estado_certificado': por_estado_certificado,
        'por_estado_entrega': por_estado_entrega,
        'notificaciones_por_estado': notificaciones_por_estado,
        'participaciones': participaciones,
    }


def _style_excel_header(sheet, headers):
    header_fill = PatternFill(fill_type='solid', fgColor='1D4ED8')
    header_font = Font(color='FFFFFF', bold=True)
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    sheet.freeze_panes = 'A2'


def _build_summary_workbook(report_data):
    workbook = Workbook()

    summary_sheet = workbook.active
    summary_sheet.title = 'Resumen'
    summary_sheet['A1'] = 'Métrica'
    summary_sheet['B1'] = 'Valor'
    _style_excel_header(summary_sheet, ['Métrica', 'Valor'])

    summary_rows = [
        ('Total eventos', report_data['summary']['total_eventos']),
        ('Total participantes', report_data['summary']['total_participantes']),
        ('Total participaciones', report_data['summary']['total_participaciones']),
        ('Notificaciones enviadas', report_data['summary']['total_notificaciones_enviadas']),
        ('Certificados entregados', report_data['summary']['total_certificados_entregados']),
    ]
    for row_number, (label, value) in enumerate(summary_rows, start=2):
        summary_sheet.cell(row=row_number, column=1, value=label)
        summary_sheet.cell(row=row_number, column=2, value=value)

    eventos_sheet = workbook.create_sheet('Eventos')
    _style_excel_header(eventos_sheet, ['Evento', 'Fecha', 'Resolución', 'Participantes', 'Entregados', 'Notificados', 'Certificados generados'])
    for row_number, evento in enumerate(report_data['eventos'], start=2):
        eventos_sheet.cell(row=row_number, column=1, value=evento['nombre'])
        eventos_sheet.cell(row=row_number, column=2, value=evento['fecha'])
        eventos_sheet.cell(row=row_number, column=3, value=evento['resolucion'])
        eventos_sheet.cell(row=row_number, column=4, value=evento['total_participantes'])
        eventos_sheet.cell(row=row_number, column=5, value=evento['entregados'])
        eventos_sheet.cell(row=row_number, column=6, value=evento['notificados'])
        eventos_sheet.cell(row=row_number, column=7, value=evento['certificados_generados'])

    participaciones_sheet = workbook.create_sheet('Participaciones')
    _style_excel_header(participaciones_sheet, ['Evento', 'Participante', 'Email', 'Rol', 'Horas', 'Estado certificado', 'Estado entrega', 'Registro'])
    for row_number, (participacion, participante, evento) in enumerate(report_data['participaciones'], start=2):
        participaciones_sheet.cell(row=row_number, column=1, value=evento.nombre_evento)
        participaciones_sheet.cell(row=row_number, column=2, value=participante.nombre_completo or participante.email)
        participaciones_sheet.cell(row=row_number, column=3, value=participante.email)
        participaciones_sheet.cell(row=row_number, column=4, value=participacion.rol)
        participaciones_sheet.cell(row=row_number, column=5, value=participacion.horas_academicas)
        participaciones_sheet.cell(row=row_number, column=6, value=participacion.estado_certificado)
        participaciones_sheet.cell(row=row_number, column=7, value=participacion.estado)
        participaciones_sheet.cell(row=row_number, column=8, value=participacion.fecha_registro.strftime('%d/%m/%Y %H:%M') if participacion.fecha_registro else '')

    return workbook


def _build_detailed_workbook(report_data):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Detalle'
    _style_excel_header(sheet, ['Tipo', 'Nombre', 'Dato 1', 'Dato 2', 'Dato 3', 'Dato 4', 'Dato 5'])

    row_number = 2
    for evento in report_data['eventos']:
        values = [
            'Evento', evento['nombre'], evento['fecha'], evento['resolucion'], evento['total_participantes'], evento['entregados'], evento['notificados']
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(row=row_number, column=column, value=value)
        row_number += 1

    for estado, cantidad in report_data['por_estado_certificado']:
        sheet.cell(row=row_number, column=1, value='Estado certificado')
        sheet.cell(row=row_number, column=2, value=estado)
        sheet.cell(row=row_number, column=3, value=cantidad)
        row_number += 1

    for estado, cantidad in report_data['por_estado_entrega']:
        sheet.cell(row=row_number, column=1, value='Estado entrega')
        sheet.cell(row=row_number, column=2, value=estado)
        sheet.cell(row=row_number, column=3, value=cantidad)
        row_number += 1

    for estado, cantidad in report_data['notificaciones_por_estado']:
        sheet.cell(row=row_number, column=1, value='Notificación')
        sheet.cell(row=row_number, column=2, value=estado)
        sheet.cell(row=row_number, column=3, value=cantidad)
        row_number += 1

    top_sheet = workbook.create_sheet('Top Eventos')
    _style_excel_header(top_sheet, ['Evento', 'Participantes', 'Entregados', 'Notificados', 'Certificados generados', 'Fecha'])
    for row_number, evento in enumerate(report_data['top_eventos'], start=2):
        top_sheet.cell(row=row_number, column=1, value=evento['nombre'])
        top_sheet.cell(row=row_number, column=2, value=evento['total_participantes'])
        top_sheet.cell(row=row_number, column=3, value=evento['entregados'])
        top_sheet.cell(row=row_number, column=4, value=evento['notificados'])
        top_sheet.cell(row=row_number, column=5, value=evento['certificados_generados'])
        top_sheet.cell(row=row_number, column=6, value=evento['fecha'])

    return workbook


def _build_summary_pdf(report_data):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportTitle', parent=styles['Title'], fontSize=20, textColor=colors.HexColor('#0F172A')))

    elements = [
        Paragraph('Reporte general de eventos y certificaciones', styles['ReportTitle']),
        Spacer(1, 0.35 * cm),
        Paragraph(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']),
        Spacer(1, 0.4 * cm),
    ]

    summary_table = [['Métrica', 'Valor']]
    summary_table.extend([
        ['Total eventos', str(report_data['summary']['total_eventos'])],
        ['Total participantes', str(report_data['summary']['total_participantes'])],
        ['Total participaciones', str(report_data['summary']['total_participaciones'])],
        ['Notificaciones enviadas', str(report_data['summary']['total_notificaciones_enviadas'])],
        ['Certificados entregados', str(report_data['summary']['total_certificados_entregados'])],
    ])

    summary = Table(summary_table, colWidths=[9 * cm, 6 * cm])
    summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1D4ED8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
    ]))
    elements.append(summary)
    elements.append(Spacer(1, 0.5 * cm))

    top_table_data = [['Evento', 'Participantes', 'Entregados', 'Notificados']]
    for evento in report_data['top_eventos']:
        top_table_data.append([
            evento['nombre'],
            str(evento['total_participantes']),
            str(evento['entregados']),
            str(evento['notificados']),
        ])

    top_table = Table(top_table_data, colWidths=[10 * cm, 3 * cm, 3 * cm, 3 * cm])
    top_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ]))
    elements.append(Paragraph('Eventos con mayor volumen', styles['Heading2']))
    elements.append(top_table)

    document.build(elements)
    buffer.seek(0)
    return buffer

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
    login_redirect = _require_login()
    if login_redirect:
        return login_redirect
    
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


@main.route('/reportes')
def reportes():
    login_redirect = _require_login()
    if login_redirect:
        return login_redirect

    report_data = _build_report_data()
    chart_data = {
        'labels_eventos': [evento['nombre'] for evento in report_data['top_eventos']],
        'values_eventos': [evento['total_participantes'] for evento in report_data['top_eventos']],
        'labels_certificado': [estado or 'Sin estado' for estado, _ in report_data['por_estado_certificado']],
        'values_certificado': [cantidad for _, cantidad in report_data['por_estado_certificado']],
        'labels_entrega': [estado or 'Sin estado' for estado, _ in report_data['por_estado_entrega']],
        'values_entrega': [cantidad for _, cantidad in report_data['por_estado_entrega']],
        'labels_notificaciones': [estado or 'Sin estado' for estado, _ in report_data['notificaciones_por_estado']],
        'values_notificaciones': [cantidad for _, cantidad in report_data['notificaciones_por_estado']],
    }
    return render_template('reportes.html', report_data=report_data, chart_data=chart_data)


@main.route('/reportes/resumen.xlsx')
def descargar_reporte_resumen_excel():
    login_redirect = _require_login()
    if login_redirect:
        return login_redirect

    report_data = _build_report_data()
    workbook = _build_summary_workbook(report_data)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name='reporte_resumen.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@main.route('/reportes/resumen.pdf')
def descargar_reporte_resumen_pdf():
    login_redirect = _require_login()
    if login_redirect:
        return login_redirect

    report_data = _build_report_data()
    buffer = _build_summary_pdf(report_data)
    return send_file(
        buffer,
        as_attachment=True,
        download_name='reporte_resumen.pdf',
        mimetype='application/pdf'
    )


@main.route('/reportes/detallado.xlsx')
def descargar_reporte_detallado_excel():
    login_redirect = _require_login()
    if login_redirect:
        return login_redirect

    report_data = _build_report_data()
    workbook = _build_detailed_workbook(report_data)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name='reporte_detallado.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

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