"""Configuración del modelo Gemini y guardrails de costo.

Ruta de acceso: API de Gemini (``langchain-google-genai``) con GOOGLE_API_KEY
tomada del archivo ``.env`` de la raíz.
"""

from __future__ import annotations

MODELO = "gemini-3.1-flash-lite"

# Temperatura 1.0 y no un valor bajo: el propio código de langchain-google-genai
# fuerza 1.0 en modelos Gemini 3+ cuando el usuario no la fija, y su comentario
# explica por qué — "to prevent infinite loops and degraded performance that can
# occur with temperature < 1.0 on these models". Al pasarla explícitamente ese
# guardrail NO se activa, así que aquí se pasa el valor recomendado.
# El determinismo de este agente no viene de la temperatura: viene del esquema
# de salida forzado y de que TODOS los plazos los calcula Python en `plazos.py`.
TEMPERATURA = 1.0

MAX_TOKENS_SALIDA = 10000

# `thinking_budget=0` está DEPRECADO para Gemini 3+ (la librería lo dice
# explícitamente) y su sustituto es `thinking_level`. Si no se fija, Gemini 3
# usa "high", y el razonamiento consume el mismo presupuesto de salida que la
# respuesta: una cadena larga puede truncar el JSON final.
NIVEL_PENSAMIENTO = "minimal"

# ToolStrategy obliga al modelo a llamar una herramienta en CADA turno
# (tool_choice="any"), así que sin un tope la corrida podría no terminar.
LIMITE_LLAMADAS_MODELO = 8

# Tope de pasos del grafo. Se fija explícito en vez de confiar en el valor por
# defecto de langgraph, que no se verificó para esta instalación.
LIMITE_RECURSION = 30


def modelo(nombre: str = MODELO):
    """Construye el modelo de chat. Importa el SDK de forma perezosa.

    ``load_dotenv()`` va ANTES de instanciar a propósito: ``google_api_key`` se
    resuelve en el CONSTRUCTOR de ``ChatGoogleGenerativeAI``, así que cargar el
    .env después no serviría de nada.
    """
    from dotenv import load_dotenv

    load_dotenv()

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=nombre,
        temperature=TEMPERATURA,
        max_output_tokens=MAX_TOKENS_SALIDA,
        thinking_level=NIVEL_PENSAMIENTO,
    )
