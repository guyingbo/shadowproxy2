from pydantic import BaseSettings, FilePath


class Settings(BaseSettings):
    cert_chain: FilePath = None
    key_file: FilePath = None
    ca_cert: FilePath = None
    verbose: int = 0
    blacklist: set = set()
    block_countries: set = set()
    allow_hosts: set = set()


settings = None
