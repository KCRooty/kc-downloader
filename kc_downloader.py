"""KC Downloader — punto de entrada (el código vive en el paquete kcdl/)."""

import sys

from kcdl.app import main

if __name__ == "__main__":
    sys.exit(main())
