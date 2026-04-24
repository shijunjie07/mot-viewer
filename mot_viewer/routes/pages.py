# --------------------
# Page routes for rendering the viewer interface.
# @author: SHI JUNJIE
# 2026-04-25
# --------------------

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def index():
    """Render the main viewer page."""
    return render_template("index.html")
