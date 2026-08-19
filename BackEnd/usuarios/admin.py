from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(DjangoUserAdmin):
    ordering = ('nombre_completo',)
    list_display = (
        'email',
        'nombre_completo',
        'rol',
        'activo',
        'disponible_para_asignacion',
        'is_staff',
    )
    list_filter = ('rol', 'activo', 'disponible_para_asignacion', 'is_staff')
    search_fields = ('email', 'nombre_completo')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informacion personal', {'fields': ('nombre_completo',)}),
        ('Rol y asignacion', {
            'fields': (
                'rol',
                'activo',
                'disponible_para_asignacion',
                'peso_maximo',
                'ultima_asignacion',
            ),
        }),
        ('Permisos', {
            'fields': (
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            ),
        }),
        ('Fechas', {
            'fields': (
                'ultimo_cambio_password',
                'last_login',
                'creado_en',
                'actualizado_en',
            ),
        }),
    )
    readonly_fields = ('creado_en', 'actualizado_en', 'last_login')

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email',
                'nombre_completo',
                'rol',
                'password1',
                'password2',
            ),
        }),
    )
