# Device Types System Documentation

## Overview

The plants_logs_server now supports multiple device types with automatic schema migration. The system is designed to be flexible and extensible for future device types.

## Device Types

### 1. **Feeding System** (`feeding_system`)
- **Scope**: `plant` (1-to-1 assignment)
- **Purpose**: pH dosing systems, nutrient management
- **Typical Sensors**: pH, EC, water temperature, PPM
- **Typical Events**: Dosing events (up/down), sensor readings
- **Controls**: Pump relays for pH up/down dosing

**Example Devices:**
- pH Dosing System (existing in `/ph_dosing_system`)

### 2. **Environmental Sensor** (`environmental`)
- **Scope**: `room` (1-to-many assignment)
- **Purpose**: Monitor grow room environment
- **Typical Sensors**: Temperature, Humidity, CO2, VPD, Lux, PPFD, Pressure, Altitude
- **Typical Events**: Sensor readings only (no control events)
- **Controls**: Read-only (no controls)

**Example Devices:**
- Environment Sensor (existing in `/Environment Sensor`)

### 3. **Valve Controller** (`valve_controller`)
- **Scope**: Configurable (`plant` or `room`)
- **Purpose**: Control water valves for irrigation
- **Typical Sensors**: Valve states (open/closed), flow rates
- **Typical Events**: Valve open/close events, watering duration
- **Controls**: Valve relays

**Example Devices:**
- Valve relay box (in development)

### 4. **Other** (`other`)
- **Scope**: Configurable
- **Purpose**: Future device types
- **Sensors/Events**: Flexible

---

## Database Schema

### New Fields in `devices` Table

The `init_database.py` script automatically adds these fields on application startup:

```sql
-- Device type categorization
device_type VARCHAR(50) DEFAULT 'feeding_system'
  -- Values: 'feeding_system', 'environmental', 'valve_controller', 'other'

-- Assignment scope (plant-level or room-level)
scope VARCHAR(20) DEFAULT 'plant'
  -- Values: 'plant' (1-to-1), 'room' (1-to-many)

-- Device capabilities (JSON string)
capabilities TEXT NULL
  -- Example: {"sensors": ["temp", "humidity", "co2"], "controls": ["fan", "light"]}

-- Last connection timestamp
last_seen DATETIME NULL
  -- Updated on WebSocket connect/disconnect
```

### Migration Strategy

**Automatic Migration on Startup:**
1. Application boots
2. `init_database.py` runs automatically
3. Checks if columns exist
4. Adds missing columns with default values
5. Existing data is preserved

**No Manual Migration Needed:**
- Dev → Production: Just deploy the code
- Columns are added automatically
- Existing devices get default values
- No downtime required

---

## API Changes

### Device Registration

**Endpoint:** `POST /user/devices`

**New Request Body:**
```json
{
  "device_id": "abc123",
  "name": "My Device",
  "device_type": "environmental",  // NEW: Optional, defaults to 'feeding_system'
  "scope": "room"                   // NEW: Optional, auto-set based on device_type
}
```

**Automatic Scope Assignment:**
- `environmental` → defaults to `scope: 'room'`
- All other types → defaults to `scope: 'plant'`
- Can be explicitly overridden in request

### Device List

**Endpoint:** `GET /user/devices`

**New Response Fields:**
```json
{
  "device_id": "abc123",
  "name": "My Device",
  "system_name": "HerbNerdz Env Sensor",
  "is_online": true,
  "device_type": "environmental",     // NEW
  "scope": "room",                    // NEW
  "capabilities": "{...}",            // NEW
  "last_seen": "2025-01-15T10:30:00", // NEW
  "assigned_plants": [...],
  ...
}
```

---

## Device Assignment Patterns

### Plant-Level Devices (scope: 'plant')

**1-to-1 Assignment:**
- One device monitors ONE plant at a time
- Used for: Feeding systems, dedicated monitors
- Assignment via `device_assignments` table

**Example:**
```
Device: "Main Dosing System" (feeding_system)
  └─ Assigned to: Plant "Northern Lights #1"
```

### Room-Level Devices (scope: 'room')

**1-to-Many Assignment:**
- One device monitors MULTIPLE plants simultaneously
- All assigned plants share the same sensor readings
- Used for: Environmental sensors

**Example:**
```
Device: "Flower Room Sensor" (environmental)
  ├─ Assigned to: Plant "Northern Lights #1"
  ├─ Assigned to: Plant "Blue Dream #2"
  └─ Assigned to: Plant "OG Kush #3"

All three plants will show the same temp/humidity/CO2 readings
```

---

## Data Logging

### Log Entry Schema (Unchanged)

The flexible `log_entries` table handles all device types:

```python
class LogEntry:
    event_type: str       # 'sensor' or 'dosing' or 'valve' or custom
    sensor_name: str      # 'ph', 'temp', 'humidity', 'valve_1', etc.
    value: float          # Sensor reading
    dose_type: str        # 'up', 'down' (for dosing events)
    dose_amount_ml: float # Amount (for dosing events)
    timestamp: datetime
    phase: str            # Plant lifecycle phase
```

### Example Log Entries by Device Type

**Feeding System:**
```python
# pH sensor reading
{"event_type": "sensor", "sensor_name": "ph", "value": 6.2}

# Dosing event
{"event_type": "dosing", "sensor_name": "ph", "value": 6.1,
 "dose_type": "up", "dose_amount_ml": 5.0}
```

**Environmental Sensor:**
```python
# Temperature
{"event_type": "sensor", "sensor_name": "temperature", "value": 72.5}

# Humidity
{"event_type": "sensor", "sensor_name": "humidity", "value": 65.0}

# CO2
{"event_type": "sensor", "sensor_name": "co2", "value": 800}
```

