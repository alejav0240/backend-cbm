from graphene_django.views import GraphQLView
from django.http import JsonResponse

class CBMGraphQLView(GraphQLView):
    def execute_graphql_request(self, *args, **kwargs):
        response = super().execute_graphql_request(*args, **kwargs)
        
        if response and hasattr(response, 'errors') and response.errors:
            for error in response.errors:
                if "No autenticado." in str(error):
                    # Podríamos cambiar el status code aquí si quisiéramos
                    # Pero en GraphQL es común mantener 200.
                    # Sin embargo, para mejorar el manejo de sesión, 
                    # vamos a forzar un 401 si es un error de auth.
                    pass
        
        return response

    @staticmethod
    def format_error(error):
        formatted_error = GraphQLView.format_error(error)
        # Aquí podríamos personalizar el formato del error si quisiéramos
        return formatted_error

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        
        if response.status_code == 200 and request.method == "POST":
            try:
                import json
                # Asegurar decodificación y manejo de errores flexible
                content = json.loads(response.content.decode('utf-8'))
                if "errors" in content:
                    for error in content["errors"]:
                        msg = error.get("message", "")
                        if "No autenticado" in msg or "Signature has expired" in msg:
                            response.status_code = 401
                            break
            except Exception:
                pass
                
        return response
