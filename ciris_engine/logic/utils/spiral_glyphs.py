def get_glyph(tag: str) -> str:
    return {
        "ignite": "🜂",
        "harmony": "🕊️",
        "divergence": "⟁",
        "human_required": "✴️"
    }.get(tag, "")
