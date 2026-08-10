import re

def _protect_and_translate(text, trans_table):
    """Translate text with `trans_table`, but protect HTML tags (<...>) and
    HTML entities (&...;) so they are never corrupted into invalid markup.

    Without entity protection, escaping a name such as '<3' to '&lt;3' would
    have its letters translated ('lt' -> 'ʟᴛ'), breaking the entity and
    producing markup Telegram rejects ('Can't parse entities')."""
    parts = re.split(r'(<[^>]+>|&[^;]+;)', text)
    result = []
    for part in parts:
        if not part:
            continue
        # Keep HTML tags and entities verbatim
        if (part.startswith('<') and part.endswith('>')) or part.startswith('&'):
            result.append(part)
        else:
            result.append(part.translate(trans_table))
    return "".join(result)


def to_small_caps(text):
    """Converts standard characters to small caps characters while preserving HTML tags and entities."""
    normal_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    small_caps_chars = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789"
    
    trans_table = str.maketrans(normal_chars, small_caps_chars)

    # Split the text into parts that are HTML tags/entities and parts that are not
    return _protect_and_translate(text, trans_table)

def to_mono(text):
    """Converts standard characters to typewriter/mono characters while preserving HTML tags and entities."""
    normal_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    mono_chars = "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"
    
    trans_table = str.maketrans(normal_chars, mono_chars)
    
    # Split the text into parts that are HTML tags/entities and parts that are not
    return _protect_and_translate(text, trans_table)
