CREATE TABLE `archivospagos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_pago` int(11) NOT NULL,
  `monto` varchar(100) DEFAULT NULL,
  `fechapago` date DEFAULT NULL,
  `horapago` time DEFAULT NULL,
  `file` varchar(300) DEFAULT NULL,
  `observacion` text DEFAULT NULL,
  `estadopago` varchar(50) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_pago` (`id_pago`),
  CONSTRAINT `archivospagos_ibfk_1` FOREIGN KEY (`id_pago`) REFERENCES `pagos` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=748 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `ciclos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_pago` int(11) NOT NULL,
  `nrociclo` int(11) DEFAULT NULL,
  `sesion` varchar(30) DEFAULT NULL,
  `estadosesion` varchar(30) DEFAULT NULL,
  `fecha` date DEFAULT NULL,
  `estadopago` varchar(30) DEFAULT NULL,
  `eri` varchar(60) DEFAULT NULL,
  `cim` varchar(60) DEFAULT NULL,
  `ejecucion` text DEFAULT NULL,
  `apuntes` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_pago` (`id_pago`),
  CONSTRAINT `ciclos_ibfk_1` FOREIGN KEY (`id_pago`) REFERENCES `pagos` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2763 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `clientes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nombres` varchar(100) DEFAULT NULL,
  `apellidos` varchar(100) DEFAULT NULL,
  `usuario` varchar(50) DEFAULT NULL,
  `contrasenia` varchar(500) DEFAULT NULL,
  `celular` int(11) DEFAULT NULL,
  `edad` varchar(20) DEFAULT NULL,
  `fechnac` date DEFAULT NULL,
  `carnet` varchar(50) DEFAULT NULL,
  `foto` varchar(500) DEFAULT NULL,
  `estado` varchar(10) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=180 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `demucas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_infocliente` int(11) NOT NULL,
  `evaluacion` varchar(30) DEFAULT NULL,
  `rango` int(11) DEFAULT NULL,
  `palabra` varchar(50) DEFAULT NULL,
  `escala` varchar(10) DEFAULT NULL,
  `multiplicar` int(11) DEFAULT NULL,
  `fecha` date DEFAULT NULL,
  `categoria` varchar(60) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_infocliente` (`id_infocliente`),
  CONSTRAINT `demucas_ibfk_1` FOREIGN KEY (`id_infocliente`) REFERENCES `infoclientes` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5301 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `infoclientes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_cliente` int(11) NOT NULL,
  `diagnostico` varchar(100) DEFAULT NULL,
  `residenciaactual` varchar(250) DEFAULT NULL,
  `tipotratamiento` varchar(100) DEFAULT NULL,
  `duracion` int(11) DEFAULT NULL,
  `fechaadmision` date DEFAULT NULL,
  `tutor` varchar(80) DEFAULT NULL,
  `frecuencia` varchar(100) DEFAULT NULL,
  `objgenerales` varchar(300) DEFAULT NULL,
  `fisico` varchar(300) DEFAULT NULL,
  `emocional` varchar(300) DEFAULT NULL,
  `cognitivo` varchar(300) DEFAULT NULL,
  `social` varchar(300) DEFAULT NULL,
  `metodosausar` varchar(300) DEFAULT NULL,
  `notas` text DEFAULT NULL,
  `cuestionario` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_cliente` (`id_cliente`),
  CONSTRAINT `infoclientes_ibfk_1` FOREIGN KEY (`id_cliente`) REFERENCES `clientes` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=178 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `matrizescalas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `categoria` varchar(60) DEFAULT NULL,
  `nombrematriz` varchar(60) DEFAULT NULL,
  `valor` varchar(15) DEFAULT NULL,
  `multiplicar` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=139 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `pagos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_infocliente` int(11) NOT NULL,
  `precio` int(11) DEFAULT NULL,
  `saldo` int(11) DEFAULT NULL,
  `pagado` int(11) DEFAULT NULL,
  `horario` varchar(100) DEFAULT NULL,
  `tipo` varchar(80) DEFAULT NULL,
  `descuento` varchar(100) DEFAULT NULL,
  `fecha` varchar(100) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_infocliente` (`id_infocliente`),
  CONSTRAINT `pagos_ibfk_1` FOREIGN KEY (`id_infocliente`) REFERENCES `infoclientes` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=690 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `plandeintervencions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `orden` int(11) DEFAULT NULL,
  `id_infocliente` int(11) NOT NULL,
  `momento` varchar(40) DEFAULT NULL,
  `objetivo` varchar(40) DEFAULT NULL,
  `foco` varchar(40) DEFAULT NULL,
  `mlt` varchar(40) DEFAULT NULL,
  `enfoque` varchar(40) DEFAULT NULL,
  `duracion` varchar(40) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_infocliente` (`id_infocliente`),
  CONSTRAINT `plandeintervencions_ibfk_1` FOREIGN KEY (`id_infocliente`) REFERENCES `infoclientes` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=164 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `submatrizescalas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_matrizescala` int(11) NOT NULL,
  `tipo` varchar(100) DEFAULT NULL,
  `nombresubmatriz` varchar(100) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_matrizescala` (`id_matrizescala`),
  CONSTRAINT `submatrizescalas_ibfk_1` FOREIGN KEY (`id_matrizescala`) REFERENCES `matrizescalas` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=43 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `subplandeintervencions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_plandeintervencion` int(11) NOT NULL,
  `categoria` varchar(80) DEFAULT NULL,
  `nombre` varchar(80) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `id_plandeintervencion` (`id_plandeintervencion`),
  CONSTRAINT `subplandeintervencions_ibfk_1` FOREIGN KEY (`id_plandeintervencion`) REFERENCES `plandeintervencions` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=721 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci

CREATE TABLE `usuarios` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nombres` varchar(100) DEFAULT NULL,
  `apellidos` varchar(100) DEFAULT NULL,
  `usuario` varchar(50) DEFAULT NULL,
  `contrasenia` varchar(500) DEFAULT NULL,
  `celular` int(11) DEFAULT NULL,
  `celulartrabajo` int(11) DEFAULT NULL,
  `carnet` varchar(50) DEFAULT NULL,
  `foto` varchar(500) DEFAULT NULL,
  `estado` varchar(10) DEFAULT NULL,
  `tipo` varchar(500) DEFAULT NULL,
  `funciones` varchar(250) DEFAULT NULL,
  `hojadevida` text DEFAULT NULL,
  `visibilidad` varchar(15) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci


