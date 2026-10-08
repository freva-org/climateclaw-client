"""Interactive, authenticated shell for the ClimateClaw chatbot.

The shell needs the optional ``cli`` dependencies, install them with
``pip install climateclaw-client[cli]``.
"""

import sys


def main() -> None:
    """Run the ``climateclaw-shell`` command."""
    try:
        from ._app import app
    except ImportError as error:  # pragma: no cover
        sys.exit(
            f"The climateclaw shell is missing a dependency ({error.name}), "
            "install it with: pip install 'climateclaw-client[cli]'"
        )
    app()
