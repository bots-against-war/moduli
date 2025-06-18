# moduli

Free & open-source no-code Telegram-bot constructor for activism. Focused on privacy both for bot users and admins.
Developed by [bots against war](https://t.me/bots_against_war_bot) team.

## Self-hosting

:warning: Under construction

## Development

### Basic dev setup

1. [Install](https://python-poetry.org/docs/) Poetry (tested with versions 1.5 - 1.8.5, not working on 2+). Then, install
   backend dependencies with

```bash
poetry install

# start new shell with poetry-created virtual env activated
poetry shell
```

If you have problems with `poetry`, you can manually create everything and install dependencies using `pip`
from `requirements.txt` generated from poetry dependencies:

```bash
# example of virtual env creation and activation for unix systems
python3.12 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

2. Setup minimal environment

```sh
# set environment variables (example for unix-like systems)
export TELEBOT_CONSTRUCTOR_USE_REDIS_EMULATION=1
# generate key with
# > python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("utf-8"))'
export SECRETS_ENCRYPTION_KEY=<encryption key>
# get your user ID from @bots_against_war_service_bot bot (`from.id` field)
export OWNER_CHAT_ID=<your telegram user id>
```

3. Start backend/API

```sh
# run the web app
python run_polling.py
```

4. In a separate terminal session, install frontend dependencies (`npm` v18+ required) and
start the dev server

```bash
npm install
npm run dev
```

5. Visit `http://localhost:8081` in the browser.

### Generate TS interfaces from backend data model

On any update to Pydantic data types on backend, run

```bash
npm run pydantic:to:ts
```

Check that [JSON schema](data/schema.json) and
[Typescript types](frontend/src/api/types.ts) are updated accordingly.

### Backend

#### Running tests with coverage check

```bash
coverage run -m pytest tests -vv
coverage html
```

Then you can review `htmlcov/index.html` in browser.

#### Running linters and code checks

```bash
ruff check --fix
ruff format
mypy
```

#### Adding/updating backend dependencies

We keep two versions of the same dependency list:
- `poetry` format (`pyproject.toml` + `poetry.lock`)
- regular `pip`'s `requirements.txt`

To modify dependency list, use
[`poetry add depdendency@contraint`](https://python-poetry.org/docs/cli/#add).

Then, re-generate `requirements.txt` with (there is a github action to check it)

```shell
poetry export -f requirements.txt --output requirements.txt 
```

### Frontend

We use:
- Tailwind CSS
- `flowbite` component library, see [docs](https://flowbite-svelte.com/docs/pages/introduction)
- `svelvet` (nodes/connections engine), see [docs](https://svelvet.mintlify.app/introduction)
- `flowbite-icons-svelte` for icons, see [catalog](https://flowbite-svelte-icons.vercel.app/solid)
- `svelte-i18n` for internationalization
- `svelte-kit` to prerender a separate static page for landing
