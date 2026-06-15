# Usage Guide

## Purpose

This project uses two Lambdas:

- **Price ingestor Lambda**: runs daily and fetches quarter-hour electricity prices from a power price API and stores them in S3.
- **Optimizer Lambda**: runs every 15 minutes and applies Thermia heating control based on prices and temperature.

The optimizer Lambda:

- Reads current quarter-hour electricity price from S3
- Reads indoor temperature from Cozify IoT sensor
- Computes a target temperature
- Decides whether the current slot should heat or stay idle
- Sends target temperature and heating curve updates to Thermia heat pump

If price or Cozify data is unavailable, the optimizer falls back to nominal target temperature.

If price data is missing, the optimizer also triggers the ingestor Lambda asynchronously in order to refresh the price data in S3.

## Cozify Bootstrap Prerequisite

Before enabling schedule-based Lambda execution, run local Cozify bootstrap onboarding once to populate SSM configuration:

```bash
python scripts/bootstrap_cozify.py \
  --region eu-west-1 \
  --parameter-name /lambda/cozify/config
```

Bootstrap handles OTP login, hub selection, and temperature sensor selection interactively. Lambda runtime reads only the stored config.

## Configuration

All Lambda environment variables are injected from `samconfig.toml` `parameter_overrides` and are automatically wired to the SAM template as environment variables. Do not set these manually; edit `samconfig.toml` instead.

### Lambda Environment Variables (Injected from samconfig.toml)

**Price Ingestor**:
- `POWER_PRICE_API_URL`: HTTP API endpoint to fetch quarter-hour electricity prices
- `S3_BUCKET`: account-regional S3 bucket containing JSON objects
- `S3_PRICE_KEY`: S3 key for price JSON object
- `AWS_REGION`: AWS region (auto-set by Lambda, defined in template.yaml)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL; default: INFO)

**SSM Parameter Paths** (secrets stored in AWS Systems Manager Parameter Store):
- `THERMIA_USERNAME_PARAMETER`: SSM SecureString path for Thermia username
- `THERMIA_PASSWORD_PARAMETER`: SSM SecureString path for Thermia password
- `COZIFY_CONFIG_PARAMETER`: SSM SecureString path for Cozify config JSON

**S3 Configuration** (electricity price and heating history data):
- `S3_BUCKET`: account-regional S3 bucket containing JSON objects
- `S3_PRICE_KEY`: S3 key for price JSON object
- `S3_HEATING_HISTORY_KEY`: S3 key for history JSON object
- `S3_LEGIONELLA_BOOST_KEY`: S3 key for the latest legionella boost timestamp JSON object

**Temperature Control Parameters**:
- `NOMINAL_INDOOR_TEMPERATURE`: Nominal indoor temperature reference (desired indoor temperature)
- `NOMINAL_TARGET_TEMPERATURE`: Nominal heating target (applied as a fallback in cases where temperature optimization is not possible)
- `MIN_TARGET_TEMPERATURE`: Lowest limit for the heat pump target.
- `MAX_TARGET_TEMPERATURE`: Highest limit for the heat pump target
- `REFERENCE_PRICE`: Reference electricity price in snt/kWh (average electrity price over time)
- `LOW_TEMPERATURE_PROTECTION_MARGIN`: Maximum allowed drop below the nominal indoor temperature before low temperature protection logic activates. When indoor temperature falls more than this amount below nominal, the controller:
- applies an additional low-temperature boost, and
- prevents the target temperature from being lowered further.
Typical values are 0.5–3.0 °C (start experimenting around 1.5 °C).
- `PRICE_GAIN`: Gain applied to normalized price adjustment (default 1.2, suggested range from 1.0 to 1.5). Encourages lower target when price is above reference price and higher target when price is below reference price.
- `INDOOR_TEMPERATURE_GAIN`: Gain applied when indoor temperature is below nominal (default 1.5, suggested range from 1.0 to 2.5). Encourages higher target if indoor temp is below nominal.
- `LOW_TEMPERATURE_BOOST`: Extra gain applied under low-temperature comfort conditions (default 3.0, suggested range from 2.0 to 4.0). Encourages higher target if indoor temp is significantly below nominal to protect the heated space and ensure comfort.

**Scheduling and Idle Control**:
- `IDLE_TARGET_TEMPERATURE`: Target temperature when heating is idle
- `DEFAULT_HEATING_CURVE`: Base heating curve for the heat pump
- `MIN_RUN`: Minimum consecutive 15-minute time slots for continuous operation
- `MIN_IDLE`: Minimum consecutive 15-minute time slots the heat pump must stay off before restarting
- `HAPPY_PRICE_BIAS`: Bias factor for extra heating during low-price periods (default 0.0, suggested range from 0.0 to 2.0)
- `TIMEZONE`: IANA timezone used for schedule logging

**Heat Pump Safety Limits**:
- `SHUTDOWN_OUTDOOR_TEMPERATURE_LIMIT`: Outdoor temperature threshold below which heating is not shut down
- `SHUTDOWN_SUPPLY_LINE_TEMPERATURE_LIMIT`: Supply line temperature threshold used in shutdown checks

**Summer Mode**:
- `SUMMER_MODE_AVERAGE_TEMPERATURE_THRESHOLD`: 24-hour average outdoor temperature threshold for treating conditions as summer mode
- `SUMMER_MODE_MINIMUM_TEMPERATURE_THRESHOLD`: 24-hour minimum outdoor temperature threshold for treating conditions as summer mode

