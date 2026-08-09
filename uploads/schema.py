import graphene

from .mutations import CompletarSubidaSesion, MarcarSubidaEnProgreso


class Mutation(graphene.ObjectType):
    completar_subida_sesion = CompletarSubidaSesion.Field()
    marcar_subida_en_progreso = MarcarSubidaEnProgreso.Field()
