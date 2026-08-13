"""Esquema de salida del agente y vocabulario cerrado del corpus.

La salida estructurada ES el guardrail principal: el agente no puede producir
texto libre fuera de ``ResultadoCitacion``.

Los tres Enum de abajo son el vocabulario con el que ``corpus`` describe cada
plazo. ``SujetoPlazo`` es el más importante de los tres — ver su docstring.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class UnidadPlazo(str, Enum):
    """Unidad en que la norma expresa el plazo.

    ``CALENDARIO`` obliga a convertir a hábiles y a advertirlo en el resumen:
    quien lea "15 días" de un requerimiento DIAN y cuente hábiles se pasa del
    término real por casi una semana.
    """

    HABILES = "habiles"
    CALENDARIO = "calendario"


class SujetoPlazo(str, Enum):
    """Contra QUIÉN corre el plazo. Sin esto el agente da respuestas erróneas.

    Varias normas del corpus fijan dos plazos distintos en el mismo artículo:
    uno para la entidad y otro para el ciudadano. En el CPACA conviven "5 días"
    (la entidad envía la citación) y "10 días" (el citado interpone recursos);
    en el Código de Policía, "5" (la autoridad cita) y "3" (el citado objeta).
    Con una lista plana de números, un agente contesta 5 en un caso de CPACA
    con toda confianza y el usuario pierde el término.

    Solo las variantes ``CITADO`` pueden ser la respuesta; las ``AUTORIDAD``
    viajan aparte, como contexto informativo.
    """

    CITADO = "citado"
    AUTORIDAD = "autoridad"


class NaturalezaPlazo(str, Enum):
    """Qué tanto manda la norma frente a lo que diga el oficio recibido.

    Habilita una regla determinística de prevalencia en ``plazos`` en vez de
    dejar que el modelo improvise cuál de los dos números gana.
    """

    PERENTORIO = "perentorio"        # la norma lo fija; gana sobre el documento
    MINIMO_LEGAL = "minimo_legal"    # la norma fija un piso; se puede conceder más
    REFERENCIAL = "referencial"      # lo fija el funcionario en el oficio


class ResultadoCitacion(BaseModel):
    """Salida única y obligatoria del agente. Exactamente dos campos.

    Esquema deliberadamente PLANO (dos escalares, sin anidamiento, sin uniones
    opcionales, sin enums): así se evita por completo la traducción de
    ``$defs``/``$ref`` al esquema de function-calling de Gemini.

    Los límites ``ge``/``le`` se descartan al construir la declaración de
    función para Gemini, así que el modelo NO los ve — pero sí validan al
    parsear y disparan el reintento de ``ToolStrategy``. Por eso el rango se
    repite dentro de la descripción, que es lo único que el modelo lee.
    """

    dias_habiles: int = Field(
        ge=0,
        le=120,
        description=(
            "Plazo MÁXIMO para responder la citación, expresado SIEMPRE en días "
            "HÁBILES (entre 0 y 120). Nunca en días calendario: si la norma "
            "habla de calendario, use el número ya convertido que devuelve la "
            "herramienta time_determination."
        ),
    )
    resumen: str = Field(
        max_length=600,
        description=(
            "Justificación breve en español (1 a 3 frases): tipo de citación "
            "identificado, norma que lo fundamenta, variante o supuesto que se "
            "asumió, y las advertencias aplicables."
        ),
    )