**Valve Controller:**
```python
# Valve opened
{"event_type": "valve", "sensor_name": "valve_1", "value": 1}  # 1 = open

# Valve closed
{"event_type": "valve", "sensor_name": "valve_1", "value": 0}  # 0 = closed
```

---

## WebSocket Protocol

### Device Connection

Devices connect via: `wss://server/ws/devices/{device_id}?api_key={api_key}`

**New Behavior:**
- On connect: `is_online = True`, `last_seen` updated
- On disconnect: `is_online = False`, `last_seen` updated

### Status Updates

Devices should send periodic status updates with capabilities:

```json
{
  "type": "full_sync",
  "data": {
    "settings": {
      "system_name": "HerbNerdz Env Sensor",
      "sensors": {
        "temperature": {"enabled": true, "value": 72.5},
        "humidity": {"enabled": true, "value": 65.0},
        "co2": {"enabled": true, "value": 800}
      }
    }
  }
}
```

The server automatically extracts and stores `system_name`.

---

## Frontend Integration

### Dashboard Rendering

The dashboard should render device cards based on `device_type`:

**Feeding System Card:**
```javascript
if (device.device_type === 'feeding_system') {
  // Show pH/EC values
  // Show dosing controls
  // Show pump status
}
```

**Environmental Sensor Card:**
```javascript
if (device.device_type === 'environmental') {
  // Show temp/humidity/CO2
  // Show VPD calculation
  // No controls (read-only)
}
```

**Valve Controller Card:**
```javascript
if (device.device_type === 'valve_controller') {
  // Show valve states
  // Show valve toggle controls
  // Show watering schedule
}
```

### Plant Details Page

Charts are generated dynamically based on `sensor_name` values:

```javascript
// Automatically creates charts for any sensor type
const sensorsByName = {
  'ph': [...],
  'temperature': [...],
  'humidity': [...],
  'co2': [...]
};

// Group by device type for better organization
const feedingData = getSensorsByDeviceType('feeding_system');
const environmentalData = getSensorsByDeviceType('environmental');
```

---

## Implementation Checklist

### Backend (Completed ✓)
- [x] Add new fields to Device model
- [x] Update init_database.py for auto-migration
- [x] Update DeviceCreate Pydantic model
- [x] Update DeviceRead Pydantic model
- [x] Update device registration endpoint
- [x] Update device list endpoint
- [x] Update WebSocket last_seen tracking

### Frontend (TODO)
- [ ] Update device registration UI to include device_type selector
- [ ] Create device-type-specific dashboard cards
- [ ] Update plant details page with grouped charts
- [ ] Add device capabilities display
- [ ] Show last_seen timestamp in device list

### Device Integration (TODO)
- [ ] Update Environment Sensor to connect to server
- [ ] Implement Valve Controller device
- [ ] Add capability reporting to all devices

---

## Adding a New Device Type

To add a new device type in the future:

1. **No database changes needed** - just use the existing fields
2. **Add to device_type enum** (documentation only, not enforced)
3. **Decide on default scope** (plant vs room)
4. **Create frontend card template** for the new type
5. **Document expected sensor_name values** for charting

Example for a "Lighting Controller":

```python
# Registration
{
  "device_id": "light-001",
  "name": "Flower Room Lights",
  "device_type": "lighting_controller",
  "scope": "room"  # One light system for whole room
}

# Log entries
{"event_type": "sensor", "sensor_name": "light_level", "value": 800}
{"event_type": "control", "sensor_name": "light_power", "value": 1}  # ON
```

---

## Testing the Migration

### Test 1: Fresh Install
```bash
# Start with empty database
python app/main.py

# Expected: All tables created with new columns
# Check: devices table has device_type, scope, capabilities, last_seen
```

### Test 2: Existing Database (Dev)
```bash
# Use existing dev database with old schema
python app/main.py

# Expected: New columns added automatically
# Check: Existing devices have default values (device_type='feeding_system', scope='plant')
```

### Test 3: Production Deployment
```bash
# Deploy to production
# Application starts
# init_database.py runs
# Columns added if missing
# Zero downtime

# Verify:
SELECT device_type, scope, capabilities, last_seen
FROM devices
LIMIT 5;
```

---

## Backward Compatibility

All changes are backward compatible:

✓ Existing devices work without modification
✓ API accepts requests without new fields
✓ Default values applied automatically
✓ Frontend can ignore new fields initially
✓ Old pH dosing systems continue working

---

## Questions & Answers

**Q: Do devices need to know their type?**
A: No. Device type is server-side only. Devices just report data and the server categorizes them.

**Q: Can I change a device's type after registration?**
A: Yes, but there's no UI for it yet. Could add a `PATCH /user/devices/{device_id}` endpoint if needed.

**Q: How are capabilities discovered?**
A: Devices should report capabilities in WebSocket status updates. Server can optionally parse and store them in the `capabilities` JSON field.

**Q: Can a room-level device be assigned to just one plant?**
A: Yes. `scope` is just a default/hint. Assignment is flexible via the `device_assignments` table.

**Q: What if I add a new sensor type?**
A: Just start logging it with a new `sensor_name`. The frontend will automatically create a chart for it (current behavior).

---

## Next Steps

1. **Test the migration** on dev database
2. **Update frontend** device registration UI
3. **Implement Environmental Sensor** integration
4. **Implement Valve Controller** device
5. **Add device-type-specific** dashboard cards
6. **Create grouped chart** sections on plant details page

---

## File Locations

- **Database Models**: `app/main.py` (lines 81-96)
- **Migration Script**: `app/init_database.py` (lines 177-201)
- **Device Registration**: `app/main.py` (lines 1246-1275)
- **Device List**: `app/main.py` (lines 1277-1383)
- **WebSocket Handler**: `app/main.py` (lines 2858-2938)
