#!/usr/bin/env python3
"""
Sync Database Schema from Production
Connects to production database, extracts schema, and updates setup_db.py
"""
import os
import re
from dotenv import load_dotenv
import pymysql

# Load production database URL
load_dotenv()

def connect_to_db():
    """Connect to production database"""
    # Parse DATABASE_URL
    db_url = os.getenv("PROD_DATABASE_URL") or "mariadb+mariadbconnector://app_user:testpass123@172.16.1.150:3306/plant_logs"

    # Extract connection details
    # Format: mariadb+mariadbconnector://user:pass@host:port/database
    pattern = r'.*://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)'
    match = re.match(pattern, db_url)

    if not match:
        raise ValueError(f"Could not parse DATABASE_URL: {db_url}")

    user, password, host, port, database = match.groups()

    print(f"Connecting to {host}:{port}/{database}...")

    connection = pymysql.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database
    )

    return connection

def get_table_schema(connection, table_name):
    """Get CREATE TABLE statement for a table"""
    with connection.cursor() as cursor:
        cursor.execute(f"SHOW CREATE TABLE {table_name}")
        result = cursor.fetchone()
        return result[1] if result else None

def parse_column_definition(column_def):
    """Parse a column definition from CREATE TABLE statement"""
    # Example: `id` int(11) NOT NULL AUTO_INCREMENT
    # Example: `email` varchar(255) DEFAULT NULL
    # Example: `is_active` tinyint(1) NOT NULL DEFAULT '0'

    parts = column_def.strip().split()
    if len(parts) < 2:
        return None

    col_name = parts[0].strip('`')
    col_type = parts[1].upper()

    # Convert MySQL types to SQLAlchemy types
    type_mapping = {
        'INT': 'Integer',
        'TINYINT(1)': 'Boolean',
        'VARCHAR': 'String',
        'TEXT': 'Text',
        'DATETIME': 'DateTime',
        'FLOAT': 'Float',
        'DOUBLE': 'Float',
    }

    # Handle varchar length
    if 'VARCHAR' in col_type:
        length_match = re.search(r'VARCHAR\((\d+)\)', col_type)
        if length_match:
            sa_type = f"String({length_match.group(1)})"
        else:
            sa_type = "String(255)"
    else:
        sa_type = type_mapping.get(col_type.split('(')[0], col_type)

    # Check for NULL/NOT NULL
    nullable = 'NULL' if 'NOT NULL' not in column_def else 'NOT NULL'

    # Check for DEFAULT
    default = None
    if 'DEFAULT' in column_def:
        default_match = re.search(r"DEFAULT '?([^']+)'?", column_def)
        if default_match:
            default = default_match.group(1)

    # Check for AUTO_INCREMENT
    auto_increment = 'AUTO_INCREMENT' in column_def

    # Check for PRIMARY KEY
    primary_key = 'PRIMARY KEY' in column_def

    return {
        'name': col_name,
        'type': sa_type,
        'nullable': nullable == 'NULL',
        'default': default,
        'auto_increment': auto_increment,
        'primary_key': primary_key
    }

def generate_sqlalchemy_model(table_name, create_statement):
    """Generate SQLAlchemy model from CREATE TABLE statement"""
    lines = create_statement.split('\n')

    # Find column definitions (lines that start with backtick and are not KEY definitions)
    columns = []
    foreign_keys = []

    for line in lines[1:]:  # Skip first line (CREATE TABLE)
        line = line.strip()
        if line.startswith('`') and not line.startswith('KEY') and not line.startswith('PRIMARY'):
            # Remove trailing comma
            col_def = line.rstrip(',')

            # Check for foreign key
            if 'FOREIGN KEY' in line:
                continue

            parsed = parse_column_definition(col_def)
            if parsed:
                columns.append(parsed)
        elif 'FOREIGN KEY' in line or 'CONSTRAINT' in line:
            # Extract foreign key info
            fk_match = re.search(r'FOREIGN KEY \(`([^`]+)`\) REFERENCES `([^`]+)`', line)
            if fk_match:
                foreign_keys.append({
                    'column': fk_match.group(1),
                    'references': fk_match.group(2)
                })

    # Generate class
    class_name = ''.join(word.capitalize() for word in table_name.split('_'))

    model_lines = [
        f"class {class_name}(Base):",
        f'    __tablename__ = "{table_name}"'
    ]

    for col in columns:
        col_parts = []

        # Column type
        col_type = col['type']

        # Build column definition
        col_args = []

        if col['primary_key'] or col['auto_increment']:
            col_args.append('primary_key=True')

        if not col['nullable'] and not col['primary_key']:
            col_args.append('nullable=False')
        elif col['nullable'] and not col['primary_key']:
            col_args.append('nullable=True')

        if col['default'] and col['default'] != 'NULL':
            if col['type'] == 'Boolean':
                col_args.append(f"default={col['default'] == '1'}")
            elif col['default'] in ['CURRENT_TIMESTAMP', 'datetime.utcnow']:
                col_args.append('default=datetime.utcnow')
            else:
                col_args.append(f"default='{col['default']}'")

        # Check if it's a foreign key
        fk_ref = next((fk for fk in foreign_keys if fk['column'] == col['name']), None)
        if fk_ref:
            col_args.insert(0, f'ForeignKey("{fk_ref["references"]}.id")')

        # Add index for common patterns
        if col['name'] in ['email', 'device_id', 'plant_id', 'share_code']:
            if 'unique' in col.get('extra', '').lower():
                col_args.append('unique=True')
                col_args.append('index=True')
            elif col['name'] != 'id':
                col_args.append('index=True')

        args_str = ', '.join(col_args) if col_args else ''

        model_lines.append(f"    {col['name']} = Column({col_type}, {args_str})")

    return '\n'.join(model_lines)

def main():
    print("="*80)
    print("SYNCING SCHEMA FROM PRODUCTION DATABASE")
    print("="*80)
    print()

    try:
        connection = connect_to_db()
        print("✓ Connected to production database\n")

        # Get all tables
        tables = [
            'users',
            'oauth_accounts',
            'devices',
            'device_shares',
            'device_assignments',
            'plants',
            'phase_history',
            'log_entries'
        ]

        print("Extracting schema from production database...\n")

        for table in tables:
            print(f"Table: {table}")
            create_stmt = get_table_schema(connection, table)
            if create_stmt:
                print(f"  ✓ Schema extracted")
                print(f"\n{create_stmt}\n")
                print("-" * 80)
            else:
                print(f"  ✗ Could not extract schema")

        connection.close()
        print("\n✓ Schema extraction complete!")
        print("\nNOTE: Review the output above and manually update setup_db.py")
        print("      The column parsing is complex, so manual review is recommended.")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
