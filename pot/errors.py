"""One error type for the whole host: a stable machine-readable code + detail.

str(exc) is "code: detail" (or just "code"), so the tool layer can render
"ERROR: <code>: <detail>" the way Fungi's tools do.
"""


class PotError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
