# --------------------
# MOT Viewer.
# @author: SHI JUNJIE
# 2026-04-25
# --------------------

from mot_viewer import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
