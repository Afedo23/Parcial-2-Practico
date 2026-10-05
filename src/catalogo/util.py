import math
import re


def texto(valor, campo, obligatorio=True, maximo=200):
    from .errores import ErrorValidacion

    v = (valor or "").strip()
    if obligatorio and not v:
        raise ErrorValidacion(f"El campo «{campo}» es obligatorio.")
    if len(v) > maximo:
        raise ErrorValidacion(f"El campo «{campo}» no puede superar {maximo} caracteres.")
    return v or None


def entero(valor, campo, obligatorio=True):
    from .errores import ErrorValidacion

    v = (str(valor) if valor is not None else "").strip()
    if not v:
        if obligatorio:
            raise ErrorValidacion(f"Debe seleccionar «{campo}».")
        return None
    try:
        return int(v)
    except ValueError:
        raise ErrorValidacion(f"«{campo}» no es válido.") from None


def numero(valor, campo):
    """Convierte a float; vacío = None (NUNCA 0)."""
    from .errores import ErrorValidacion

    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        n = float(valor)
    else:
        v = str(valor).strip().replace(",", ".")
        if not v:
            return None
        try:
            n = float(v)
        except ValueError:
            raise ErrorValidacion(f"«{campo}» debe ser un número.") from None
    if math.isnan(n) or math.isinf(n):
        raise ErrorValidacion(f"«{campo}» debe ser un número finito.")
    return n


def paginar(total, pagina, por_pagina):
    paginas = max(1, math.ceil(total / por_pagina))
    pagina = min(max(1, pagina), paginas)
    return {"pagina": pagina, "paginas": paginas, "total": total, "offset": (pagina - 1) * por_pagina, "por_pagina": por_pagina}


def entero_seguro(valor, defecto=1):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._@+\-]{2,149}$")
