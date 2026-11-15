"""Conexiones a MySQL (SQLAlchemy + PyMySQL) y MongoDB (pymongo)."""
from collections.abc import Iterator
from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Connection, Engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    # URL.create escapa la contraseña: no hay que armar la URL a mano
    url = URL.create(
        "mysql+pymysql",
        username=s.mysql_user,
        password=s.mysql_password,
        host=s.mysql_host,
        port=s.mysql_port,
        database=s.mysql_database,
        query={"charset": "utf8mb4"},
    )
    connect_args = {}
    if s.mysql_ssl_ca:
        # TLS entre la app y MySQL, verificando el certificado del servidor
        connect_args["ssl"] = {"ca": s.mysql_ssl_ca}
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args)


def get_db() -> Iterator[Connection]:
    """Dependencia de FastAPI: una transacción por petición.
    Si la ruta lanza una excepción, se hace ROLLBACK; si no, COMMIT."""
    with get_engine().begin() as conn:
        yield conn


@lru_cache
def get_mongo_client() -> MongoClient:
    return MongoClient(get_settings().mongo_uri, serverSelectionTimeoutMS=3000, tz_aware=True)


def get_mongo_db() -> Database:
    """Base de datos indicada en MONGO_URI (ej. .../sarais?authSource=sarais)."""
    return get_mongo_client().get_default_database()
