"""Shared rules for uploaded and automatically adopted character assets."""

from typing import Literal

CharacterEmotion = Literal["joy", "anger", "sorrow", "fun"]
CHARACTER_EMOTIONS: tuple[CharacterEmotion, ...] = ("joy", "anger", "sorrow", "fun")
CHARACTER_ASSET_MIN_SIDE_PIXELS = 300
CHARACTER_ASSET_MAX_BYTES = 20 * 1024 * 1024
CHARACTER_ASSET_MAX_SLOTS = 5


def validate_character_asset_dimensions(width: int, height: int) -> str | None:
    if min(width, height) < CHARACTER_ASSET_MIN_SIDE_PIXELS:
        return f"画質不足です。短い辺が{CHARACTER_ASSET_MIN_SIDE_PIXELS}px以上の画像を選んでください。"
    return None
