# AgenteTriage — plazo de respuesta a citaciones jurídicas

Agente LangChain que recibe una **citación jurídica colombiana en texto plano** y
devuelve dos cosas:

- `dias_habiles`: el plazo **máximo** de respuesta, siempre en días hábiles.
- `resumen`: una justificación breve en español de por qué ese plazo.

Modelo: `gemini-3.1-flash-lite` por la API de Gemini.

## Instalación

```powershell
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # y ponga su GOOGLE_API_KEY
```

## Uso

```powershell
venv\Scripts\python.exe examples\demo_citaciones.py
```

El demo corre cuatro citaciones sintéticas (notificación personal civil,
requerimiento DIAN, comparendo de policía y una que no está en el corpus),
imprime la traza de herramientas con sus puntajes y la salida estructurada.

Desde código:

```python
from citaciones_agent.agente import construir_agente_citaciones
from citaciones_agent.prompts import formatear_entrada

agente = construir_agente_citaciones()
salida = agente.invoke(
    {"messages": [{"role": "user", "content": formatear_entrada(texto_citacion)}]},
    config={"recursion_limit": 30},
)
resultado = salida.get("structured_response")   # .get: la clave es NotRequired
print(resultado.dias_habiles, resultado.resumen)
```

## Las tres herramientas

| Herramienta | Módulo | Qué hace |
|---|---|---|
| `read` | `lectura.py` | Describe el documento: entidad emisora, fechas, plazos que menciona, referencias normativas, señales del tipo de proceso y de ubicación del citado. Acepta texto o una ruta `.txt`/`.md`. |
| `search` | `busqueda.py` | Empareja la citación contra el corpus normativo local y reporta la `fuerza` de la coincidencia. |
| `time_determination` | `plazos.py` | **Fija el número de días.** Toda la aritmética ocurre aquí, incluida la conversión calendario→hábiles. |

El modelo nunca calcula ni convierte nada: copia `dias_habiles_recomendados`.

## Arquitectura

```
texto  ─┐
schemas─┼─> corpus ─┬─> lectura ─┐
        │           ├─> busqueda ┼─> plazos ─> prompts ─> herramientas ─> agente
        │           └────────────┘
```

Solo `herramientas.py` y `agente.py` importan LangChain: **todo el dominio se
puede ejercitar sin el SDK, sin credenciales y sin gastar tokens.**

`corpus.py` es la **única fuente de verdad** de todo plazo y toda norma.
`prompts.py` se construye por f-string desde el corpus, así que el prompt no
puede contradecir al código — ni un número de días aparece escrito a mano.

## Tres decisiones de diseño que cargan el peso

**1. `SujetoPlazo` (`schemas.py`).** Varias normas fijan en el mismo artículo un
plazo para la entidad y otro para el ciudadano: en el CPACA conviven "5 días"
(la entidad envía la citación) y "10 días" (el citado interpone recursos); en el
Código de Policía, "5" (la autoridad cita) y "3" (el citado objeta). Con una
lista plana de números el agente contesta 5 en un caso de CPACA con toda
confianza. Solo las variantes `CITADO` pueden ser la respuesta.

**2. Conservador = menos días.** Son plazos perentorios: pasarse hace perder el
término (irreversible), quedarse corto solo cuesta urgencia. De ahí el piso en
`calendario_a_habiles` (15 → 10, no 11), el defecto conservador de cada tipo y
la regla "ante la duda, el plazo más corto" del prompt.

**3. `variante_por_defecto = None` en `cit_traslado_demanda`.** Entre 3 y 20 días
no hay defecto honesto: el procedimiento es un hecho declarado en el documento,
no una circunstancia asumible. El agente está obligado a resolverlo o a declarar
el supuesto.

## Deuda declarada

- **El corpus no fue contrastado contra fuente oficial.** Lo aportó el dueño del
  proyecto; cada tipo lleva `fuente_verificada = False`. Cambiar un plazo es una
  decisión del dueño del dato, no solo un cambio de código.
- **La conversión calendario→hábiles ignora los festivos.** 15 días calendario
  que crucen Semana Santa pueden ser 9 hábiles reales, no 10. La advertencia que
  acompaña esos plazos lo dice. La costura para un `fecha_inicio` con calendario
  real de festivos queda abierta.
- **Umbrales de `busqueda.py` sin calibrar** (0.55 / 0.30 / 0.10) y pesos 3/2/1.
  Se eligieron a ojo y se validaron contra 15 consultas; conviene ajustarlos con
  citaciones reales. El demo imprime los puntajes justamente para eso.
- **Respaldo web de `search()` no implementado.** Hoy devuelve
  `{"estado": "sin_backend"}` y el agente sigue con el corpus local. El diseño
  acordado está documentado en el `TODO` de `busqueda.py::_respaldo_web` y las
  dependencias candidatas están comentadas en `requirements.txt`.
- **Tipos 3, 4 y 6:** los "30 días" de conciliación y los "5 días" de CPACA y del
  Código de Policía no especifican unidad en el dato de origen; se asumen hábiles
  y se declara en la `nota`. Los tres son plazos de la **autoridad**, así que
  nunca pueden ser la respuesta y el riesgo queda contenido.
- **Tipo 7 (MinTrabajo):** no se afirma que la Resolución 0312 de 2019 fije 10
  días de respuesta. Es `REFERENCIAL`: el plazo lo fija el oficio del inspector y
  ese prevalece.
- **Tipo 3 es el encaje más forzado:** una citación a conciliación no da "N días
  para responder", da una **fecha** para comparecer. El único término en días
  contra el citado son los 3 hábiles para justificar la inasistencia.

## Notas de la integración con Gemini

Detalles verificados en el código fuente instalado, que explican decisiones que
de otro modo parecen arbitrarias:

- **`TEMPERATURA = 1.0`**, no un valor bajo. `langchain_google_genai` fuerza 1.0
  en Gemini 3+ cuando el usuario no la fija, "*to prevent infinite loops and
  degraded performance that can occur with temperature < 1.0 on these models*".
  El determinismo lo dan el esquema forzado y `plazos.py`, no la temperatura.
- **`thinking_level="minimal"`**, no `thinking_budget=0`: este último está
  deprecado para Gemini 3+. El razonamiento consume el mismo presupuesto de
  salida que la respuesta, y una cadena larga puede truncar el JSON final.
- **`ToolStrategy` explícito** y no la clase Pydantic pelada. Con la clase pelada
  la autodetección elige `ProviderStrategy`, y ahí una salida inválida **lanza** y
  se pierde la corrida entera; con `ToolStrategy` el error vuelve al modelo como
  ToolMessage y se reintenta.
- **Firmas de herramienta solo con escalares** (`str`, `int`), con centinelas
  `""`/`0` en vez de `None`. Un parámetro `dict` se reescribe silenciosamente a
  `STRING` en el function-calling de Gemini, y los centinelas evitan `anyOf` en
  el esquema.
- **`ModelCallLimitMiddleware` no es opcional:** `ToolStrategy` fuerza
  `tool_choice="any"`, es decir el modelo debe llamar algo en cada turno.
- **Siempre `salida.get("structured_response")`:** la clave es `NotRequired` y no
  existe si la corrida terminó por el tope de llamadas.

Si la capa Gemini falla, la escalera de respaldo es: cambiar a
`ProviderStrategy`; ajustar el mensaje de `handle_errors` en `agente.py`; probar
con `gemini-2.5-flash` para aislar si es el modelo; y como último recurso
`model.with_structured_output(ResultadoCitacion, method="json_schema")` haciendo
la recuperación en Python plano.
