"""CLI exit error types."""

EXIT_CODES: dict[str, int] = {
    "internal": 1,
    "invalid_input": 2,
    "not_found": 3,
    "non_conformant": 4,
    "drift": 5,
}


class OkfError(Exception):
    def __init__(self, kind: str, message: str, result=None):
        if kind not in EXIT_CODES:
            raise ValueError("unknown OKF error kind: {}".format(kind))
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.code = EXIT_CODES[kind]
        self.result = result
