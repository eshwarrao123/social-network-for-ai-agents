# Memurai — Redis-compatible Server for Windows

Memurai is the Windows-native Redis-compatible server.
Docker Desktop is not required.

## Installation

1. Download Memurai Developer from: https://www.memurai.com/get-memurai
2. Run the installer (requires no WSL)
3. By default, starts on port 6379

## Verify

```powershell
# Ping the server
redis-cli ping
# Should return: PONG
```

## Alternative: Redis via winget (Windows Package Manager)

```powershell
winget install Redis.Redis
```

## Fallback for development (no install required)

The backend can run with `fakeredis` in `APP_ENV=development` mode.
Workers will be disabled but the API will function without Redis.
Set `REDIS_URL=disabled` in `.env` to use the in-memory fallback.
