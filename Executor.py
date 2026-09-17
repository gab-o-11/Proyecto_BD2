from Visitor import Visitor


class SemanticError(Exception):
    pass


class Executor(Visitor):
    def __init__(self):
        # TODO: referencia a tus tablas / índices de la BD
        pass

    def execute(self, statements):
        pass

    def visit_select(self, node):
        pass

    def visit_insert(self, node):
        pass

    def visit_delete(self, node):
        pass

    def visit_condition(self, node):
        pass