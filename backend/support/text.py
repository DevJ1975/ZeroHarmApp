"""Making text from a phone safe to keep: cleaned so the database takes it, cut to size, and, for crash reports,
with anything that could point at a person taken out.

A person's own report is kept as they typed it (they chose to send it). A crash report is written by the phone
without anyone reading it first, and error text can carry what someone had on screen: an email typed into a form, a
web address with a sign-in code in it, a phone number. So crash text goes through scrub() before it is saved."""
import hashlib
import re
import unicodedata


def line(value, limit=None):
    """One line of text: invisible and control characters become spaces, runs of spaces become one, the ends are
    trimmed, and it is cut to `limit`. Nothing (null) is "". A number is read as text, because phones send the
    Android version as one. Anything else is handed back as it came, for the schema to refuse."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return value
    text = " ".join("".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in value).split())
    return text[:limit] if limit else text


def block(value, limit=None):
    """Text that may run over several lines. Control characters go (a NUL makes PostgreSQL refuse the whole save)
    and so do broken halves of emoji (they cannot be written as UTF-8 at all); line breaks and tabs stay. The ends
    are trimmed, then it is cut to `limit`. Nothing (null) is ""."""
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    text = "".join(ch for ch in value.replace("\r\n", "\n").replace("\r", "\n")
                   if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cs")).strip()
    return text[:limit] if limit else text


# What scrub() takes out. The part of a web address after "?" or "#" is where sign-in codes and search words travel.
# It runs to the next space or quote, brackets and parentheses included ("?ids[]=5&token=..."), so a code after an
# email or a bracket in the query goes with the rest. A {...} run in it goes whole, quotes and all
# ('?data={"token":"..."}'), and so does a quoted value right after an "=" ('?q="..."'). A ":line:column" on the end
# of it is kept, because that is what says where in the code the crash was, and so is one ")" closing a stack frame.
_SAFE = r"\s\"'<>()\[\]"   # where the address itself (before "?" or "#") ends
_TAIL_STOP = r"\s\"'<>"     # where the part after "?" or "#" ends
_TAIL = rf"(?:\{{[^\s{{}}<>]*\}}|(?<==)\"[^\"\s<>]*\"|(?<==)'[^'\s<>]*'|[^{_TAIL_STOP}])*"
# Not "icon@2x.png": that is how the app names its own pictures, and it is no address. Not "f@index.bundle:12:34"
# either: that is a place in the app's code, as an iPhone's JavaScript engine writes a stack frame.
EMAIL = re.compile(r"[\w.+-]+@(?!\d(?:\.\d)?x\.)(?![\w.-]*\.bundle(?![\w.-]))[\w-]+(?:\.[\w-]+)+")
URL_LOGIN = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/?#@\s\"'<>]*@", re.I)  # "https://user:password@host" loses "user:password@"
URL_TAIL = re.compile(rf"(\b[a-z][a-z0-9+.-]*://[^?#{_SAFE}]*)([?#]{_TAIL})", re.I)
# A path with no scheme: "/reset?token=..." and "/reset#token=...". Only with an "=" in it, so "/a#top" stays.
PATH_QUERY = re.compile(rf"(/[^?#{_SAFE}]*)([?#][^{_TAIL_STOP}=]*={_TAIL})")
BARE_QUERY = re.compile(rf"([^?#{_SAFE}])([?#][\w%.~+\[\]-]*={_TAIL})")  # "invite?code=..." with no "/" or scheme
# What is left of a query that had a space in it: "?q=jane doe&token=..." keeps "doe&token=..." after the cut.
QUERY_LEFTOVER = re.compile(r"(?<!\S)[^\s\"'<>]*&[\w.%\[\]-]+=[^\s\"'<>]*")
LINE_AND_COLUMN = re.compile(r"(?::\d+){1,2}$")
ADDRESS = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# An IPv6 address: hex groups and colons with a "::" in it or at least five groups, and a digit somewhere. A place in
# the code ("bundle:1:234") has fewer groups and no "::", and a name like "std::vector" is not hex.
ADDRESS6 = re.compile(r"(?<![\w:])(?=[0-9a-f:]*\d)(?=[0-9a-f:]*::|(?:[0-9a-f]{1,4}:){4}[0-9a-f])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])", re.I)
# An id: a UUID (an iPhone app folder, a device or session id), a long hex id (a push token), or a shorter hex id
# holding six digits in a row. Each becomes one "[id]" before the number rules run, so half an id is never left in
# the text. The phone's own scrub (lib/support/crash.ts) has the same three rules, except that there a long run of
# digits alone is an id too; here it is a card or account number and becomes "[number]".
# A UUID is found with a letter or "_" right before it as well ("photo_<UUID>.jpg", "cacheV<UUID>"), where "\b" sees
# no edge; its end is the end of the hex.
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
IDS_IN_TEXT = (
    re.compile(UUID, re.I),
    re.compile(r"\b(?:0x[0-9a-f]{16,}|(?=[0-9a-f]*[a-f])[0-9a-f]{16,})\b", re.I),  # all digits is a number, below
    re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d{6})[0-9a-f]{8,}\b", re.I),
)
# Nine digits or more in a row: an account, card or phone number, never a place in the code (a line or column in
# the app's code has at most eight digits).
LONG_NUMBER = re.compile(r"(?<!\d)\d{9,}(?!\d)")
# A phone number. Never starts right after "digit:", which is a place in the code ("bundle:1:234 567"); after a
# word and ":" it is a label ("phone:702-555-1234") and goes.
PHONE = re.compile(r"(?<!\d)(?<!\d:)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\d)")
LOCAL_PHONE = re.compile(r"(?<![\w.\-])(?<!\d:)\d{3}-\d{4}(?![\w-])")  # "555-1234", a number without its area code
# Digits in groups joined by spaces, dots or hyphens: "+44 20 7946 0958", "4111 1111 1111 1111", "123-45-6789".
# Taken out when the groups hold nine digits or more between them. Never starts after "digit:" (a place in the
# code) or inside a word or an id ("3f2a9c1e-1111-2222"). A date and the hour after it ("2026-11-12 14:05") stay.
GROUPED = re.compile(r"(?<![\w.\-])(?<!\d:)\+?\d+(?:[ .-]\d+){1,}(?![\w-])")
DATE_AND_HOUR = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}")
# A place on a map: "36.169941, -115.139832". The phone takes these out too.
COORDINATE = re.compile(r"(?<![\w.])-?\d{1,3}\.\d{4,}(?![\d.])")


def _keep_position(match):
    tail, close = match.group(2), ""
    if tail.endswith(")"):
        tail, close = tail[:-1], ")"  # the ")" that closes "at f (https://...:12:34)"
    position = LINE_AND_COLUMN.search(tail)
    return match.group(1) + (position.group(0) if position else "") + close


def _grouped(match):
    found = match.group(0)
    if DATE_AND_HOUR.fullmatch(found) and match.string[match.end():match.end() + 1] == ":":
        return found  # "2026-11-12 14:05:00": a time, not a number
    return "[number]" if sum(ch.isdigit() for ch in found) >= 9 else found


def scrub(value):
    """Crash text with emails, web address details, ids, network addresses, long numbers and phone numbers taken out.
    What is left still says what broke and where. Web addresses go first, so an email inside a query string is taken
    out with the rest of the query and not left behind as "[email]&token=..."."""
    if not isinstance(value, str):
        return value
    text = URL_LOGIN.sub(r"\1", value)
    text = URL_TAIL.sub(_keep_position, text)
    text = PATH_QUERY.sub(_keep_position, text)
    text = BARE_QUERY.sub(r"\1", text)
    text = QUERY_LEFTOVER.sub("", text)
    text = EMAIL.sub("[email]", text)
    for pattern in IDS_IN_TEXT:
        text = pattern.sub("[id]", text)
    text = ADDRESS.sub("[address]", text)
    text = ADDRESS6.sub("[address]", text)
    text = PHONE.sub("[phone]", text)
    text = GROUPED.sub(_grouped, text)
    text = LOCAL_PHONE.sub("[phone]", text)
    text = COORDINATE.sub("[number]", text)
    return LONG_NUMBER.sub("[number]", text)


def route(value, limit=120):
    """The screen something happened on, as a route like "/talk/12": one line, and nothing after a "?" or "#"."""
    text = line(value)
    if not isinstance(text, str):
        return text
    return EMAIL.sub("[email]", re.split(r"[?#]", text, maxsplit=1)[0])[:limit]


def first_line(text, limit=120):
    """A title from a longer text: its first line that says anything."""
    for part in str(text or "").splitlines():
        part = " ".join(part.split())
        if part:
            return part[:limit]
    return ""


# Two crashes are the same crash when only a number or an id inside the message differs
# ("item 12 not found" and "item 97 not found").
IDS = re.compile(rf"0x[0-9a-f]+|{UUID}|\b(?=[0-9a-f]*\d)[0-9a-f]{{8,}}\b", re.I)
# What a scrub leaves of an id it has already cut into: "E91AC587-2E[number]EFD537C5BF". The phone's scrub, or an
# older one, may have cut a different part of the id on every phone, so the placeholder and every hex digit and
# hyphen touching it count as one "#". Otherwise one crash files as hundreds of tickets.
SCRUBBED = re.compile(r"[0-9a-f-]*(?:\[(?:id|number|phone|address)\][0-9a-f-]*)+", re.I)
DIGITS = re.compile(r"\d+")
JOINED = re.compile(r"#(?:-*#)+")  # "#-#-#" is one id or number, however it was cut


def fingerprint(name, message, app_version, platform):
    """What groups crash reports into one ticket: the error's name, its message with numbers and ids evened out,
    the app version and the platform."""
    evened = DIGITS.sub("#", IDS.sub("#", SCRUBBED.sub("#", message or "")))
    evened = " ".join(JOINED.sub("#", evened).lower().split())
    return hashlib.sha256("\x1f".join([name or "", evened, app_version or "", platform or ""]).encode()).hexdigest()
