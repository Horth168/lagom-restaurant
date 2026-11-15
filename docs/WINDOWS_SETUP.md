# Running LAGOM on Windows (development)

This guide assumes no previous experience. Commands go in **PowerShell**
(Start menu → type "PowerShell").

## 1. Install the tools (one time)

| Tool | Where | Check it works |
|---|---|---|
| Git | https://git-scm.com/download/win | `git --version` |
| Python 3.13 | https://www.python.org/downloads/ (tick **"Add python.exe to PATH"**) | `py -3.13 --version` |
| Node.js 22 LTS | https://nodejs.org | `node --version` |

You do **not** need to install PostgreSQL for local development: the backend
uses a local SQLite file by default.

## 2. Get the code

```powershell
cd $HOME\Desktop
git clone https://github.com/Horth168/lagom-restaurant.git
cd lagom-restaurant
```

## 3. Start the backend (API)

```powershell
cd backend
py -3.13 -m venv .venv                 # create a private Python environment
.\.venv\Scripts\Activate.ps1           # turn it on (you'll see (.venv) in the prompt)
pip install -r requirements-dev.txt    # install libraries
copy .env.example .env                 # create your settings file
alembic upgrade head                   # create the database tables
python -m scripts.seed_demo            # optional: load the demo menu, tables and staff
uvicorn app.main:app --reload          # start the API
```

If PowerShell says running scripts is disabled, run this once and answer `Y`:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Open http://localhost:8000/docs to see and try every API endpoint.

## 4. Create the real owner account

```powershell
python -m scripts.create_owner
```

It asks for your email, name and password (at least 10 characters, with upper-
and lower-case letters and a number).

## 5. Run the automated tests

```powershell
pytest
```

All tests should say `passed`.

## Demo accounts (development only)

After `python -m scripts.seed_demo` you can sign in as
`owner@lagom.test`, `admin@lagom.test`, `cashier@lagom.test`,
`kitchen@lagom.test`, `drinks@lagom.test` or `inventory@lagom.test`.
The password is the `DEMO_STAFF_PASSWORD` value defined in
`backend/scripts/seed_demo.py`. The seed script refuses to run in production.
