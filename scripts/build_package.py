import atexit
import os
import shutil
import subprocess
from pathlib import Path

# when constructor app is hosted within a larger web application, this base path will be used
BASE_PATH = "/constructor"

ROOT_DIR = Path(__file__).parent.parent
print(f"Root dir: {ROOT_DIR.absolute()}")

STATIC_FILES_DIR = ROOT_DIR / "telebot_constructor/static"
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_BUILD_DIR = FRONTEND_DIR / "dist"
LANDING_DIR = ROOT_DIR / "landing"
LANDING_BUILD_DIR = LANDING_DIR / "dist"


def print_cmd(cmd: list[str]) -> None:
    print("Running\n$ " + " ".join(cmd))


delimiter = "\n" + "=" * 30 + "\n"


print("Determining version from GIT_TAG_NAME env var")
version = os.environ.get("GIT_TAG_NAME", "development")
print(f"Package version: {version!r}")


print(delimiter)
print("Replacing base path in custom HTML files")
paths = [Path("frontend/public") / filename for filename in ["group_chat_auth_login.html", "telegram_auth_login.html"]]
original_contents: list[str] = []
processed_contents: list[str] = []
for path in paths:
    content = path.read_text()
    original_contents.append(content)
    processed_contents.append(content.replace('const BASE_PATH = "";', f'const BASE_PATH = "{BASE_PATH}";'))
atexit.register(lambda: [path.write_text(original_content) for path, original_content in zip(paths, original_contents)])
for path, content in zip(paths, processed_contents):
    path.write_text(content)


print(delimiter)
print("Building main frontend")
vite_cmd = ["npx", "vite", "build", "--base", BASE_PATH]
print_cmd(vite_cmd)
subprocess.run(vite_cmd, env={"GIT_COMMIT_ID": version, **os.environ}, check=True, cwd=FRONTEND_DIR)


print(delimiter)
print("Copying frontend build artifacts to the /static dir inside Python package")
shutil.rmtree(STATIC_FILES_DIR, ignore_errors=True)
shutil.copytree(FRONTEND_BUILD_DIR, STATIC_FILES_DIR)


print(delimiter)
print("Building landing page")
vite2_cmd = ["npx", "vite", "build"]
print("Running\n$ " + " ".join(vite2_cmd))
subprocess.run(vite2_cmd, env={"BASE_PATH": BASE_PATH, **os.environ}, check=True, cwd=LANDING_DIR)


print("Copying landing build artifacts to the /static dir inside Python package")
for src in LANDING_BUILD_DIR.iterdir():
    dest_name = src.name if src.name != "index.html" else "landing.html"
    dest = STATIC_FILES_DIR / dest_name
    print(f"    {src.relative_to(ROOT_DIR)} => {dest.relative_to(ROOT_DIR)}")
    if src.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)
    else:
        dest.unlink(missing_ok=True)
        shutil.copy(src, dest)


print(delimiter)
print("Setting build-time configuration in backend Python code")
build_time_config_file = Path("telebot_constructor/build_time_config.py")
build_time_config_body = build_time_config_file.read_text()
atexit.register(lambda: build_time_config_file.write_text(build_time_config_body))
build_time_config_body_preprocessed = build_time_config_body.replace('BASE_PATH = ""', f'BASE_PATH = "{BASE_PATH}"')
build_time_config_body_preprocessed = build_time_config_body_preprocessed.replace(
    'VERSION = ""', f'VERSION = "{version}"'
)
build_time_config_file.write_text(build_time_config_body_preprocessed)


print(delimiter)
print("Building final package")
poetry_cmd = ["poetry", "build"]
print_cmd(poetry_cmd)
subprocess.run(poetry_cmd, check=True)


print(delimiter)
print("See ya!")
