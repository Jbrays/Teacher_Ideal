"""
Utilidades de validación de periodos.
"""

from datetime import datetime
from typing import Optional, Set

def obtener_periodos_validos(desde: Optional[datetime] = None, cantidad: int = 4) -> Set[str]:
    """
    Genera los últimos N periodos académicos válidos contando hacia atrás
    desde el periodo actual.
    El formato de salida es YYYY-CC.
    """
    if desde is None:
        desde = datetime.utcnow()

    anio = desde.year
    mes = desde.month

    if mes <= 6:
        ciclo_actual = "10"
    else:
        ciclo_actual = "20"

    periodos = []
    ciclo = int(ciclo_actual)
    for _ in range(cantidad):
        periodos.append(f"{anio}-{ciclo:02d}")
        if ciclo == 10:
            ciclo = 20
            anio -= 1
        else:
            ciclo = 10

    return set(periodos)
