"""
Fix missing imports in main.py after refactoring.
Run this on your server: python fix_imports.py
"""

def fix_main_imports():
    """Add missing imports to main.py"""

    with open('app/main.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if SQLAlchemyUserDatabase is imported
    if 'from fastapi_users.db import SQLAlchemyUserDatabase' not in content:
        print("Adding missing fastapi_users imports...")

        # Find the line with "from fastapi_users import"
        lines = content.split('\n')
        new_lines = []

        for i, line in enumerate(lines):
            new_lines.append(line)
            # Add the missing import right after the fastapi_users import
            if 'from fastapi_users import' in line and 'exceptions' in line:
                new_lines.append('from fastapi_users.db import SQLAlchemyUserDatabase')
                print("  Added: from fastapi_users.db import SQLAlchemyUserDatabase")

        content = '\n'.join(new_lines)

        # Write back
        with open('app/main.py', 'w', encoding='utf-8') as f:
            f.write(content)

        print("[OK] Fixed imports in main.py")
    else:
        print("[OK] Imports already correct")

if __name__ == "__main__":
    fix_main_imports()
