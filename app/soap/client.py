import html
import re
import xml.sax.saxutils as saxutils

import requests
from requests.auth import HTTPBasicAuth


class SoapError(Exception):
    pass


class SoapClient:
    """Cliente ligero para el endpoint SOAP de AzerothCore (comandos GM)."""

    def __init__(self, host: str, port: int, username: str, password: str, timeout: float = 5.0):
        self.url = f"http://{host}:{port}/"
        self.auth = HTTPBasicAuth(username, password)
        self.timeout = timeout

    def execute(self, command: str) -> str:
        escaped = saxutils.escape(command)
        envelope = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
            "<SOAP-ENV:Body>"
            '<ns1:executeCommand xmlns:ns1="urn:AC">'
            f"<command>{escaped}</command>"
            "</ns1:executeCommand>"
            "</SOAP-ENV:Body>"
            "</SOAP-ENV:Envelope>"
        )
        try:
            response = requests.post(
                self.url,
                data=envelope.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                auth=self.auth,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SoapError(f"No se pudo contactar con el servicio SOAP: {exc}") from exc

        if response.status_code == 401:
            raise SoapError("Credenciales SOAP invalidas.")
        if response.status_code >= 500:
            match = re.search(r"<faultstring>(.*?)</faultstring>", response.text, re.DOTALL)
            raise SoapError(html.unescape(match.group(1)).strip() if match else "Error SOAP desconocido.")

        match = re.search(r"<result>(.*?)</result>", response.text, re.DOTALL)
        if match:
            return html.unescape(match.group(1)).strip()
        return response.text.strip()
