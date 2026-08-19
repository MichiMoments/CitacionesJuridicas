Plan: App usuarios - Custom User Model
Context
The project needs a custom Django user model (Usuario) before any migration is ever run. Switching AUTH_USER_MODEL after Django's auth migrations have been applied requires dropping and recreating the database, so this must happen first. The model supports the legal citation assignment system: users have roles (ABOGADO, JURIDICA, ADMIN), availability tracking, and workload caps.

Step 1 — Install dependencies
Update BackEnd/requirements.txt, add:

psycopg2-binary==2.9.10
argon2-cffi==23.1.0
python-dotenv==1.1.0
Then pip install -r requirements.txt inside the venv.

Step 2 — Configure settings.py
File: BackEnd/citjur/settings.py

All changes in one pass, before any startapp or migrate:

Top of file (after from pathlib import Path): add import os and from dotenv import load_dotenv, then load_dotenv(BASE_DIR.parent / '.env') — the .env is at the repo root, one level above BackEnd/.

INSTALLED_APPS: add 'usuarios' at the top of the list.

After INSTALLED_APPS: add AUTH_USER_MODEL = 'usuarios.Usuario'.

DATABASES: replace SQLite with PostgreSQL using os.environ.get() for each credential (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST defaulting to localhost, POSTGRES_PORT).

After AUTH_PASSWORD_VALIDATORS: add PASSWORD_HASHERS with Argon2PasswordHasher first, then PBKDF2/BCrypt/Scrypt as fallbacks.

Internationalization: change LANGUAGE_CODE to 'es-co' and TIME_ZONE to 'America/Bogota'.

Step 3 — Create the usuarios app
Run python manage.py startapp usuarios inside BackEnd/, then create/edit these files:

usuarios/enums.py (new)
Rol(models.TextChoices) with values: ABOGADO, JURIDICA, ADMIN.

usuarios/managers.py (new)
UsuarioQuerySet(models.QuerySet) — methods abogados() and asignables().
UsuarioManager(BaseUserManager) — overrides get_queryset() to return UsuarioQuerySet, implements create_user() and create_superuser(). Superusers default to rol='ADMIN'.
usuarios/models.py (replace generated content)
Usuario(AbstractBaseUser, PermissionsMixin):

UUID primary key
email as USERNAME_FIELD (unique, indexed)
nombre_completo, rol (from Rol choices), activo, disponible_para_asignacion, peso_maximo (Decimal nullable), ultima_asignacion (DateTime nullable indexed), is_staff, ultimo_cambio_password, creado_en (auto_now_add), actualizado_en (auto_now)
is_active as @property aliasing activo — single source of truth, no separate DB column
Composite index on (rol, activo, disponible_para_asignacion) named idx_candidatos_asignacion
db_table = 'usuarios'
REQUIRED_FIELDS = ['nombre_completo', 'rol']
usuarios/types.py (new)
ResultadoDesactivacion — frozen dataclass with usuario_id, email, citaciones_reasignadas, mensaje.

usuarios/services.py (new)
Five service functions per spec:

crear_usuario(email, nombre, rol, password, *, actor) — validates rol, delegates to create_user
cambiar_password(usuario, password_actual, password_nuevo) — verifies current, sets new, updates ultimo_cambio_password
restablecer_password(usuario, *, actor) — generates 16-char random password via secrets, returns plaintext
marcar_disponibilidad(usuario, disponible, motivo, *, actor) — toggles disponible_para_asignacion
desactivar_usuario(usuario, *, actor) — @transaction.atomic, sets activo=False and disponible_para_asignacion=False, returns ResultadoDesactivacion
All mutating saves use update_fields (including 'actualizado_en'). actor param present for future audit logging.

usuarios/admin.py (replace generated content)
UsuarioAdmin(DjangoUserAdmin):

Extends Django's UserAdmin for proper password hash handling
Custom fieldsets and add_fieldsets (no reference to username/first_name/last_name)
List display: email, nombre_completo, rol, activo, disponible, is_staff
Readonly: creado_en, actualizado_en, last_login
usuarios/apps.py (edit generated)
Set verbose_name = 'Gestion de usuarios'.

Step 4 — Migrate
docker compose up -d (start Postgres)
python manage.py makemigrations usuarios
python manage.py migrate
python manage.py createsuperuser
Step 5 — Verify
python manage.py check — no issues
python manage.py makemigrations --check — no changes detected
Shell smoke test: create a user, test queryset methods, change password, toggle availability, deactivate
python manage.py runserver — visit /admin/, confirm user list and password form work
Verify Argon2: identify_hasher(make_password('test')).algorithm == 'argon2'