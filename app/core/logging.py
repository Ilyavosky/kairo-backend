import json
import logging


class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        carga: dict[str, str] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "nivel": record.levelname,
            "logger": record.name,
            "mensaje": record.getMessage(),
        }
        if record.exc_info:
            carga["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(carga, ensure_ascii=False)


def configurar_logging(nivel: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(FormatoJson())
    raiz = logging.getLogger()
    raiz.handlers = [handler]
    raiz.setLevel(nivel.upper())
    for ruidoso in ("httpx", "httpcore"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
