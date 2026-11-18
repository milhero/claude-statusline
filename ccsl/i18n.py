"""User-facing text in English and German.

Everything a person reads goes through t(). Code, settings keys and file
formats stay English in both languages; only the words on screen change.
"""

import os

LANGS = ("en", "de")

WEEKDAYS = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
}

TEXTS = {
    # Status line
    "week": ("Week", "Woche"),
    "context": ("Context", "Kontext"),
    "five_hour": ("5h", "5h"),
    "week_short": ("W", "W"),
    "context_short": ("Ctx", "Ktx"),
    "today": ("today", "heute"),
    "tomorrow": ("tomorrow", "morgen"),
    "unassigned": ("Unassigned", "Nicht zuzuordnen"),
    "other_projects": ("Other", "Übrige"),
}


def t(key, lang="en", **values):
    pair = TEXTS.get(key)
    if pair is None:
        return key
    text = pair[1] if lang == "de" else pair[0]
    return text.format(**values) if values else text


def add(texts):
    """Modules register their own strings next to the code that uses them."""
    for key, pair in texts.items():
        TEXTS[key] = pair


def weekday(index, lang="en"):
    return WEEKDAYS.get(lang, WEEKDAYS["en"])[index % 7]


def _windows_is_german():
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return (lang_id & 0x3FF) == 0x07   # primary language: German
    except Exception:
        return False


def resolve(setting, env=None):
    """Turn the setting (auto, en, de) into a language."""
    if setting in LANGS:
        return setting
    env = os.environ if env is None else env
    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = (env.get(name) or "").strip()
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return "de" if value.lower().startswith("de") else "en"
    if os.name == "nt" and _windows_is_german():
        return "de"
    return "en"


SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "CHF": "CHF", "JPY": "¥"}


def number(value, decimals, lang):
    """1234.5 -> '1,234.50' in English, '1.234,50' in German."""
    text = "{:,.{}f}".format(value, decimals)
    if lang == "de":
        text = text.translate(str.maketrans({",": ".", ".": ","}))
    return text


def money(value, currency="USD", lang="en", decimals=2, plus=False):
    """A money amount the way each language writes it.

    English puts the symbol first ($4.73, €12.00), German after the number
    with a space (4,73 $). Codes without a symbol stay codes (CHF 12.00).
    """
    amount = value or 0
    symbol = SYMBOLS.get(currency, currency)
    sign = "-" if amount < 0 else ("+" if plus else "")
    digits = number(abs(amount), decimals, lang)
    if lang == "de":
        return "{}{} {}".format(sign, digits, symbol)
    if len(symbol) > 1:
        return "{}{} {}".format(sign, symbol, digits)
    return "{}{}{}".format(sign, symbol, digits)


def percent(value, decimals, lang):
    """Share in percent: '69.5%' in English, '69,5 %' in German."""
    digits = number(value, decimals, lang)
    return digits + (" %" if lang == "de" else "%")
