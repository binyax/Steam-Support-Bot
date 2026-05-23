"""
CLI de ejecución del agente.
"""
import argparse
from agent.crew import resolver_caso_soporte

def main():
    parser = argparse.ArgumentParser(description="Steam Support Agent CLI")
    parser.add_argument("--email", type=str, default="usuario@ejemplo.com", help="Email del usuario")
    parser.add_argument("--mensaje", type=str, default="No puedo iniciar sesion y vi cargos que no reconozco", help="Mensaje del usuario")
    parser.add_argument("--steam-id", type=str, default="miUsuario", dest="steam_id", help="Steam ID")
    
    args = parser.parse_args()
    
    print("Iniciando caso de soporte...")
    resultado = resolver_caso_soporte(
        mensaje_usuario=args.mensaje,
        email_usuario=args.email,
        steam_id=args.steam_id
    )
    
    print("\n--- RESULTADO FINAL ---")
    print(resultado)

if __name__ == "__main__":
    main()
