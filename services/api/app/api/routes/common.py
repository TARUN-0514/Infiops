from typing import NoReturn

from fastapi import HTTPException


def not_found(what: str = "Not found.") -> NoReturn:
    raise HTTPException(404, detail={"code": "not_found", "message": what})


def bad_request(message: str, code: str = "bad_request") -> NoReturn:
    raise HTTPException(400, detail={"code": code, "message": message})
