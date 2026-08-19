import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .enums import Rol
from .managers import UsuarioManager


class Usuario(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        'correo electronico',
        unique=True,
        db_index=True,
    )
    nombre_completo = models.CharField(
        'nombre completo',
        max_length=180,
    )
    rol = models.CharField(
        'rol',
        max_length=20,
        choices=Rol.choices,
        default=Rol.ABOGADO,
    )
    activo = models.BooleanField(
        'activo',
        default=True,
        help_text='Desactivar en lugar de eliminar.',
    )
    disponible_para_asignacion = models.BooleanField(
        'disponible para asignacion',
        default=True,
        help_text='Vacaciones, incapacidad o carga excepcional.',
    )
    peso_maximo = models.DecimalField(
        'peso maximo de carga',
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Tope opcional de carga.',
    )
    ultima_asignacion = models.DateTimeField(
        'ultima asignacion',
        null=True,
        blank=True,
        db_index=True,
        help_text='Criterio de desempate en el reparto.',
    )
    is_staff = models.BooleanField(
        'acceso al admin',
        default=False,
        help_text='Permite acceder al sitio de administracion de Django.',
    )
    ultimo_cambio_password = models.DateTimeField(
        'ultimo cambio de password',
        null=True,
        blank=True,
    )
    creado_en = models.DateTimeField('creado en', auto_now_add=True)
    actualizado_en = models.DateTimeField('actualizado en', auto_now=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre_completo', 'rol']

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        ordering = ['nombre_completo']
        indexes = [
            models.Index(
                fields=['rol', 'activo', 'disponible_para_asignacion'],
                name='idx_candidatos_asignacion',
            ),
        ]

    def __str__(self):
        return f'{self.nombre_completo} ({self.email})'

    @property
    def is_active(self):
        return self.activo
