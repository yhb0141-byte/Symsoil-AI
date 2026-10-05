"""Start an isolated local API and run the real browser smoke workflow."""
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    if len(os.getenv("SYMSOIL_DEMO_PASSWORD", "")) < 12:
        raise SystemExit("Set SYMSOIL_DEMO_PASSWORD to a synthetic test password of at least 12 characters")
    with tempfile.TemporaryDirectory(prefix="symsoil-r0-browser-") as directory:
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{directory}/demo.db", "PYTHONPATH": str(ROOT / "services/api"), "SYMSOIL_WEB_DIST": str(ROOT / "apps/web/dist"), "SYMSOIL_MODE": "development", "SYMSOIL_COOKIE_SECURE": "false", "SYMSOIL_ALLOWED_ORIGINS": "http://127.0.0.1:8000", "SYMSOIL_AI_ENABLED": "false"}
        fixture = None
        if os.getenv("SYMSOIL_TEST_AI_FIXTURE") == "1":
            from ollama_fixture import MODEL, make_server
            fixture = make_server()
            threading.Thread(target=fixture.serve_forever, daemon=True).start()
            env.update(SYMSOIL_AI_ENABLED="true", SYMSOIL_OLLAMA_MODEL=MODEL, SYMSOIL_OLLAMA_URL="http://127.0.0.1:11435")
            print("Synthetic Ollama HTTP fixture enabled; no real model weights or inference", flush=True)
        python = str(ROOT / ".venv/bin/python")
        subprocess.run([python, "-m", "symsoil_api.cli", "seed", "--demo"], cwd=ROOT, env=env, check=True)
        with open(Path(directory) / "server.log", "w+") as log:
            server = subprocess.Popen([python, "-m", "uvicorn", "symsoil_api.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=1)
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise RuntimeError("API startup timeout")
                script = ROOT / os.getenv("SYMSOIL_BROWSER_SCRIPT", "tests/browser/smoke.mjs")
                result = subprocess.run(["node", str(script)], env=env, cwd=ROOT)
                return result.returncode
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
                if fixture:
                    fixture.shutdown()
                    fixture.server_close()
                    print(f"Synthetic protocol chat calls: {fixture.chat_calls}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
