import sys

from . import grammar, URLVisitor

if __name__ == "__main__":
    tree = grammar.parse(sys.argv[1])
    visitor = URLVisitor()
    print(visitor.visit(tree))
