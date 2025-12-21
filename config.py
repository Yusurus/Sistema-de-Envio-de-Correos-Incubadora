import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una_clave_secreta_muy_dificil_de_adivinar'
    # Database configuration
    DB_HOST= os.environ.get('DB_HOST')
    DB_PORT=os.environ.get('DB_PORT')
    DB_USER=os.environ.get('DB_USER')
    DB_PASSWORD=os.environ.get('DB_PASSWORD')
    DB_NAME=os.environ.get('DB_NAME')
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://' + DB_USER + ':' + DB_PASSWORD + '@' + DB_HOST + ':' + DB_PORT + '/' + DB_NAME
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Email configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('GMAIL_USER')
    MAIL_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('EMAIL_REMITENTE_REAL')
