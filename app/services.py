import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from .models import db, Participacion, Participante, Notificacion
import time
import os

def send_email(to_email, subject, body):
    # (Tu código de envío de email se mantiene igual)
    try:
        msg = MIMEMultipart()
        msg['From'] = current_app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'])
        server.starttls()
        server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
        text = msg.as_string()
        server.sendmail(current_app.config['MAIL_DEFAULT_SENDER'], to_email, text)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

def get_pending_notifications(event_id, limit=50, include_notified=False):
    """
    Obtiene participantes que:
    1. Tienen certificado en estado imprimible.
    2. NO han recogido el certificado (estado != 'ENTREGADO').
    3. Tienen email válido.

    Si include_notified=True, se incluyen aunque ya tengan notificación enviada
    para permitir reenvíos manuales.
    """

    base_query = db.session.query(Participacion).join(Participante).filter(
        Participacion.evento_id == event_id,
        Participacion.estado_certificado.in_(['Impreso', 'Generado', 'Firmado', 'Por Imprimir']),
        Participacion.estado != 'ENTREGADO',
        Participante.email.isnot(None),
        Participante.email != ''
    )

    if not include_notified:
        # Excluir los que ya tuvieron una notificación enviada
        sent_subquery = db.session.query(Notificacion.participacion_id).filter(
            Notificacion.estado == 'Enviado'
        ).subquery()
        base_query = base_query.filter(~Participacion.id.in_(sent_subquery))

    return base_query.limit(limit).all()

