# Sistema de Notificaciones - Incubadora UNASAM

Este sistema permite enviar notificaciones por correo electrónico a los participantes de eventos cuyos certificados ya están impresos.

## Requisitos

1.  Python 3.8+
2.  MySQL Server

## Instalación

1.  Instalar dependencias:
    ```bash
    pip install -r requirements.txt
    ```

2.  Configuración:
    -   Abre el archivo `config.py`.
    -   Configura la conexión a la base de datos (`SQLALCHEMY_DATABASE_URI`).
    -   Configura las credenciales de Gmail (`MAIL_USERNAME`, `MAIL_PASSWORD`).
    -   **Nota**: Para Gmail, es posible que necesites usar una "Contraseña de Aplicación" si tienes la verificación en dos pasos activada.

## Ejecución

1.  Ejecutar la aplicación:
    ```bash
    python run.py
    ```
2.  Abrir en el navegador: `http://localhost:5000`
3.  Credenciales por defecto:
    -   Usuario: `admin`
    -   Contraseña: `admin`

## Uso

-   **Dashboard**: Muestra métricas generales y una lista de eventos.
-   **Enviar Notificaciones**: En la tabla de eventos, si hay certificados impresos pendientes de notificar, aparecerá un botón "Enviar Lote (32)".
-   **Límites**: El sistema envía correos en lotes de 32 con un retraso de 1 segundo entre cada uno para evitar bloqueos.
