"""Construcción del agente de citaciones (create_agent de LangChain 1.x).

El modelo es INYECTABLE, igual que en ProyectoEDCO: sin argumento se construye
el de ``config``; los scripts y las pruebas pueden pasar el suyo.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy

from citaciones_agent.config import LIMITE_LLAMADAS_MODELO, modelo
from citaciones_agent.herramientas import LISTA_HERRAMIENTAS
from citaciones_agent.prompts import SYSTEM_PROMPT_CITACIONES
from citaciones_agent.schemas import ResultadoCitacion

# Mensaje de reintento cuando el modelo devuelve una salida que no valida.
_REINTENTO = (
    "La salida no cumple el esquema. Devuelve EXACTAMENTE dos campos: "
    "dias_habiles (entero entre 0 y 120, en días hábiles) y resumen (texto "
    "breve en español, máximo 600 caracteres)."
)


def construir_agente_citaciones(model=None):
    """Agente de triage de citaciones: tres herramientas y salida estructurada.

    Se pasa ``ToolStrategy`` explícito en vez de la clase Pydantic pelada. Con
    la clase pelada, la autodetección elige ``ProviderStrategy`` para los
    modelos Gemini 3, y en esa ruta una salida inválida LANZA
    ``StructuredOutputValidationError`` y se pierde la corrida entera. Con
    ``ToolStrategy`` el error vuelve al modelo como un ToolMessage y se
    reintenta, que para un caso de uso legal es mucho mejor negocio: cuesta un
    turno en vez de la respuesta completa.

    El tope de llamadas no es opcional: ``ToolStrategy`` fuerza
    ``tool_choice="any"``, es decir el modelo DEBE llamar algo en cada turno y
    nunca puede quedarse callado.
    """
    return create_agent(
        model=model if model is not None else modelo(),
        tools=LISTA_HERRAMIENTAS,
        system_prompt=SYSTEM_PROMPT_CITACIONES,
        response_format=ToolStrategy(ResultadoCitacion, handle_errors=_REINTENTO),
        middleware=[
            ModelCallLimitMiddleware(
                run_limit=LIMITE_LLAMADAS_MODELO,
                exit_behavior="end",
            )
        ],
    )
