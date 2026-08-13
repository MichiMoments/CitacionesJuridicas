"""Las tres herramientas que ve el agente: read, search y time_determination.

Envoltorios delgados sobre el dominio. Sus DOCSTRINGS son la descripción que
lee el modelo para decidir cuándo llamarlas, así que pesan tanto como el prompt.

Tres restricciones vienen del function-calling de Gemini y no son negociables
(verificadas en ``langchain_google_genai/_function_utils.py``):

  1. Nada de ``dict``, ``Any`` ni ``**kwargs`` en las firmas. Una propiedad de
     tipo ``object`` sin ``properties`` se reescribe SILENCIOSAMENTE a STRING,
     así que el modelo mandaría un string donde el código espera un dict.
  2. Toda herramienta necesita al menos un argumento explícito: a las que no
     tienen, la librería les fabrica un ``__arg1`` de tipo string.
  3. Se usan centinelas ("" y 0) en vez de ``None`` para los opcionales, para
     que el esquema quede con tipos escalares planos y sin ``anyOf``.

Ninguna lanza excepciones: devuelven ``{"ok": false, ...}``. Una herramienta que
revienta mata el turno del agente.
"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool

from citaciones_agent.busqueda import buscar_referencias
from citaciones_agent.lectura import leer_citacion
from citaciones_agent.plazos import determinar_plazo


@tool("read")
def herramienta_read(entrada: str) -> dict[str, Any]:
    """Lee la citación jurídica y extrae sus señales.

    Úsala SIEMPRE primero, con el texto íntegro de la citación. También acepta
    la ruta a un archivo .txt o .md.

    Devuelve la entidad emisora, las fechas encontradas, los plazos que menciona
    el propio documento (con su unidad si la califica), las referencias
    normativas, las señales del tipo de proceso y las señales de ubicación del
    citado. No interpreta la ley: solo describe el documento.

    Args:
        entrada: Texto completo de la citación, o ruta a un archivo .txt/.md.
    """
    return leer_citacion(entrada)


@tool("search")
def herramienta_search(consulta: str, max_resultados: int = 3) -> dict[str, Any]:
    """Busca en el corpus normativo qué tipo de citación es y su fundamento.

    Úsala después de `read`, con las palabras clave más diagnósticas del
    documento (entidad emisora, tipo de actuación, normas citadas).

    Devuelve los tipos candidatos ordenados por puntaje, con su `tipo_id`, su
    fundamento normativo y los plazos que corren contra el citado. El campo
    `fuerza` dice qué tan confiable es la coincidencia: fuerte, media, debil o
    nula. Con fuerza debil o nula, trata la citación como caso fuera del corpus.

    Args:
        consulta: Palabras clave o fragmento representativo de la citación.
        max_resultados: Cuántos tipos candidatos devolver (1 a 7).
    """
    return buscar_referencias(consulta, max_resultados)


@tool("time_determination")
def herramienta_time_determination(
    tipo_id: str = "",
    senales: str = "",
    variante_id: str = "",
    dias_indicados_en_documento: int = 0,
    unidad_dias_indicados: str = "",
) -> dict[str, Any]:
    """Fija el plazo máximo de respuesta en días hábiles. Es quien decide el número.

    Llámala después de `search`. Toda la aritmética de días ocurre aquí,
    incluida la conversión de días calendario a hábiles: tú nunca calculas.

    Devuelve `dias_habiles_recomendados` (el número que debes reportar),
    `variante_recomendada`, `regla_aplicada`, `advertencia_calendario` con su
    `texto_advertencia_calendario`, los `candidatos` cuando hay varias variantes
    posibles, y `plazos_de_la_autoridad`, que es solo contexto y nunca la
    respuesta. Si ningún tipo coincide, devuelve estado `sin_coincidencia` con
    una `guia_razonamiento` y plazos de referencia, sin inventar un número.

    Args:
        tipo_id: Identificador del tipo devuelto por `search`. Vacío si no lo tiene.
        senales: Texto o palabras clave de la citación; se usa para inferir el
            tipo cuando `tipo_id` viene vacío.
        variante_id: Identificador de la sub-variante, cuando el documento
            permite resolverla (por ejemplo el tipo de proceso o la ubicación
            del citado). Vacío si aún no se sabe.
        dias_indicados_en_documento: Días que el propio documento concede, si
            `read` encontró alguno. 0 si no hay.
        unidad_dias_indicados: "habiles" o "calendario", según cómo lo califique
            el documento. Vacío si el documento no lo dice.
    """
    return determinar_plazo(
        tipo_id=tipo_id or None,
        senales=senales,
        variante_id=variante_id or None,
        dias_indicados_en_documento=dias_indicados_en_documento or None,
        unidad_dias_indicados=unidad_dias_indicados or None,
    )


LISTA_HERRAMIENTAS = [
    herramienta_read,
    herramienta_search,
    herramienta_time_determination,
]
