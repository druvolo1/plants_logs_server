#!/usr/bin/env python3
"""
Database Setup Script with GUI
Creates all necessary tables for the Plant Logs Server
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float, Text
from sqlalchemy.orm import relationship
import time

# Load environment variables
load_dotenv()

Base = declarative_base()

# ============ MODEL DEFINITIONS (copied from main.py) ============

class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    id = Column(Integer, primary_key=True)
    oauth_name = Column(String(255), nullable=False)
    access_token = Column(String(1024), nullable=False)
    expires_at = Column(Integer, nullable=True)
    refresh_token = Column(String(1024), nullable=True)
    account_id = Column(String(255), nullable=False, index=True)
    account_email = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="oauth_accounts")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(1024), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)
    dashboard_preferences = Column(Text, nullable=True)
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")

class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

class LocationShare(Base):
    __tablename__ = "location_shares"
    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    share_code = Column(String(12), unique=True, nullable=False)
    permission_level = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(36), unique=True, index=True)
    api_key = Column(String(64))
    name = Column(String(255), nullable=True)
    system_name = Column(String(255), nullable=True)
    is_online = Column(Boolean, default=False)
    device_type = Column(String(50), nullable=True, default='feeding_system')
    scope = Column(String(20), nullable=True, default='plant')
    capabilities = Column(Text, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    user = relationship("User", back_populates="devices")
    plants = relationship("Plant", foreign_keys="Plant.device_id", cascade="all, delete-orphan", passive_deletes=False)
    device_assignments = relationship("DeviceAssignment", back_populates="device", cascade="all, delete-orphan")

class DeviceShare(Base):
    __tablename__ = "device_shares"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    share_code = Column(String(12), unique=True, nullable=False)
    permission_level = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

class DeviceAssignment(Base):
    __tablename__ = "device_assignments"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    assigned_at = Column(DateTime, nullable=False)
    removed_at = Column(DateTime, nullable=True)

class PhaseHistory(Base):
    __tablename__ = "phase_history"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    phase = Column(String(50), nullable=False)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)

class PhaseTemplate(Base):
    __tablename__ = "phase_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Expected durations for each phase (in days)
    expected_seed_days = Column(Integer, nullable=True)
    expected_clone_days = Column(Integer, nullable=True)
    expected_veg_days = Column(Integer, nullable=True)
    expected_flower_days = Column(Integer, nullable=True)
    expected_drying_days = Column(Integer, nullable=True)
    expected_curing_days = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)

class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    batch_number = Column(String(100), nullable=True)
    system_id = Column(String(255), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    yield_grams = Column(Float, nullable=True)
    display_order = Column(Integer, nullable=True, default=0)

    # Lifecycle fields
    status = Column(String(50), nullable=False, default='feeding')
    current_phase = Column(String(50), nullable=True)
    harvest_date = Column(DateTime, nullable=True)
    cure_start_date = Column(DateTime, nullable=True)
    cure_end_date = Column(DateTime, nullable=True)

    # Expected phase durations (in days) - can override template
    expected_seed_days = Column(Integer, nullable=True)
    expected_clone_days = Column(Integer, nullable=True)
    expected_veg_days = Column(Integer, nullable=True)
    expected_flower_days = Column(Integer, nullable=True)
    expected_drying_days = Column(Integer, nullable=True)
    expected_curing_days = Column(Integer, nullable=True)
    template_id = Column(Integer, ForeignKey("phase_templates.id"), nullable=True)

class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    event_type = Column(String(20), nullable=False)
    sensor_name = Column(String(50), nullable=True)
    value = Column(Float, nullable=True)
    dose_type = Column(String(10), nullable=True)
    dose_amount_ml = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    phase = Column(String(50), nullable=True)

# ============ GUI APPLICATION ============

class DatabaseSetupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Plant Logs Server - Database Setup")
        self.root.geometry("700x600")
        self.root.resizable(True, True)

        # Variables
        self.db_url = tk.StringVar(value=os.getenv("DATABASE_URL", ""))
        self.is_running = False

        self.create_widgets()

    def create_widgets(self):
        # Header
        header = tk.Label(
            self.root,
            text="Database Setup Tool",
            font=("Arial", 16, "bold"),
            bg="#10b981",
            fg="white",
            pady=10
        )
        header.pack(fill=tk.X)

        # Database URL Frame
        url_frame = ttk.LabelFrame(self.root, text="Database Connection", padding=10)
        url_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(url_frame, text="Database URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        url_entry = ttk.Entry(url_frame, textvariable=self.db_url, width=60)
        url_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        url_frame.columnconfigure(1, weight=1)

        # Info Label
        info_text = "This will create all necessary tables in the database.\nExisting tables will not be modified."
        info_label = ttk.Label(url_frame, text=info_text, foreground="gray")
        info_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)

        # Tables Frame
        tables_frame = ttk.LabelFrame(self.root, text="Database Tables", padding=10)
        tables_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create table list
        self.table_list = ttk.Treeview(
            tables_frame,
            columns=("Table", "Status"),
            show="headings",
            height=8
        )
        self.table_list.heading("Table", text="Table Name")
        self.table_list.heading("Status", text="Status")
        self.table_list.column("Table", width=200)
        self.table_list.column("Status", width=400)

        # Add all tables
        tables = [
            "users",
            "oauth_accounts",
            "locations",
            "location_shares",
            "devices",
            "device_shares",
            "device_assignments",
            "phase_templates",
            "plants",
            "phase_history",
            "log_entries"
        ]

        for table in tables:
            self.table_list.insert("", tk.END, values=(table, "Waiting..."))

        self.table_list.pack(fill=tk.BOTH, expand=True)

        # Log Frame
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Buttons Frame
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        self.setup_btn = ttk.Button(
            button_frame,
            text="Setup Database",
            command=self.start_setup,
            style="Accent.TButton"
        )
        self.setup_btn.pack(side=tk.LEFT, padx=5)

        self.check_btn = ttk.Button(
            button_frame,
            text="Check Existing Tables",
            command=self.check_tables
        )
        self.check_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Close",
            command=self.root.quit
        ).pack(side=tk.RIGHT, padx=5)

    def log(self, message, level="INFO"):
        """Add message to log window"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")

        # Color coding
        if level == "ERROR":
            tag = "error"
            self.log_text.tag_config("error", foreground="red")
        elif level == "SUCCESS":
            tag = "success"
            self.log_text.tag_config("success", foreground="green")
        elif level == "WARNING":
            tag = "warning"
            self.log_text.tag_config("warning", foreground="orange")
        else:
            tag = "info"
            self.log_text.tag_config("info", foreground="black")

        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update()

    def update_table_status(self, table_name, status, success=True):
        """Update status of a table in the list"""
        for item in self.table_list.get_children():
            values = self.table_list.item(item, "values")
            if values[0] == table_name:
                self.table_list.item(item, values=(table_name, status))
                if success:
                    self.table_list.item(item, tags=("success",))
                    self.table_list.tag_configure("success", foreground="green")
                else:
                    self.table_list.item(item, tags=("error",))
                    self.table_list.tag_configure("error", foreground="red")
                break
        self.root.update()

    def check_tables(self):
        """Check which tables already exist"""
        db_url = self.db_url.get()
        if not db_url:
            messagebox.showerror("Error", "Please enter a database URL")
            return

        try:
            self.log("Connecting to database...", "INFO")
            # Convert to sync URL
            sync_url = db_url.replace("mariadb+mariadbconnector", "mariadb+pymysql")
            engine = create_engine(sync_url)
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()

            self.log(f"Found {len(existing_tables)} existing tables", "SUCCESS")

            for item in self.table_list.get_children():
                values = self.table_list.item(item, "values")
                table_name = values[0]
                if table_name in existing_tables:
                    self.update_table_status(table_name, "Already exists", True)
                    self.log(f"Table '{table_name}' already exists", "INFO")
                else:
                    self.update_table_status(table_name, "Does not exist", False)

            engine.dispose()

        except Exception as e:
            self.log(f"Error checking tables: {str(e)}", "ERROR")
            messagebox.showerror("Error", f"Failed to check tables:\n{str(e)}")

    def start_setup(self):
        """Start database setup in a thread"""
        if self.is_running:
            messagebox.showwarning("Warning", "Setup is already running")
            return

        db_url = self.db_url.get()
        if not db_url:
            messagebox.showerror("Error", "Please enter a database URL")
            return

        # Confirm
        if not messagebox.askyesno(
            "Confirm Setup",
            "This will create all tables in the database.\nExisting tables will not be modified.\n\nContinue?"
        ):
            return

        self.is_running = True
        self.setup_btn.config(state=tk.DISABLED)
        self.check_btn.config(state=tk.DISABLED)

        # Run in thread to keep GUI responsive
        thread = threading.Thread(target=self.setup_database, daemon=True)
        thread.start()

    def setup_database(self):
        """Actually perform the database setup"""
        db_url = self.db_url.get()

        try:
            self.log("Starting database setup...", "INFO")
            self.log(f"Database: {db_url.split('@')[-1]}", "INFO")

            # Convert to sync URL for setup
            sync_url = db_url.replace("mariadb+mariadbconnector", "mariadb+pymysql")

            self.log("Connecting to database...", "INFO")
            engine = create_engine(sync_url)

            # Test connection
            with engine.connect() as conn:
                self.log("Connection successful!", "SUCCESS")

            # Get existing tables
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()

            # Create tables in dependency order (respecting foreign keys)
            self.log("Creating tables in dependency order...", "INFO")

            # Define table creation order (parent tables first)
            table_order = [
                "users",              # No dependencies
                "locations",          # Depends on users
                "location_shares",    # Depends on locations and users
                "oauth_accounts",     # Depends on users
                "devices",            # Depends on users and locations
                "device_shares",      # Depends on devices and users
                "phase_templates",    # Depends on users
                "plants",             # Depends on devices, users, and locations
                "device_assignments", # Depends on devices and plants
                "phase_history",      # Depends on plants
                "log_entries"         # Depends on plants
            ]

            for table_name in table_order:
                if table_name in existing_tables:
                    self.update_table_status(table_name, "Already exists (skipped)", True)
                    self.log(f"Table '{table_name}' already exists - skipping", "WARNING")
                else:
                    self.update_table_status(table_name, "Creating...", True)
                    self.log(f"Creating table '{table_name}'...", "INFO")
                    table = Base.metadata.tables[table_name]
                    table.create(engine)
                    self.update_table_status(table_name, "Created successfully", True)
                    self.log(f"Table '{table_name}' created successfully", "SUCCESS")
                    time.sleep(0.1)  # Small delay for visual feedback

            engine.dispose()

            self.log("=" * 50, "INFO")
            self.log("Database setup completed successfully!", "SUCCESS")
            self.log("=" * 50, "INFO")

            messagebox.showinfo("Success", "Database setup completed successfully!")

        except Exception as e:
            self.log(f"ERROR: {str(e)}", "ERROR")
            messagebox.showerror("Error", f"Database setup failed:\n{str(e)}")

        finally:
            self.is_running = False
            self.setup_btn.config(state=tk.NORMAL)
            self.check_btn.config(state=tk.NORMAL)

# ============ MAIN ============

def main():
    root = tk.Tk()

    # Set theme
    style = ttk.Style()
    style.theme_use('clam')

    app = DatabaseSetupGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
