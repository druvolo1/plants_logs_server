# GitHub Preparation Checklist

## Files to DELETE Before Pushing to GitHub

### ✅ Already Deleted
- [x] `__pycache__/` directories (Python bytecode cache)
- [x] `*.pyc` files (Python bytecode files)

### 🔴 MUST DELETE (Sensitive/Personal)
```bash
# Delete these files - they contain secrets or are personal
rm .env                           # Contains database passwords and API keys!
rm app/main_backup.py             # Backup file, not needed in Git
```

### 🟡 SHOULD DELETE (Cleanup/Build Scripts)
```bash
# These are one-time migration/setup scripts
rm refactor_main.py               # One-time refactoring script
rm verify_imports.py              # Verification script
rm run_migration_*.py             # Migration scripts (003-007)
rm run_migration_*.bat            # Migration batch files
rm sync_schema_from_prod.py      # Production sync script
rm sync_schema.bat                # Sync batch file
rm setup_database.bat             # Setup batch file
rm export_prod_schema.sql        # Production export
rm add_missing_columns.sql       # Migration SQL
```

### 🟢 KEEP (Core Project Files)
```bash
# These files should be committed
✓ app/                           # Main application code
✓ static/                        # Static assets
✓ templates/                     # HTML templates
✓ requirements.txt               # Python dependencies
✓ requirements-setup.txt         # Setup dependencies
✓ Dockerfile                     # Docker configuration
✓ README.md                      # Project documentation
✓ .gitignore                     # Git ignore rules
✓ DEVICE_TYPES.md               # Documentation
✓ REFACTORING_GUIDE.md          # Refactoring docs (helpful for contributors)
```

### ⚠️ MAYBE KEEP (Utility Scripts)
```bash
# These might be useful for others
app/init_database.py             # Database initialization
app/fix_device_ownership.py      # Utility script
setup_db.py                      # Database setup
check_env_sensors.py             # Sensor check script
scripts/                         # Utility scripts folder
template_endpoints.py            # Template/example code
```

## Files Already in .gitignore

The `.gitignore` file now includes:
- `__pycache__/` and `*.pyc`
- `.venv/` and virtual environments
- `.env` and environment files
- `main_backup.py`
- `refactor_main.py`
- `verify_imports.py`
- Migration scripts
- IDE files (`.vscode/`, `.idea/`)
- Logs and temporary files

## Commands to Clean Up

### Quick Cleanup (Recommended)
```bash
cd C:\Users\Dave\Documents\Programming\Garden\plants_logs_server

# Delete sensitive files
rm .env

# Delete backup and refactoring scripts
rm app/main_backup.py
rm refactor_main.py
rm verify_imports.py

# Delete migration scripts (if you don't need them)
rm run_migration_*.py
rm run_migration_*.bat
rm sync_schema_from_prod.py
rm sync_schema.bat
rm setup_database.bat
rm export_prod_schema.sql
rm add_missing_columns.sql
```

### Conservative Cleanup (Keep More)
```bash
# Just delete the most sensitive/unnecessary
rm .env
rm app/main_backup.py
rm refactor_main.py
rm verify_imports.py
```

## Create .env.example

Before deleting `.env`, create a template:

```bash
# Copy .env to .env.example and remove sensitive values
cp .env .env.example
```

Then edit `.env.example` to have placeholder values:
```
DATABASE_URL=mariadb+mariadbconnector://username:password@host:port/database
SECRET_KEY=your-secret-key-here
SERVER_URL=http://localhost:8000
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

## Final Checklist Before `git push`

- [ ] `.env` file deleted (or at minimum, in `.gitignore`)
- [ ] `.env.example` created with placeholder values
- [ ] `__pycache__/` and `*.pyc` deleted
- [ ] `main_backup.py` deleted
- [ ] `.gitignore` file present and complete
- [ ] README.md updated with refactoring notes
- [ ] Test that app still runs locally
- [ ] Review `git status` to ensure no sensitive files

## What Your GitHub Repo Should Look Like

```
plants_logs_server/
├── .gitignore
├── Dockerfile
├── README.md
├── DEVICE_TYPES.md
├── REFACTORING_GUIDE.md          # Optional but helpful
├── requirements.txt
├── requirements-setup.txt
├── .env.example                  # Template for environment variables
├── app/
│   ├── __init__.py
│   ├── main.py                  # Refactored main file
│   ├── init_database.py
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── auth/
│   └── routers/                 # (empty for now)
├── static/
├── templates/
├── scripts/                     # Optional utility scripts
└── snips/                       # Delete this folder (error logs, etc.)
```

## After Cleanup

Run these commands to verify:
```bash
# Check what files will be committed
git status

# Check that .env is NOT in the list
git status | grep -i "env"

# If .env appears, make sure it's in .gitignore
echo ".env" >> .gitignore
```

## Recommended Git Workflow

```bash
# Initialize git (if not already)
git init

# Add files
git add .

# Review what's being added
git status

# Commit
git commit -m "Refactor: Split 4,000+ line main.py into modular structure

- Created core/, models/, schemas/, auth/ modules
- Separated models, schemas, and configuration
- Improved code organization and maintainability
- Reduced file size for better IDE performance"

# Push to GitHub
git remote add origin https://github.com/yourusername/plants_logs_server.git
git branch -M main
git push -u origin main
```

---

**Summary:** Delete `.env`, `main_backup.py`, and bytecode files. Everything else is safe to commit!
