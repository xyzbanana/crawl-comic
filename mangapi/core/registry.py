"""
MangAPI — Source Registry
Đăng ký và tra cứu parser theo source name.
"""
from __future__ import annotations
from ..core.base_parser import BaseParser
from ..parsers.nettruyen import NettruyenParser
from ..parsers.truyenqq import TruyenqqParser
from ..parsers.cuutruyen import CuutruyenParser

_REGISTRY: dict[str, BaseParser] = {
    "nettruyen": NettruyenParser(),
    "truyenqq":  TruyenqqParser(),
    "cuutruyen": CuutruyenParser(),
}


def get_parser(source: str) -> BaseParser:
    parser = _REGISTRY.get(source.lower())
    if not parser:
        available = list(_REGISTRY.keys())
        raise ValueError(f"Source '{source}' không tồn tại. Có sẵn: {available}")
    return parser


def list_sources() -> list[str]:
    return list(_REGISTRY.keys())


def all_parsers() -> list[BaseParser]:
    return list(_REGISTRY.values())
