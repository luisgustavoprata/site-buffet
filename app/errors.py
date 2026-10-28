"""Respostas de erro num formato só, com mensagens em português.

{"detail": "Dados inválidos.", "errors": [{"field": "title", "message": "Campo obrigatório."}]}
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

MESSAGES = {
    "missing": "Campo obrigatório.",
    "string_too_short": "Deve ter pelo menos {min_length} caractere(s).",
    "string_too_long": "Deve ter no máximo {max_length} caracteres.",
    "too_long": "No máximo {max_length} itens.",
    "string_type": "Deve ser um texto.",
    "int_parsing": "Deve ser um número inteiro.",
    "int_type": "Deve ser um número inteiro.",
    "int_from_float": "Deve ser um número inteiro.",
    "bool_parsing": "Use true ou false.",
    "greater_than_equal": "Deve ser maior ou igual a {ge}.",
    "less_than_equal": "Deve ser menor ou igual a {le}.",
    "date_from_datetime_parsing": "Data inválida. Use AAAA-MM-DD.",
    "date_parsing": "Data inválida. Use AAAA-MM-DD.",
    "date_type": "Data inválida. Use AAAA-MM-DD.",
    "enum": "Valor inválido. Use: {expected}.",
    "literal_error": "Valor inválido. Use: {expected}.",
    "extra_forbidden": "Campo não permitido.",
    "json_invalid": "JSON inválido.",
    "list_type": "Deve ser uma lista.",
    "model_attributes_type": "Envie um objeto JSON.",
    "dict_type": "Envie um objeto JSON.",
}


def _message(error: dict) -> str:
    if error.get("input") in ("", None) and error["type"] != "extra_forbidden":
        return "Campo obrigatório."
    if error["type"] == "string_too_short" and error.get("ctx", {}).get("min_length") == 1:
        return "Não pode ficar vazio."
    template = MESSAGES.get(error["type"])
    if template is None:
        return error["msg"].removeprefix("Value error, ")
    try:
        return template.format(**error.get("ctx", {}))
    except (KeyError, IndexError):
        return error["msg"]


def _field(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "body"


async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"field": _field(e["loc"]), "message": _message(e)} for e in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "Dados inválidos.", "errors": errors},
    )


def register(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_handler)
