"""HTTPS con certificados que funcionan en cualquier distro.

El Python empaquetado busca los certificados en la ruta de la máquina donde
se compiló (en Debian, /usr/lib/ssl). En Arch, CachyOS o Fedora están en otro
sitio y toda petición HTTPS fallaba con CERTIFICATE_VERIFY_FAILED. Se usan
los certificados del sistema que se encuentren y además los de certifi, que
viajan con la app.
"""

from __future__ import annotations

import ssl
import urllib.request
from functools import lru_cache

# Rutas habituales del almacén del sistema (Debian/Ubuntu, Arch/Fedora, openSUSE)
_SYSTEM_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
    "/etc/ssl/ca-bundle.pem",
)


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()        # almacén del sistema (en Windows, el de Windows)
    import os
    for f in _SYSTEM_BUNDLES:
        if os.path.isfile(f):
            try:
                ctx.load_verify_locations(cafile=f)
                break
            except (OSError, ssl.SSLError):
                pass
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError, ssl.SSLError):
        pass
    return ctx


def urlopen(req, timeout: float = 30):
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())
