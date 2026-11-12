"""Log filters named in settings.LOGGING. Nothing here may import the apps: it loads while Django is starting."""
import logging


class NoQueryString(logging.Filter):
    """Drops the query string from gunicorn's request lines before they are written.

    Two addresses carry things that must not sit in a log: /backoffice/?key=<BACKOFFICE_KEY> and /get/?c=<contact id>.
    gunicorn hands its access logger a dict of pieces ("atoms"): r is the request line, q the query string and f the
    page the request came from, which for a click inside the back office is that same address with its key."""

    def filter(self, record):
        atoms = record.args
        if isinstance(atoms, dict):
            for name in ("r", "f", "{referer}i"):  # the last is the same Referer under the name a custom format uses
                value = atoms.get(name)
                if isinstance(value, str) and "?" in value:
                    before, _, after = value.partition("?")
                    # Only the request line has something to keep after the query string: its last word, " HTTP/1.1".
                    # A Referer is cut at the "?" whatever follows. Looking for a space there too let the rest of a
                    # query string through when it had a space in it ("?a=1 key=VALUE").
                    atoms[name] = before + after[after.rindex(" "):] if name == "r" and " " in after else before
            if atoms.get("q"):
                atoms["q"] = "-"
        return True
