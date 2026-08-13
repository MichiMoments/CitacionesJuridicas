"""Agente de triage de citaciones jurídicas colombianas.

Recibe una citación en texto plano y determina el PLAZO MÁXIMO DE RESPUESTA en
días hábiles, más un resumen en español que justifica ese plazo.

Topología de dependencias (acíclica, de abajo hacia arriba):

    texto  ─┐
    schemas─┼─> corpus ─┬─> lectura ─┐
            │           ├─> busqueda ┼─> plazos ─> prompts ─> herramientas ─> agente
            │           └────────────┘

``texto`` y ``schemas`` no importan nada del paquete. Solo ``herramientas`` y
``agente`` importan LangChain: todo el dominio se puede ejercitar sin el SDK,
sin credenciales y sin gastar tokens.
"""
