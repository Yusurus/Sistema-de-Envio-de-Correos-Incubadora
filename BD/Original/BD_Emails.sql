DROP TABLE IF EXISTS `eventos`;

CREATE TABLE `eventos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nombre_evento` varchar(500) NOT NULL,
  `fecha_evento` varchar(100) DEFAULT NULL,
  `resolucion` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nombre_evento` (`nombre_evento`)
);

DROP TABLE IF EXISTS `notificaciones`;

CREATE TABLE `notificaciones` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `participacion_id` int(11) DEFAULT NULL,
  `canal` enum('Email','WhatsApp','SMS') DEFAULT 'Email',
  `fecha_envio` timestamp NULL DEFAULT current_timestamp(),
  `estado` enum('Enviado','Fallido','Leido') DEFAULT NULL,
  `mensaje_error` text DEFAULT NULL,
  `veces_notificado` int(11) DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `participacion_id` (`participacion_id`),
  CONSTRAINT `notificaciones_ibfk_1` FOREIGN KEY (`participacion_id`) REFERENCES `participaciones` (`id`)
);

DROP TABLE IF EXISTS `participaciones`;

CREATE TABLE `participaciones` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `participante_id` int(11) DEFAULT NULL,
  `evento_id` int(11) DEFAULT NULL,
  `rol` varchar(300) DEFAULT NULL,
  `horas_academicas` varchar(50) DEFAULT NULL,
  `certificado_url` text DEFAULT NULL,
  `qr_token` varchar(100) DEFAULT NULL,
  `estado_certificado` enum('Generado','Impreso','Entregado','Firmado','Por Imprimir','Imprimir') DEFAULT 'Generado',
  `fecha_registro` timestamp NULL DEFAULT current_timestamp(),
  `estado` enum('PENDIENTE','ENTREGADO') DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `participante_id` (`participante_id`),
  KEY `evento_id` (`evento_id`),
  CONSTRAINT `participaciones_ibfk_1` FOREIGN KEY (`participante_id`) REFERENCES `participantes` (`id`),
  CONSTRAINT `participaciones_ibfk_2` FOREIGN KEY (`evento_id`) REFERENCES `eventos` (`id`)
);

DROP TABLE IF EXISTS `participantes`;

CREATE TABLE `participantes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nombre_normalizado` varchar(255) NOT NULL,
  `nombre_completo_original` varchar(255) DEFAULT NULL,
  `email` varchar(150) DEFAULT NULL,
  `telefono` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`id`)
);