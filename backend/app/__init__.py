"""Online XSD/XML Viewer backend package."""

import os

__version__ = "0.2.0"


def release_version() -> str:
    """The package version plus the Cloud Run revision serving it, if any.

    ``__version__`` only moves when someone bumps it, but every deploy is a
    new revision. Usage rows and sample_issue fingerprints need to tell deploys
    apart, or nobody can see whether a fix worked.
    """
    revision = os.environ.get("K_REVISION", "").strip()
    return f"{__version__}+{revision}" if revision else __version__
