import ipaddress


def is_global(host: str) -> bool:
    """
    >>> assert not is_global("127.0.0.1")
    >>> assert not is_global("192.168.20.168")
    >>> assert is_global("211.13.20.168")
    >>> assert is_global("google.com")
    """
    if host == "localhost":
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return address.is_global
