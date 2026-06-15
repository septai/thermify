# Technical Description

## Architecture

The implementation uses a clean structure:

- `domain`: business rules for deciding how much to heat and when to heat
- `application`: orchestration services with fallback handling
- `adapters`: external integrations (Thermia API, S3, Cozify, SSM parameter retrieval)
- `config`: environment parsing and validation
- `handler_optimizer`: optimizer Lambda entrypoint
- `handler_ingestor`: price ingestor Lambda entrypoint

## Execution Sequence

Optimizer Lambda:

1. Lambda handler loads environment settings.
2. Parameter adapter reads Thermia credentials and Cozify config from SSM SecureString.
3. Thermia adapter authenticates with Thermia Online API.
4. First heat pump is selected (`heat_pumps[0]`).
5. S3 adapter reads `latest-prices.json` and selects the current quarter-hour price slot.
6. Cozify adapter reads indoor temperature; Thermia adapter reads outdoor temperature.
7. Domain logic computes `Tset` using the price/temperature adjustments and clamps to `[Tmin, Tmax]`.
8. Application layer calls domain logic to decide whether the current slot should heat or stay idle.
9. Thermia adapter updates target temperature, heating curve, and operation mode.
10. Heating history and legionella boost timestamps are persisted to S3.
11. Handler returns structured response.

If S3 price data is missing/invalid or Cozify is unavailable, service fallback sets `Tset = Tnom`and still applies target temperature through Thermia. When price data is missing, the optimizer attempts to invoke the ingestor Lambda asynchronously to refresh S3 data.


Price ingestor Lambda:

1. Lambda handler loads environment settings.
2. Price client fetches the latest quarter-hour price payload.
3. S3 adapter writes the normalized payload to `latest-prices.json`.
4. Handler returns structured response.



## Parameter Retrieval

Parameter retrieval uses boto3 directly:

1. `ssm.get_parameter(..., WithDecryption=True)`


## Environment Variables

All Lambda environment variables are loaded at function startup via the settings dataclasses in `src/config/settings.py`. Configuration includes:

- Temperature control parameters: `NominalTargetTemperature`, `MinTargetTemperature`, `MaxTargetTemperature`, `IdleTargetTemperature`
- Heat pump control: `MinRun` (minimum consecutive 15-minute time slots for continuous operation), `MinIdle` (minimum consecutive 15-minute time slots for forced idle)
- Price-based adjustment gains: `PriceGain`, `ReferencePrice`, `HappyPriceBias` (bias factor for low-price period)
- Temperature-based adjustment gains: `IndoorTemperatureGain`, `LowTemperatureProtectionMargin`, `LowTemperatureBoost`
- Heating parameters: `DefaultHeatingCurve`, `ShutdownOutdoorTemperatureLimit`, `ShutdownSupplyLineTemperatureLimit`, `LegionellaDisinfectionTemperature`
- S3 parameters: `S3BucketPrefix`, `S3PriceKey`, `S3HeatingHistoryKey`, `S3LegionellaBoostKey`
- Runtime settings: `Timezone`, `LogLevel`, `ThermiaDemoMode`
- Ingestor settings: `PowerPriceApiUrl`, `S3Bucket`, `S3PriceKey`

See `docs/configuration.md` for full parameter documentation.

## IAM Model

Optimizer Lambda IAM policy allows only:

- `ssm:GetParameter` for configured username parameter path
- `ssm:GetParameter` for configured password parameter path
- `ssm:GetParameter` for configured Cozify config parameter path
- `s3:GetObject` for the configured account-regional `latest-prices.json` object
- `s3:GetObject` for heating history and legionella boost timestamp objects
- `s3:PutObject` for heating history and legionella boost timestamp objects

Price ingestor Lambda IAM policy allows:

- `s3:PutObject` for the configured account-regional `latest-prices.json` object


## Error Handling

- S3 read/validation failure triggers fallback (`Tset = Tnom`) and increments `ApplicationErrorCount`.
- Cozify authentication/data failure triggers fallback (`Tset = Tnom`) and increments `ApplicationErrorCount`.
- Thermia authentication/selection/write failures return `500` and increment `ApplicationErrorCount`.
- SSM credential retrieval failures return `500` and increment `ApplicationErrorCount`.
- Failure reason is logged in the Lambda logs; it is not emitted as a metric dimension.
- HTTP Responses from lambda include request id field, so you can match the response to a specific CloudWatch log entry.

- The remaining alarm watches the shared error metric (2 of 3 periods, 15-minute periods, threshold >= 1):
	- `ApplicationErrorAlarm`
- Alarms publish to the SNS topic: `thermia-optimize-heating-alarms-<account-id>` (resource: `OptimizeHeatingAlarmTopic`).
- Subscribe to the SNS topic (example, email):
	- `aws sns subscribe --topic-arn <topic-arn> --protocol email --notification-endpoint you@example.com`
- Metrics emitted:
	- `ApplicationErrorCount`