**Legionella Prevention**:
- `LEGIONELLA_DISINFECTION_TEMPERATURE`: A hot water temperature higher than this threshold in °C (default: 61) suggests that the legionella boost has been activated. Legionella boost prevents legionella bacteria growth by ensuring adequate hot water temperature.

**Runtime Configuration**:
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL; default: INFO)
- `THERMIA_DEMO_MODE`: Demo mode flag (true/false): no real changes are made to the heat pump settings when in demo mode.
- `AWS_REGION`: AWS region (SAM deployment region, defined in samconfig.toml)

**Cozify Sensor**:
- `temperature_sensor_id` is read from the Systems Manager parameter specified by `COZIFY_CONFIG_PARAMETER`

### Parameter Values (Single Source of Truth)

Edit `samconfig.toml` under `[default.deploy.parameters]` and `[default.local_invoke.parameters]` sections to customize values.

Also see: Temperature Control Tuning


## Deploy

```bash
sam build
sam deploy --guided
```

Deployed function names:

- thermia-optimize-heating
- ingest-spot-prices

## Invoke From AWS CLI

```bash
aws lambda invoke \
  --function-name thermia-optimize-heating \
  --payload '{}' \
  response.json
cat response.json
```

Invoke the price ingestor Lambda:

```bash
aws lambda invoke \
  --function-name ingest-spot-prices \
  --payload '{}' \
  response.json
cat response.json
```

## Local Invocation

Use the current SAM logical id:

```bash
sam local invoke OptimizeHeatingFunction
```

Invoke the ingestor Lambda locally:

```bash
sam local invoke IngestSpotPricesFunction
```

Local invocation uses parameter values from `samconfig.toml`
`[default.local_invoke.parameters]`.

## Temperature Control Tuning

Use the interactive Streamlit tuner to explore different `TemperatureControlConstants` values against electricity prices and indoor temperatures in real-time:

```bash
streamlit run scripts/tune_temperature_control.py
```

The Streamlit app will open at **http://localhost:8501**. Use the interactive sliders in the left sidebar to adjust the following parameters:

- **nominal_target_temperature**: The target temperature you aim for (e.g., 20.0°C)
- **nominal_indoor_temperature**: The indoor indoor temperature you aim for (e.g.,  21.0°C)
- **min_target_temperature**: Minimum allowable target temperature (e.g., 17.0°C)
- **max_target_temperature**: Maximum allowable target temperature (e.g., 21.0°C)
- **reference_price**: Baseline electricity price per kWh (e.g., 5.0 snt/kWh)
- **low_temperature_protection_margin**: Maximum allowed drop below the nominal indoor temperature before low temperature protection logic activates. (e.g.,  1.5°C)
- **price_gain**: Gain for price sensitivity in target formula (e.g., 1.2)
- **indoor_temperature_gain**: Gain for indoor-temperature correction (e.g., 1.5)
- **low_temperature_boost**: Additional gain for low-temperature comfort boost (e.g., 3.0)

The app displays three real-time plots:

- **Left (2D)**: Target temperature vs electricity price (indoor temperature fixed)
- **Middle (2D)**: Target temperature vs indoor temperature (electricity price fixed)
- **Right (3D)**: Target temperature as a function of both price and indoor temperature

Adjust any slider to see the plots update instantly. Expand the "Constants" section in the sidebar to view the current JSON values.

## Runtime Behavior

1. Read Thermia and Cozify configuration from SSM Parameter Store.
2. Read current electricity prices from S3 `latest-prices.json`.
3. Read indoor temperature from Cozify and outdoor temperature from Thermia.
4. Compute target temperature with control constants.
5. Decide whether the current slot should heat or stay idle based on prices, history, and outdoor temperature.
6. Apply target temperature and heating curve (or idle target/curve) and update Thermia operation mode.
7. Persist heating history and legionella boost timestamp to S3.
8. If price data is missing, fall back to nominal target temperature and trigger the price ingestor Lambda.

## Operational Monitoring

- Lambda emits one custom CloudWatch metric in namespace `Thermia/OptimizeHeating`:
  - `ApplicationErrorCount`: total count of fallback and application-level errors
- Failure reason is logged in CloudWatch logs, not emitted as a metric dimension.
- CloudWatch alarms (configured threshold: 2 of 3 periods, 15-minute periods):
  - `ApplicationErrorAlarm`: SSM retrieval, Thermia auth/API failures
- All alarms publish to SNS topic: `thermia-optimize-heating-alarms-<account-id>`
- Subscribe to alarm notifications (example, email):
  - `aws sns subscribe --topic-arn <topic-arn> --protocol email --notification-endpoint you@example.com`
- For Cozify unavailability, re-bootstrap tokens:
  - `python scripts/bootstrap_cozify.py --region eu-west-1 --parameter-name /lambda/cozify/config`

## Expected Responses

### Success (200)

- requestId: AWS Lambda request ID for correlation with CloudWatch logs
- message: Target temperature applied successfully
- priceSntPerKwh: current price or null when fallback path triggered before price result
- indoorTemperatureC: indoor temperature or null when fallback path triggered before Cozify result
- targetTemperatureC: computed or fallback target temperature
- fallbackUsed: true or false
- fallbackReason: null, price_data_unavailable, or cozify_unavailable

### Failure (500)

Returned for application-level errors; emits `ApplicationErrorCount` metric.
Examples:

- Missing required configuration
- SSM credential/config retrieval failure
- Thermia authentication or API call failure

