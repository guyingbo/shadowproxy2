class InboundBase:
    def __repr__(self):
        if hasattr(self, "transport"):
            peername = self.transport.get_extra_info("peername")
            sockname = self.transport.get_extra_info("sockname")
            peer = f"{peername[0]}:{peername[1]}"
            sock = f"{sockname[0]}:{sockname[1]}"
        else:
            peer = sock = ""
        return f"{self.__class__.__name__}({peer} -> {sock})"


class OutboundBase:
    def __repr__(self):
        if hasattr(self, "transport"):
            peername = self.transport.get_extra_info("peername")
            sockname = self.transport.get_extra_info("sockname")
            peer = f"{peername[0]}:{peername[1]}"
            sock = f"{sockname[0]}:{sockname[1]}"
            if peername != self.target_addr:
                peer += f"({self.target_addr[0]}:{self.target_addr[1]})"
        else:
            peer = sock = ""
        return f"{self.__class__.__name__}({sock} -> {peer})"
