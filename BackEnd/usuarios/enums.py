from django.db import models


class Rol(models.TextChoices):
    ABOGADO = 'ABOGADO', 'Abogado'
    JURIDICA = 'JURIDICA', 'Juridica'
    ADMIN = 'ADMIN', 'Administrador'
