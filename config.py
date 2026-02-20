import os
import pymysql

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una_clave_secreta_muy_dificil_de_adivinar'
    
    # Datos de conexión base (Prioriza variables de entorno de Render)
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = int(os.environ.get('DB_PORT') or 3306)
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or ''
    DB_NAME = os.environ.get('DB_NAME') or 'pruebas_incu'

    # URI para SQLAlchemy
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            cursorclass=pymysql.cursors.DictCursor
        )
        with connection.cursor() as cursor:
            # Consultamos la fila con ID 1 de tu tabla configuracion
            cursor.execute("SELECT * FROM configuraciones WHERE idconfiguracion = 1")
            db_config = cursor.fetchone()
            
            if db_config:
                # Asignamos los valores de la DB (ajusta los nombres de las columnas si son distintos)
                GMAIL_USER = db_config.get('gmail_user')
                GMAIL_APP_PASSWORD = db_config.get('gmail_app_password')
                EMAIL_REMITENTE_REAL = db_config.get('email_remitente_real')
                # Puedes agregar más como la dirección
                DIRECCION_RECOJO = db_config.get('direccion_recojo')
            else:
                # Valores por defecto si no existe el ID 1
                GMAIL_USER = os.environ.get('GMAIL_USER')
                GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
                EMAIL_REMITENTE_REAL = os.environ.get('EMAIL_REMITENTE_REAL')
        connection.close()
    except Exception as e:
        print(f"Error cargando config desde DB: {e}")
        # Backup: si la DB falla, intenta leer del .env o entorno
        MAIL_USERNAME = os.environ.get('GMAIL_USER')
        MAIL_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
        MAIL_DEFAULT_SENDER = os.environ.get('EMAIL_REMITENTE_REAL')

    # Configuración fija del servidor
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
