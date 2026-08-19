import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoDesactivacion:
    usuario_id: uuid.UUID
    email: str
    citaciones_reasignadas: int = 0
    mensaje: str = ''
