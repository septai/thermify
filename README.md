# Thermia Price-Driven Heating Control Lambdas (AWS SAM)

AWS SAM based Python Lambdas that ingest quarter-hour electricity prices daily and optimize Thermia heating every 15 minutes based on price, as well as indoor and outdoor temperatures. Cozify home automation sensors are used to measure the indoor temperature. Prices come from Nord Pool day-ahead market data.

Credentials and Cozify configuration are loaded from AWS Systems Manager Parameter Store `SecureString` parameters.

Includes Python scripts
- to set up the Cozify configuration for the first time, and
- to adjust and fine-tune the optimizer’s parameters.

The project is a hobby project and is not actively maintained.

## Features

- Clean architecture (domain, application, adapters, config).
- Ingests quarter-hour prices from a power price API and stores them in S3.
- Reads quarter-hour prices from the S3 bucket object `latest-prices.json`.
- Reads indoor temperature from Cozify sensor.
- Reads outdoor temperature from Thermia heat pump.
- Uses outdoor temperature, heating history, and pricing to decide whether to heat in the current 15 minute slot.
- Updates heat pump's heating curve and operation mode based on the current slot decision.
- Tracks legionella boost timestamps in S3 to trigger hot water legionella disinfection regularly.
- Fallback behavior: if price data is missing or Cozify is unavailable, uses fallback heating settings. When price data is missing, the optimizer Lambda triggers the ingestor Lambda.
- Secure credential retrieval using AWS SSM Parameter Store.
- Unit tests for domain logic, adapters, service orchestration, and Lambda handler.

## Project Layout

- `src/`: application code
- `scripts/`: local bootstrap and tuning tools
- `layers/`: Lambda layer assets
- `tests/`: unit and integration tests
- `docs/`: usage and technical documentation
- `requirements/`: dependency files
- `template.yaml`: SAM template (infrastructure and deployment definition)
- `samconfig.toml`: SAM defaults and parameter overrides
- `pyproject.toml`: linting, formatting, type-checking, and pytest configuration
- `.gitignore`

## Architecture

This project uses a clean/layered architecture split:

- Domain (`src/domain`): pure business rules and domain errors.
- Application (`src/application`): use-case orchestration and contracts.
- Adapters (`src/adapters`): integrations with Thermia API, S3, Cozify, and AWS SSM.
- Config/Entrypoint (`src/config`, `src/handler_optimizer.py`, `src/handler_ingestor.py`): environment settings and Lambda wiring.

For a full explanation of responsibilities, dependency direction, and request flow, see `docs/architecture.md`.

## Prerequisites

- Python 3.14+
- AWS SAM CLI
- AWS credentials with permissions to deploy CloudFormation and read SSM parameters
- Thermia account credentials stored in Parameter Store as `SecureString`
- Electricity price API URL for the ingestor Lambda

## Setup

1. Create and activate virtual environment.
2. Install dev dependencies:

```bash
pip install -r requirements/dev.txt
```

3. Put your Thermia username and password into SSM:

```bash
aws ssm put-parameter \
  --name /lambda/thermia/username \
  --type SecureString \
  --value "YOUR_USERNAME" \
  --overwrite

aws ssm put-parameter \
  --name /lambda/thermia/secret \
  --type SecureString \
  --value "YOUR_PASSWORD" \
  --overwrite
```

4. Bootstrap Cozify configuration into SSM:

```bash
python scripts/bootstrap_cozify.py \
  --region eu-west-1 \
  --parameter-name /lambda/cozify/config
```

The bootstrap flow performs interactive Cozify login and writes finalized config JSON to SSM SecureString.

Dry-run mode to preview generated JSON without writing SSM:

```bash
python scripts/bootstrap_cozify.py --dry-run --region eu-west-1
```

5. Optional manual Cozify parameter write:

```bash

aws ssm put-parameter \
  --name /lambda/cozify/config \
  --type SecureString \
  --value '{"cloud_token": "...", ...}' \
  --overwrite
```

> **Note**: Cozify configuration must be in JSON format. See [docs/configuration.md](docs/configuration.md) for the complete schema, field descriptions, and manual setup instructions.

## Build and Validate

```bash
sam validate
sam build
```

## Deploy

```bash
sam deploy --guided
```

Guided values and their defaults:

- `ThermiaUsernameParameterPath`: `/lambda/thermia/username`
- `ThermiaPasswordParameterPath`: `/lambda/thermia/secret`
- `CozifyConfigParameterPath`: `/lambda/cozify/config`
- `S3BucketPrefix`: your bucket prefix
- `S3PriceKey`: `latest-prices.json`
- `S3HeatingHistoryKey`: `heating-history.json`
- `S3LegionellaBoostKey`: `latest-legionella-boost-time.json`

The stack creates the S3 bucket automatically when it is missing.

## Local Invoke

Local invoke uses initialization defaults from `template.yaml` and `samconfig.toml`.

```bash
sam local invoke OptimizeHeatingFunction
```

Invoke the ingestor Lambda locally:

```bash
sam local invoke IngestSpotPricesFunction
```


## Testing

Run unit tests:

```bash
pytest tests/unit
```

Run integration tests (opt-in):

```bash
RUN_INTEGRATION_TESTS=1 pytest tests/integration -m integration
```

## Parameters tuning

Run the interactive parameters tuner:

```bash
streamlit run scripts/tune_temperature_control.py
```

## Documentation

- `docs/usage.md`
- `docs/cozify-configuration.md`
- `docs/lambda-environment-parameters.md`
- `docs/architecture.md`

## License

GPL-3.0-only.

