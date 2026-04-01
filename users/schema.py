# users/schema.py
from .queries import Query as UsersQuery
from .mutations import Mutation as UsersMutation

class Query(UsersQuery):
    pass

class Mutation(UsersMutation):
    pass