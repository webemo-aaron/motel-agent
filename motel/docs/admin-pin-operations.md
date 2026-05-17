# Motel Admin PIN Operations

## Effective PIN precedence
The kiosk admin unlock endpoint (`POST /api/motel/admin/unlock`) accepts PINs in this order:

1. `MOTEL_ADMIN_PIN`
2. `MOTEL_KIOSK_TEST_PIN`
3. fallback default `2468`

## Check the live configured PIN
From repo root:

```bash
motel/scripts/show_admin_pin.sh
```

## Common failure mode
If the PIN is correct but unlock fails in UI, check the API is actually running:

```bash
curl -sS http://127.0.0.1:8653/api/motel/overview
```

If this fails, start full stack:

```bash
cd /home/webemo-aaron/projects
./start-marvin-full.sh
```

## Recommended production setup
Set a non-default value in `webemo-hermes-agent/.env`:

```env
MOTEL_ADMIN_PIN=####
```

Then restart stack.
