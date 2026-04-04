# DataCenter Asset Tracker (DAT)

A hardware lifecycle management API that tracks datacenter assets from arrival to disposal, with automated validation checks.

## Architecture

```
POST /assets (register hardware)
        ↓
  Asset: Pending
        ↓
POST /assets/{id}/status → Validating
        ↓
  Hangfire background job
  ├── Ping check (device reachable?)
  ├── Firmware check (approved version?)
  └── Duplicate check (serial/MAC unique?)
        ↓
  Pass → Approved → Deployed → Retired
  Fail → Pending (re-validate after fix)
        ↓
  All transitions logged to AuditLog
```

## Stack

- **C# / ASP.NET Core 8** — REST API
- **Entity Framework Core** — ORM
- **PostgreSQL** — asset store and audit log
- **Hangfire** — async background validation jobs
- **Docker + Azure Container Apps** — deployment
- **GitHub Actions** — CI/CD

## Quick Start (local)

```bash
# 1. Clone and start services
docker compose up -d

# 2. API available at
http://localhost:8080

# 3. Swagger docs
http://localhost:8080/swagger

# 4. Hangfire dashboard
http://localhost:8080/hangfire
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness check |
| POST | `/api/assets` | Register a new asset |
| GET | `/api/assets` | List assets (filter by status, type, location) |
| GET | `/api/assets/{id}` | Get asset with audit log and validation results |
| PATCH | `/api/assets/{id}` | Update asset metadata |
| POST | `/api/assets/{id}/status` | Transition lifecycle status |
| DELETE | `/api/assets/{id}` | Retire and remove an asset |

## Lifecycle States

```
Pending → Validating → Approved → Deployed → Retired
                ↓
             Pending (on validation failure)
```

Invalid transitions are rejected with a 400 response.

## Validation Checks

When an asset transitions to `Validating`, three checks run automatically:

- **PingCheck** — verifies the device is reachable at its registered IP
- **FirmwareCheck** — compares firmware version against a configurable approved list per asset type
- **DuplicateCheck** — ensures serial number and MAC address are unique in the catalog

Configure approved firmware versions in `appsettings.json`:

```json
{
  "ApprovedFirmware": {
    "Server": ["2.1.0", "2.2.0"],
    "NetworkInterface": ["4.5.2", "4.5.3"]
  }
}
```

## Azure Deployment

Set the following GitHub Actions secrets:

| Secret | Description |
|--------|-------------|
| `AZURE_CREDENTIALS` | Service principal JSON |
| `AZURE_RESOURCE_GROUP` | Resource group name |
| `ACR_LOGIN_SERVER` | Azure Container Registry URL |
| `ACR_USERNAME` | ACR username |
| `ACR_PASSWORD` | ACR password |

On merge to `main`, GitHub Actions will build, push, and deploy automatically.
