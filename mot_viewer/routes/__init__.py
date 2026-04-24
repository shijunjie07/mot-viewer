# --------------------
# Route package exports for page and API blueprints.
# @author: SHI JUNJIE
# 2026-04-25
# --------------------

from .api import api_bp
from .pages import pages_bp

__all__ = ["api_bp", "pages_bp"]
