"""
GeneLink Content Moderation
Filtra palavrões, conteúdo suspeito e criminoso em português e inglês.
Registra alertas na tabela admin_flags para revisão pelo admin.
"""

import re
from db.connection import get_connection

# ── Listas de palavras ────────────────────────────────────────────────────────

_PROFANITY = [
    # PT-BR
    "porra", "merda", "caralho", "puta", "viado", "fdp", "filho da puta",
    "corno", "arrombado", "buceta", "cu ", " cu", "cuzao", "cuzão",
    "desgraça", "inferno", "idiota", "imbecil", "babaca", "vadia", "vagabunda",
    "piranha", "safado", "safada", "otario", "otário", "cretino", "lixo",
    # EN
    "fuck", "shit", "asshole", "bitch", "cunt", "dick", "pussy", "bastard",
    "motherfucker", "whore", "slut", "faggot", "nigger",
]

_SUSPICIOUS = [
    # Fraude / golpe
    "transferencia bancaria", "transferência bancária", "transferir dinheiro",
    "pix agora", "cartão de crédito", "número do cartão", "senha do banco",
    "western union", "bitcoin grátis", "bitcoin gratis", "criptomoeda gratis",
    "clique no link", "acesse o link", "ganhe dinheiro", "renda extra",
    "investimento garantido",
    # Spam
    "whatsapp group", "grupo whatsapp", "telegram group",
    # Ameaças
    "vou te matar", "te mato", "vou te bater", "te acerto",
    "vou te encontrar", "descobri seu endereço", "sei onde você mora",
    # Conteúdo ilegal
    "drogas", "cocaina", "cocaína", "heroina", "heroína", "crack vendo",
    "vendo arma", "vendo armas", "pistola vendo", "rifle vendo",
    "conteudo infantil", "conteúdo infantil", "menor de idade",
    "child porn", "cp link", "underage",
    # EN threats
    "i will kill", "gonna kill you", "kill yourself", "kys",
    "i know where you live", "found your address",
]

_CRIMINAL = [
    "comprar arma", "comprar drogas", "trafico", "tráfico", "traficante",
    "lavagem de dinheiro", "money laundering", "terrorismo", "atentado",
    "bomb threat", "bomba aqui", "explodir",
]


def _normalize(text: str) -> str:
    return text.lower()


def check_content(text: str) -> dict:
    """
    Analisa o conteúdo e retorna:
    {
        'flagged': bool,
        'reasons': list[str],   # lista de motivos
        'severity': str,        # 'low' | 'medium' | 'high'
    }
    """
    norm = _normalize(text)
    reasons = []
    severity = "low"

    for w in _PROFANITY:
        pattern = r'\b' + re.escape(w) + r'\b' if ' ' not in w else re.escape(w)
        if re.search(pattern, norm):
            reasons.append(f"profanity:{w}")
            if severity == "low":
                severity = "low"

    for w in _SUSPICIOUS:
        if w in norm:
            reasons.append(f"suspicious:{w}")
            severity = "medium"

    for w in _CRIMINAL:
        if w in norm:
            reasons.append(f"criminal:{w}")
            severity = "high"

    return {
        "flagged": len(reasons) > 0,
        "reasons": reasons,
        "severity": severity,
    }


def flag_message(sender_id: int, content: str, msg_type: str, reference_id: int, reasons: list):
    """Salva um alerta de moderação no banco de dados para o admin revisar."""
    reason_str = ", ".join(reasons[:5])  # limita o tamanho
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO admin_flags (type, content, sender_id, reference_id, reason)
               VALUES (%s, %s, %s, %s, %s)""",
            (msg_type, content[:500], sender_id, reference_id, reason_str),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[GeneLink][Moderation] Error saving flag: {e}")
