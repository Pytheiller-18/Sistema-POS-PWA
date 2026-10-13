"""
Utilidades de validación de entrada y protección (A9, O8).
Todas las conversiones lanzan ValidationError, que el manejador global
traduce a HTTP 400 (en lugar de un 500 con traza interna).
"""
import threading
import time
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO_PLACES = Decimal('0.01')


class ValidationError(ValueError):
    """Error de validación de datos de entrada del cliente."""


def to_decimal(value, field: str, default=None, min_value=None, max_value=None) -> Decimal:
    """Convierte a Decimal con 2 decimales validando rango."""
    if value is None or value == '':
        if default is None:
            raise ValidationError(f'El campo "{field}" es obligatorio')
        value = default
    try:
        result = Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f'El campo "{field}" debe ser numérico')
    if not result.is_finite():
        raise ValidationError(f'El campo "{field}" debe ser un número finito')
    if min_value is not None and result < Decimal(str(min_value)):
        raise ValidationError(f'El campo "{field}" no puede ser menor que {min_value}')
    if max_value is not None and result > Decimal(str(max_value)):
        raise ValidationError(f'El campo "{field}" no puede ser mayor que {max_value}')
    return result


def to_int(value, field: str, default=None, min_value=None, max_value=None) -> int:
    """Convierte a entero validando rango."""
    if value is None or value == '':
        if default is None:
            raise ValidationError(f'El campo "{field}" es obligatorio')
        value = default
    try:
        if isinstance(value, float) and not value.is_integer():
            raise ValueError
        result = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f'El campo "{field}" debe ser un número entero')
    if min_value is not None and result < min_value:
        raise ValidationError(f'El campo "{field}" no puede ser menor que {min_value}')
    if max_value is not None and result > max_value:
        raise ValidationError(f'El campo "{field}" no puede ser mayor que {max_value}')
    return result


def clean_str(value, field: str, max_len: int, required: bool = False):
    """Normaliza cadenas: recorta espacios, valida tipo y longitud."""
    if value is None:
        if required:
            raise ValidationError(f'El campo "{field}" es obligatorio')
        return None
    if not isinstance(value, str):
        raise ValidationError(f'El campo "{field}" debe ser texto')
    value = value.strip()
    if required and not value:
        raise ValidationError(f'El campo "{field}" es obligatorio')
    if len(value) > max_len:
        raise ValidationError(f'El campo "{field}" excede {max_len} caracteres')
    return value or None


class LoginRateLimiter:
    """
    Limitador en memoria de intentos fallidos de login por (IP, email).
    Ventana deslizante: tras N fallos en W segundos se bloquea temporalmente.
    """

    def __init__(self):
        self._attempts = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key, window):
        now = time.monotonic()
        q = self._attempts[key]
        while q and now - q[0] > window:
            q.popleft()
        return q

    def is_blocked(self, key, max_attempts, window) -> int:
        """Retorna segundos restantes de bloqueo (0 si no está bloqueado)."""
        with self._lock:
            q = self._prune(key, window)
            if len(q) >= max_attempts:
                return max(1, int(window - (time.monotonic() - q[0])))
            return 0

    def register_failure(self, key, window):
        with self._lock:
            self._prune(key, window).append(time.monotonic())

    def reset(self, key):
        with self._lock:
            self._attempts.pop(key, None)


login_limiter = LoginRateLimiter()
