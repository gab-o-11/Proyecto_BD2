from abc import ABC, abstractmethod


class Visitor(ABC):
    @abstractmethod
    def visit_select(self, node):
        pass

    @abstractmethod
    def visit_insert(self, node):
        pass

    @abstractmethod
    def visit_delete(self, node):
        pass

    @abstractmethod
    def visit_condition(self, node):
        pass


class PrintVisitor(Visitor):
    def visit_select(self, node):
        pass

    def visit_insert(self, node):
        pass

    def visit_delete(self, node):
        pass

    def visit_condition(self, node):
        pass