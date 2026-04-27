from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_flask_app():
    app_py = Path(__file__).with_name("app.py")
    spec = spec_from_file_location("flask_app_module", app_py)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Flask app from app.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


app = _load_flask_app()

if __name__ == "__main__":
    app.run()
