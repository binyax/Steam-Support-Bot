"""
Listas de palabras para el filtro de coherencia.

Se separa de security.py para mantener archivos compactos.
"""

# Lista corta y especifica de palabras vulgares puras (ES + EN).
# NO incluye expresiones comunes ("maldito", "carajo") para no romper
# mensajes legitimos. Solo insultos puros y vulgaridades explicitas.
PROFANITY_WORDS = {
    # ES
    "pene", "polla", "verga", "pinga", "pija", "vagina", "concha", "cono",
    "culo", "cula", "culiao", "culiada", "csm", "ctm",
    "puto", "puta", "putas", "putos", "putada", "putamadre",
    "mierda", "cagada", "cagado", "cagar",
    "joder", "jodete", "jodida", "jodido",
    "cabron", "cabrona", "cabrones", "cabronas",
    "huevon", "wn", "weon", "weona", "hueon", "hueona",
    "marica", "maricon", "maricona", "maricones", "joto",
    "perra", "perras", "zorra", "zorras",
    "estupido", "estupida", "imbecil", "imbeciles",
    # EN
    "fuck", "fucking", "fucker", "fucked", "motherfucker",
    "shit", "shitty", "bullshit", "shithead",
    "ass", "asshole", "asses", "dumbass",
    "dick", "dickhead", "cock", "pussy",
    "bitch", "bitches", "bitchy",
    "nigger", "nigga", "nword",
    "faggot", "fag", "retard", "retarded",
    "cunt", "twat", "bastard", "whore", "slut",
}

# Conectores y palabras vacias que no cuentan como "significativas"
STOP_WORDS = {
    # ES
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "a", "al", "y", "o", "u", "pero", "si", "no",
    "que", "como", "cuando", "donde", "porque", "para", "por",
    "mi", "tu", "su", "mis", "tus", "sus", "me", "te", "se", "le", "les",
    "este", "esta", "estos", "estas", "ese", "esa", "eso", "esto",
    "todo", "todos", "todas", "mas", "menos", "ya", "muy", "tan",
    "yo", "ella", "nos", "vos", "lo",
    "es", "son", "soy", "estan", "fue", "era", "ser",
    "n",  # "n word" attack
    # EN
    "the", "a", "an", "of", "in", "to", "for", "and", "or", "but",
    "that", "this", "these", "those", "is", "are", "was", "were",
    "my", "your", "his", "her", "their", "i", "you", "he", "she", "we", "they",
    "it", "its", "be", "been", "being",
    "word",  # "n word" attack
}

# Palabras-clave que indican intencion de soporte de Steam.
# Si ALGUNA aparece, el mensaje se considera consulta legitima.
SUPPORT_CONTEXT_WORDS = {
    # Genericas
    "problema", "problemas", "error", "errores", "ayuda", "ayudar",
    "soporte", "fallo", "falla", "funciona", "funcionar", "anda", "andar",
    "necesito", "quiero", "puedo", "pueden", "podria", "ayudarme",
    # Cuenta
    "cuenta", "usuario", "perfil", "login", "logueo", "logearme",
    "iniciar", "ingresar", "ingreso", "sesion", "entrar",
    "password", "pass", "contrasena", "contrasenas", "clave",
    "email", "correo", "mail", "verificacion", "autenticador", "guard",
    "hackeo", "hackeado", "robado", "robaron", "acceso", "perdi", "perdido",
    # Compra
    "compra", "compras", "compre", "comprar", "comprado",
    "pago", "pagos", "pagar", "pagado", "tarjeta", "cargo", "cargos",
    "reembolso", "reembolsos", "devolucion", "devolver", "factura",
    "transaccion", "cobro", "cobraron", "dinero",
    # Juego / biblioteca
    "juego", "juegos", "jugar", "biblioteca", "library", "instalar",
    "instalacion", "descargar", "descarga", "actualizar", "actualizacion",
    "dlc", "demo", "key", "codigo", "activar", "activacion",
    "partida", "partidas", "multijugador", "multiplayer", "single",
    "lag", "lags", "conexion", "servidor", "servidores", "ping",
    "guardado", "guardar", "save", "progreso",
    # Plataforma
    "steam", "valve", "deck", "store", "tienda", "comunidad", "amigos",
    "workshop", "mod", "mods", "trading", "intercambio",
    "windows", "mac", "linux", "consola", "version",
    # Especificos
    "ban", "baneo", "baneado", "vac", "reporte", "reportar",
    "screenshot", "captura", "achievement", "logro", "logros",
    # EN
    "account", "purchase", "buy", "bought", "refund", "game", "play",
    "stolen", "hacked", "access",
    "install", "download", "update", "issue", "support",
    "help", "problem", "broken", "crash", "crashed", "freeze",
}
