import argparse
import sys
import os

# Ajoute le répertoire parent au path pour que les imports absolus depuis server fonctionnent
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Utilise des imports absolus depuis server pour éviter les problèmes d'imports relatifs
from server.agents.interaction_agent import InteractionAgentRuntime
import asyncio

def main():
    parser = argparse.ArgumentParser(description='Bridge Telegram messages to backend.')
    parser.add_argument('--sender', type=str, required=True)
    parser.add_argument('--text', type=str, required=True)
    parser.add_argument('--timestamp', type=str, required=False)
    args = parser.parse_args()

    # Appelle la logique backend pour traiter le message et générer la réponse
    async def run():
        try:
            runtime = InteractionAgentRuntime()
            result = await runtime.execute(user_message=args.text)

            # TOUJOURS envoyer une réponse à l'utilisateur, même en cas d'erreur
            # Ne sortir avec code 1 que pour les vraies exceptions Python (bloc except)

            # Priorité 1: Réponse générée (succès ou erreur avec message)
            if result.response and result.response.strip():
                print(result.response)
                sys.exit(0)

            # Priorité 2: Erreur mais pas de réponse - générer un message user-friendly
            if not result.success:
                error_msg = result.error or "Une erreur s'est produite"
                # Envoyer un message user-friendly au lieu de l'erreur brute
                user_message = f"Désolé, j'ai rencontré un problème : {error_msg}"
                print(user_message)
                sys.exit(0)  # ✅ Sort avec succès car on a répondu à l'utilisateur

            # Priorité 3: Succès mais aucune réponse (duplicate detector, tool 'wait', etc.)
            fallback = (
                "Je n'ai pas généré de réponse pour ce message. "
                "Peut-être que c'était un doublon ou qu'un outil silencieux a été utilisé. "
                "Réessaie si besoin."
            )
            print(fallback)
            sys.exit(0)
        except Exception as e:
            # Seulement ici on sort avec code 1 : vraies exceptions Python
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)

    asyncio.run(run())

if __name__ == '__main__':
    main()