def process_notifications(event_id, force=False):
    pending_participations = get_pending_notifications(event_id, limit=50, include_notified=force)
    results = {'total': len(pending_participations), 'success': 0, 'failed': 0, 'errors': []}

    if not pending_participations:
        return results

    for p in pending_participations:
        participante = p.participante
        evento = p.evento
        
        subject = f"Certificado Listo - {evento.nombre_evento}"
        # Se recomienda mover el HTML a un template file, pero por ahora inline está bien
        body = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                /* Estilos base para clientes de correo que los soporten */
                body {{ font-family: 'Helvetica', 'Arial', sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
                .header {{ background-color: #0056b3; color: #ffffff; padding: 20px; text-align: center; }}
                .content {{ padding: 30px; color: #333333; line-height: 1.6; }}
                .footer {{ background-color: #f9f9f9; padding: 15px; text-align: center; font-size: 12px; color: #888888; }}
                .highlight {{ color: #0056b3; font-weight: bold; }}
                .info-box {{ background-color: #eef7ff; border-left: 4px solid #0056b3; padding: 15px; margin: 20px 0; border-radius: 4px; }}
            </style>
            </head>
            <body>
            <div style="background-color: #f4f4f4; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); overflow: hidden; font-family: Arial, sans-serif;">
                
                <div style="background-color: #004aad; padding: 30px 20px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0; font-size: 24px;">¡Tu certificado está listo! 🎓</h1>
                </div>

                <div style="padding: 30px; color: #444444; line-height: 1.6;">
                    <p style="font-size: 16px; margin-bottom: 20px;">
                    Hola, <strong>{participante.nombre_normalizado}</strong>:
                    </p>
                    
                    <p>
                    Esperamos que te encuentres muy bien. Nos complace mucho informarte que tu certificado de participación del evento <strong style="color: #004aad;">{evento.nombre_evento}</strong> ya ha sido emitido exitosamente.
                    </p>
                    
                    <p>
                    Agradecemos tu entusiasmo y compromiso. Para nosotros es un honor haber contado con tu presencia.
                    </p>

                    <div style="background-color: #f0f8ff; border-radius: 6px; padding: 20px; margin: 25px 0; text-align: center; border: 1px solid #dceefc;">
                    <p style="margin: 0 0 10px 0; font-weight: bold; color: #004aad;">📍 Instrucciones de recojo:</p>
                    <p style="margin: 0; font-size: 14px;">
                        Por favor, acércate a recoger tu documento físico en nuestras oficinas.<br>
                        <em>(Horario de atención sugerido: Lun-Vie 9:00am - 5:00pm)</em>
                        <br>
                        <em>(Oficina principal: {os.environ.get('DIRECCION_RECOJO')})</em>
                    </p>
                    </div>

                    <p style="margin-top: 30px;">
                    ¡Esperamos verte pronto en nuestros próximos eventos!
                    </p>
                </div>

                <div style="background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #999999; border-top: 1px solid #eeeeee;">
                    <p style="margin: 0;">Este es un mensaje automático, por favor no responder.</p>
                    <p style="margin: 5px 0 0 0;">&copy; 2024 Organización del Evento</p>
                </div>

                </div>
            </div>
            </body>
            </html>
            """
        
        success, error = send_email(participante.email, subject, body)
        
        estado_notif = 'Enviado' if success else 'Fallido'
        
        notificacion = Notificacion(
            participacion_id=p.id,
            canal='Email',
            estado=estado_notif,
            mensaje_error=error,
            veces_notificado=1
        )
        db.session.add(notificacion)
        
        if success:
            results['success'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(f"{participante.email}: {error}")
            
        # tiempo de 10 segundos
        time.sleep(10) # Pausa cortés al servidor SMTP

    db.session.commit()
    return results


def process_single_notification(participacion_id, force=False):
    """
    Envía notificación para una sola participación.
    - Respeta: no enviar si estado es ENTREGADO.
    - Respeta: certificado en estado imprimible.
    - Si force es False, evita reenviar si ya existe 'Enviado'.
    """
    p = Participacion.query.get(participacion_id)
    if not p:
        return {'success': False, 'error': 'Participación no encontrada'}

    if p.estado == 'ENTREGADO':
        return {'success': False, 'error': 'Ya fue entregado, no se notifica'}

    if p.estado_certificado not in ['Impreso', 'Generado', 'Firmado', 'Por Imprimir']:
        return {'success': False, 'error': 'Certificado no está en estado válido para notificar'}

    participante = p.participante
    if not participante or not participante.email:
        return {'success': False, 'error': 'Participante sin email válido'}

    if not force:
        exists = db.session.query(Notificacion.id).filter(
            Notificacion.participacion_id == p.id,
            Notificacion.estado == 'Enviado'
        ).first()
        if exists:
            return {'success': False, 'error': 'Ya fue notificado previamente'}

    evento = p.evento
    subject = f"Certificado Listo - {evento.nombre_evento}"
    
    # USA EL MISMO HTML QUE process_notifications
    body = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            body {{ font-family: 'Helvetica', 'Arial', sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
            .header {{ background-color: #004aad; color: #ffffff; padding: 30px 20px; text-align: center; }}
            .content {{ padding: 30px; color: #444444; line-height: 1.6; }}
            .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #999999; border-top: 1px solid #eeeeee; }}
        </style>
        </head>
        <body>
            <div style="background-color: #f4f4f4; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; font-family: Arial, sans-serif;">
                    <div style="background-color: #004aad; padding: 30px 20px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 24px;">¡Tu certificado está listo! 🎓</h1>
                    </div>
                    <div style="padding: 30px; color: #444444; line-height: 1.6;">
                        <p style="font-size: 16px; margin-bottom: 20px;">Hola, <strong>{participante.nombre}</strong>:</p>
                        <p>Nos complace informarte que tu certificado del evento <strong style="color: #004aad;">{evento.nombre_evento}</strong> ya ha sido emitido.</p>
                        
                        <div style="background-color: #f0f8ff; border-radius: 6px; padding: 20px; margin: 25px 0; text-align: center; border: 1px solid #dceefc;">
                            <p style="margin: 0 0 10px 0; font-weight: bold; color: #004aad;">📍 Instrucciones de recojo:</p>
                            <p style="margin: 0; font-size: 14px;">
                                Oficina principal: {current_app.config.get('DIRECCION_RECOJO', 'Oficina de Incubadora')}<br>
                                <em>(Horario: Lun-Vie 9:00am - 5:00pm)</em>
                            </p>
                        </div>
                    </div>
                    <div style="background-color: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #999999;">
                        <p>&copy; 2024 Organización del Evento</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
    """

    success, error = send_email(participante.email, subject, body)
    estado_notif = 'Enviado' if success else 'Fallido'

    db.session.add(Notificacion(
        participacion_id=p.id,
        canal='Email',
        estado=estado_notif,
        mensaje_error=error,
        veces_notificado=1
    ))
    db.session.commit()

    return {'success': success, 'error': error}