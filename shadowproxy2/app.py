from pydantic import BaseSettings, FilePath


class Settings(BaseSettings):
    cert_chain: FilePath = None
    key_file: FilePath = None
    ca_cert: FilePath = None
    verbose: int = 0
    blacklist: set = set()


settings = None
