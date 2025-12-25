from . import db
from datetime import datetime

class Evento(db.Model):
    __tablename__ = 'eventos'
    id = db.Column(db.Integer, primary_key=True)
    nombre_evento = db.Column(db.String(500), nullable=False, unique=True)
    fecha_evento = db.Column(db.String(100))
    resolucion = db.Column(db.String(100))
    
    participaciones = db.relationship('Participacion', backref='evento', lazy=True)

class Participante(db.Model):
    __tablename__ = 'participantes'
    id = db.Column(db.Integer, primary_key=True)
    nombre_normalizado = db.Column(db.String(255), nullable=False)
    nombre_completo_original = db.Column(db.String(255))
    email = db.Column(db.String(150))
    telefono = db.Column(db.String(20))
    
    participaciones = db.relationship('Participacion', backref='participante', lazy=True)

class Participacion(db.Model):
    __tablename__ = 'participaciones'
    id = db.Column(db.Integer, primary_key=True)
    participante_id = db.Column(db.Integer, db.ForeignKey('participantes.id'))
    evento_id = db.Column(db.Integer, db.ForeignKey('eventos.id'))
    rol = db.Column(db.String(300))
    horas_academicas = db.Column(db.String(50))
    certificado_url = db.Column(db.Text)
    qr_token = db.Column(db.String(100))
    estado_certificado = db.Column(db.Enum('Generado','Impreso','Entregado','Firmado','Por Imprimir','Imprimir'), default='Generado')
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.Enum('PENDIENTE','ENTREGADO'))
    
    notificaciones = db.relationship('Notificacion', backref='participacion', lazy=True)

class Notificacion(db.Model):
    __tablename__ = 'notificaciones'
    id = db.Column(db.Integer, primary_key=True)
    participacion_id = db.Column(db.Integer, db.ForeignKey('participaciones.id'))
    canal = db.Column(db.Enum('Email','WhatsApp','SMS'), default='Email')
    fecha_envio = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.Enum('Enviado','Fallido','Leido'))
    mensaje_error = db.Column(db.Text)
    veces_notificado = db.Column(db.Integer, default=0)
