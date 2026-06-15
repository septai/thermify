# Cozify Configuration Guide

This document describes the Cozify configuration format stored in AWS SSM Parameter Store and the automatic token refresh mechanism.

## Configuration Format

Cozify configuration is stored as a JSON document in AWS SSM Parameter Store at `/lambda/cozify/config` (or the path specified by `CozifyConfigParameterPath` in the SAM template).

### JSON Schema

```json
{
  "cloud_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "hub_id": "5d3bec53-26e2-56d3-353e-433636d32fde",
  "hub_key": "eyJ0xWDjDkUTYHJnHHEYwbAe...",
  "hub_name": "My hub",
  "hub_host": "192.168.x.x",
  "remote": true,
  "email": "user@example.com",
  "temperature_sensor_id": "88e3deaca-d38d-2b46-13d8-d90da234edbca",
  "last_refresh_timestamp_unix_ms": 1750493571000
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cloud_token` | string | Yes | JWT token for Cozify cloud API authentication. Used for remote hub access. |
| `hub_id` | string | Yes | Unique identifier of the Cozify Hub. |
| `hub_key` | string \| null | No | Hub-specific token for API access. Required for remote access; optional for local LAN access. |
| `hub_name` | string | Yes | Human-readable name of the Hub. |
| `hub_host` | string \| null | No | LAN IP address of Hub. Used for local access; ignored if `remote=true`. |
| `remote` | boolean | Yes | If `true`, use cloud relay for remote hub access. If `false`, use direct LAN access to hub_host. |
| `email` | string | Yes | Email address associated with Cozify account. |
| `temperature_sensor_id` | string | Yes | UUID of the temperature sensor to read for indoor temperature. |
| `last_refresh_timestamp_unix_ms` | integer \| null | No | Unix milliseconds timestamp of the last configuration update. Configuration is valid for 28 days and refreshed every 14 days. |

## Automatic Token Refresh

The Lambda function automatically manages cloud token refresh to keep the Cozify connection alive.
Tokens are kept in memory for the current Lambda execution. Refreshed tokens are persisted back to SSM parameter store by the Cozify client.

### Refresh Trigger

When the Lambda function reads temperature:

1. **Refresh schedule check**: `last_refresh_timestamp_unix_ms` is checked. If at least **14 days** have elapsed (or timestamp is missing), a refresh is triggered.
2. **Refresh flow**: 
   - Call Cozify API `/user/refreshsession` to obtain a new token
   - Update in-memory token for use in subsequent API calls
   - Attempt to logout old token via `/user/logout` (best-effort, non-fatal)
3. **Persistence**: The updated configuration is persisted to SSM Parameter Store. The configuration is written back to SSM with:
  - Updated `cloud_token`
  - Updated `last_refresh_timestamp_unix_ms` (current time)

### Thresholds

- **Configuration validity period**: 28 days from `last_refresh_timestamp_unix_ms`.
- **Configuration refresh interval**: 14 days. Configuration is refreshed before the 28-day validity would expire.

### Example Timeline

- **Day 0**: User manually provisions Cozify config in SSM. `last_refresh_timestamp_unix_ms = null`.
- **Day 5**: Lambda reads temperature. Last refresh age is 5 days. No refresh triggered.
- **Day 15**: Lambda reads temperature. Last refresh age is 15 days. Refresh triggered:
  - New token obtained
  - Config written to SSM with new token and `last_refresh_timestamp_unix_ms = now`
- **Day 25**: Lambda reads temperature. Last refresh age is 10 days. No refresh triggered.
- **Day 30**: Lambda reads temperature. Last refresh age is 15 days. Refresh triggered:
  - New token obtained
  - Config written to SSM with new token and `last_refresh_timestamp_unix_ms = now`

## Bootstrap Onboarding CLI (Recommended)

Use the local interactive bootstrap CLI to generate and store Cozify configuration.

```bash
python scripts/bootstrap_cozify.py \
  --region eu-west-1 \
  --parameter-name /lambda/cozify/config
```

### Bootstrap Workflow

1. Enter your Cozify account email.
2. CLI calls `POST /user/requestlogin?email=...` to trigger one-time login code delivery.
3. Enter OTP/password received by email.
4. CLI calls `POST /user/emaillogin` and receives cloud token (raw text).
5. CLI fetches hub keys from `GET /user/hubkeys` and lets you choose a hub.
6. CLI reads hub metadata from `GET /hub/remote/hub`, derives API version (`major.minor`), and fetches devices.
7. CLI filters temperature sensors where:
   - `capabilities.values` contains `TEMPERATURE`
   - `state.temperature` is numeric
8. Select the temperature sensor by index or id.
9. CLI writes finalized configuration JSON to SSM as `SecureString`.

### OTP Handling Notes

- OTP/password is only requested in the local bootstrap process.
- OTP/password is never stored in configuration.
- Lambda runtime stays non-interactive and only reads ready-made SSM JSON config.

### Dry Run

To validate login and selection flow without writing SSM:

```bash
python scripts/bootstrap_cozify.py --dry-run --region eu-west-1
```

## Manual Configuration Setup

To set up Cozify configuration manually:

1. **Obtain credentials** from Cozify (or use bootstrap CLI above):
   - Cloud token (via Cozify account login)
   - Hub ID and Hub Key
   - Hub LAN IP address (if using local access)

2. **Determine temperature sensor ID**:
   - Log into Cozify Hub and identify the sensor UUID

3. **Create JSON configuration**:
   ```json
   {
     "cloud_token": "YOUR_CLOUD_TOKEN_HERE",
     "hub_id": "YOUR_HUB_ID_HERE",
     "hub_key": "YOUR_HUB_KEY_HERE",
     "hub_name": "Your Hub Name",
     "hub_host": "192.168.x.x",
     "remote": true,
     "email": "your.email@example.com",
     "temperature_sensor_id": "YOUR_SENSOR_UUID_HERE",
     "last_refresh_timestamp_unix_ms": null
   }
   ```

4. **Store in AWS SSM Parameter Store**:
   ```bash
   aws ssm put-parameter \
     --name /lambda/cozify/config \
     --value '{"cloud_token": "...", ...}' \
     --type SecureString \
     --overwrite \
     --region eu-west-1
   ```

5. **Deploy Lambda**: The next invocation will use the updated configuration.

## Troubleshooting

### Cozify unavailable in logs

If logs show `fallback_reason=cozify_unavailable`:

1. Verify configuration is valid JSON in SSM Parameter Store
2. Check that `last_refresh_timestamp_unix_ms` is kept up to date by refresh cycles (target interval: 14 days)
3. Verify network connectivity to Cozify API (api.cozify.fi)
4. Check Lambda logs for detailed error messages

### Token refresh failures

Token refresh failures (401/403 responses) are logged but do not interrupt operation. The in-memory token remains valid for the current execution. The next Lambda invocation will retry the refresh.

### SSM write failures

SSM Parameter Store write failures (e.g., permission denied, quota exceeded) are logged as warnings but do not interrupt operation. The function continues using in-memory token. The next refresh cycle will retry the write.

## IAM Permissions

The Lambda function requires the following SSM permissions:

```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:GetParameter"
  ],
  "Resource": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/lambda/cozify/config"
}
```

- `ssm:GetParameter`: Read configuration at Lambda startup
- `ssm:PutParameter`: Write updated tokens after refresh (if ≥14 days have passed)
