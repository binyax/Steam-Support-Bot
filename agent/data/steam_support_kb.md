# Base de Conocimiento — Soporte de Steam

Documento de referencia que alimenta la memoria semántica a largo plazo (FAISS)
del Steam Support Agent. Cada sección es un fragmento recuperable por similitud.

## 1. Recuperación de cuenta (account recovery)
Si un usuario perdió el acceso a su cuenta de Steam, debe iniciar el proceso en
help.steampowered.com seleccionando "No puedo iniciar sesión". Steam solicitará
verificar la identidad mediante el correo asociado, el número de teléfono, o un
método de pago histórico (últimos 4 dígitos de la tarjeta o ID de transacción).
El bot debe confirmar al usuario por correo electrónico que se ha abierto un caso
de recuperación e indicar los pasos de verificación. Nunca se debe pedir la
contraseña completa por correo. El tiempo estándar de recuperación es de 24 a 72
horas hábiles.

## 2. Alertas de seguridad y robo de cuenta (account theft / hijacking)
Indicadores de cuenta comprometida: inicios de sesión desde regiones
desconocidas, cambios de correo no autorizados, o intercambios (trades) no
reconocidos. Acción prioritaria: bloquear la cuenta vía Steam Guard, forzar
cambio de contraseña y revocar sesiones activas. El agente debe enviar de
inmediato un correo de ALERTA DE SEGURIDAD con prioridad alta, instrucciones para
activar Steam Guard Mobile Authenticator y un enlace al portal oficial de
soporte. Los artículos y cromos intercambiados fraudulentamente pueden, en
algunos casos, ser restaurados por el equipo de soporte dentro de los 30 días.

## 3. Confirmación de tickets de soporte
Cada vez que se abre un caso, el sistema genera un identificador único con
formato `STM-XXXXXX`. El agente debe enviar un correo de confirmación que
incluya: número de ticket, resumen del problema, prioridad asignada y tiempo
estimado de respuesta. Prioridades: BAJA (consultas generales, 72h), MEDIA
(problemas de compra/instalación, 48h), ALTA (seguridad/acceso, 24h).

## 4. Reembolsos (refunds)
Steam reembolsa cualquier juego solicitado dentro de los 14 días posteriores a la
compra y con menos de 2 horas de juego acumuladas. Las solicitudes se gestionan
en help.steampowered.com. Las compras de DLC, contenido in-game y créditos de
billetera (Steam Wallet) tienen reglas particulares. El agente debe validar la
elegibilidad antes de confirmar y, si no aplica, escalar a revisión manual.

## 5. Steam Guard y autenticación de dos factores (2FA)
Steam Guard protege la cuenta mediante un código enviado por correo o generado
por la app móvil. Para operaciones sensibles (cambio de correo, retiro de
artículos del Market) se exige el Steam Guard Mobile Authenticator activo por al
menos 7 días. Si el usuario perdió el acceso al autenticador, debe usar la opción
"Ayuda con el Steam Guard Mobile Authenticator" para recuperar el acceso, lo que
desactiva temporalmente el Market por 15 días por seguridad.

## 6. Problemas de compra y facturación
Errores comunes: pago rechazado, cargo duplicado, compra no acreditada. El agente
debe solicitar el ID de transacción y validar el método de pago. Los cargos
duplicados se reembolsan automáticamente en 5-7 días hábiles. Cualquier disputa
de cargo (chargeback) bloquea la cuenta hasta su resolución y requiere
escalamiento manual obligatorio.

## 7. Reglas de escalamiento manual (handoff)
El agente debe escalar a un humano cuando: (a) hay una disputa de cargo o fraude
financiero, (b) la identidad del usuario no puede ser verificada con los datos
disponibles, (c) el caso involucra una posible violación de los Términos de
Servicio (baneo VAC, comportamiento abusivo), o (d) el envío de correo falla tras
los reintentos automáticos. En todos estos casos se registra el caso para
revisión humana y se informa al usuario del cambio de canal.

## 8. Política de comunicación por correo
Todos los correos deben: identificarse como "Soporte de Steam (asistente
automatizado)", incluir el número de ticket, no solicitar contraseñas ni códigos
2FA completos, y dirigir siempre a los dominios oficiales (steampowered.com /
steamcommunity.com). El tono debe ser claro, empático y orientado a la acción.
