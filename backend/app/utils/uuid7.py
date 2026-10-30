"""
Utilidad para generación de identificadores únicos UUIDv7 (RFC 9562).
Proporciona identificadores ordenables cronológicamente con precisión de milisegundos,
optimizando el rendimiento de inserción e indexación en árboles B/B+ (InnoDB, SQLite).
"""
import os
import time
import uuid

# Prioridad 1: Librería estándar en Python 3.14+
# Prioridad 2: Librería uuid6 externa (RFC 9562)
# Prioridad 3: Implementación nativa conforme a RFC 9562
try:
    from uuid import uuid7 as _builtin_uuid7
    def uuid7() -> uuid.UUID:
        return _builtin_uuid7()
except ImportError:
    try:
        import uuid6
        def uuid7() -> uuid.UUID:
            return uuid6.uuid7()
    except ImportError:
        def uuid7() -> uuid.UUID:
            """Genera UUIDv7 puro en Python según RFC 9562 Sección 5.7."""
            timestamp_ms = int(time.time() * 1000)
            rand_bytes = bytearray(os.urandom(10))
            time_bytes = timestamp_ms.to_bytes(6, byteorder='big')
            # Versión 7 en los 4 bits superiores del byte 6
            ver_and_rand = (0x70 | (rand_bytes[0] & 0x0f))
            # Variante RFC 4122 (10xx) en los 2 bits superiores del byte 8
            var_and_rand = (0x80 | (rand_bytes[2] & 0x3f))
            raw = (
                time_bytes +
                bytes([ver_and_rand, rand_bytes[1], var_and_rand]) +
                rand_bytes[3:10]
            )
            return uuid.UUID(bytes=raw)


def uuid7_str() -> str:
    """Retorna la representación canónica en cadena de un UUIDv7."""
    return str(uuid7())


def is_uuid7(val: str) -> bool:
    """Valida si una cadena corresponde a un UUIDv7 válido."""
    try:
        parsed = uuid.UUID(str(val))
        return parsed.version == 7
    except (ValueError, TypeError, AttributeError):
        return False

