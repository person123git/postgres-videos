"""Interpreter customization that scripts/setup installs into .venv site-packages.

mimetypes otherwise reads host files such as /etc/apache2/mime.types, which
the project sandbox denies. Python's built-in table is the same on every host.
"""

import mimetypes

mimetypes.knownfiles.clear()
