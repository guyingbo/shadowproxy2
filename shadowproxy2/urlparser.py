import types
import sys
from parsimonious.grammar import Grammar
from parsimonious.nodes import NodeVisitor

grammar = r"""
url         = (transport "+")? proxy "://" (username ":" password "@")? host? ":" port ("#" pair)?
transport   = "tcp" / "kcp" / "quic" / "udp" / "tls"
proxy       = "ss" / "socks5" / "socks4" / "http" / "tunnel" / "red"
host        = ipv4 / fqdn
ipv4        = ~r"\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}"
fqdn        = ~r"([0-9a-z]((-[0-9a-z])|[0-9a-z])*\.){0,4}[a-z]+"i
username    = ~r"[\w-]+"
password    = ~r"[\w-]+"
port        = ~r"\d+"
pair        = key "=" value
key         = "via" / "name"
value       = ~r"[\w-]+"
"""


grammar = Grammar(grammar)


class URLVisitor(NodeVisitor):
    def __init__(self):
        self.info = {
            "transport": "tcp",
            "username": None,
            "password": None,
            "host": "0.0.0.0",
        }

    def visit_proxy(self, node, visited_children):
        self.info["proxy"] = node.text

    def visit_transport(self, node, visited_children):
        self.info["transport"] = node.text

    def visit_username(self, node, visited_children):
        self.info["username"] = node.text

    def visit_password(self, node, visited_children):
        self.info["password"] = node.text

    def visit_host(self, node, visited_children):
        self.info["host"] = node.text

    def visit_port(self, node, visited_children):
        self.info["port"] = int(node.text)

    def visit_pair(self, node, visited_children):
        self.info[node.children[0].text] = node.children[2].text

    def visit_url(self, node, visited_children):
        return types.SimpleNamespace(**self.info)

    def generic_visit(self, node, visited_children):
        return node


if __name__ == "__main__":
    tree = grammar.parse(sys.argv[1])
    visitor = URLVisitor()
    print(visitor.visit(tree))
