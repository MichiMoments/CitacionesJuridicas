import secrets
import string
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .enums import Rol
from .models import Usuario
from .types import ResultadoDesactivacion


def crear_usuario(
    email: str,
    nombre: str,
    rol: str,
    password: str,
    *,
    actor: Optional[Usuario] = None,
) -> Usuario:
    if rol not in Rol.values:
        raise ValueError(f'Rol invalido: {rol}. Opciones: {Rol.values}')

    return Usuario.objects.create_user(
        email=email,
        password=password,
        nombre_completo=nombre,
        rol=rol,
    )


def cambiar_password(
    usuario: Usuario,
    password_actual: str,
    password_nuevo: str,
) -> None:
    if not usuario.check_password(password_actual):
        raise ValueError('La contrasena actual es incorrecta.')

    usuario.set_password(password_nuevo)
    usuario.ultimo_cambio_password = timezone.now()
    usuario.save(update_fields=['password', 'ultimo_cambio_password', 'actualizado_en'])


def restablecer_password(
    usuario: Usuario,
    *,
    actor: Optional[Usuario] = None,
) -> str:
    alphabet = string.ascii_letters + string.digits + string.punctuation
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(16))

    usuario.set_password(temp_password)
    usuario.ultimo_cambio_password = timezone.now()
    usuario.save(update_fields=['password', 'ultimo_cambio_password', 'actualizado_en'])
    return temp_password


def marcar_disponibilidad(
    usuario: Usuario,
    disponible: bool,
    motivo: str,
    *,
    actor: Optional[Usuario] = None,
) -> None:
    usuario.disponible_para_asignacion = disponible
    usuario.save(update_fields=['disponible_para_asignacion', 'actualizado_en'])


@transaction.atomic
def desactivar_usuario(
    usuario: Usuario,
    *,
    actor: Optional[Usuario] = None,
) -> ResultadoDesactivacion:
    usuario.activo = False
    usuario.disponible_para_asignacion = False
    usuario.save(update_fields=['activo', 'disponible_para_asignacion', 'actualizado_en'])

    return ResultadoDesactivacion(
        usuario_id=usuario.id,
        email=usuario.email,
        citaciones_reasignadas=0,
        mensaje=f'Usuario {usuario.email} desactivado correctamente.',
    )
