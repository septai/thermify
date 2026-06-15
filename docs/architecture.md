# Architecture Overview

This project follows a classic layered (clean architecture inspired) split to keep business logic simple, testable, and independent from AWS and third-party API details.

Primary reference for this split: [The Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

## Layer Map

- Domain layer: core business rules and domain-specific exceptions.
- Application layer: use-case orchestration and application-level contracts.
- Adapter layer: infrastructure and external system integrations.
- Configuration and entrypoint layer: runtime settings and Lambda handler wiring.

In this repository, these layers map to the following folders:

- `src/domain`
- `src/application`
- `src/adapters`
- `src/config` plus `src/handler_optimizer.py` and `src/handler_ingestor.py`

## What Each Layer Does

### 1) Domain (`src/domain`)

Purpose:
- Owns the pure business rules for price-driven target temperature calculation.
- Contains no AWS SDK, no Thermia API client, and no Lambda-specific code.

Current implementation:
- `how_much_to_heat.py`: pure functions and types for computing a price-driven target temperature.
  - `TemperatureControlConstants` holds all tunable constants (nominal/limits, gains, reference price, protection margins).
  - `clamp(value, minimum, maximum)` bounds values to an inclusive range.
  - `compute_target_temperature(price, indoor_temperature, constants)` implements the control formula:
    - `price_adjustment = (reference_price - price) / reference_price`
    - `indoor_temperature_adjustment = max(nominal_indoor - Ti, 0)`
    - `low_indoor_temperature_adjustment = max(nominal_indoor - Ti - low_temperature_protection_margin, 0)`
    - `Tset_raw = Tnom + price_gain * price_adjustment + indoor_temperature_gain * indoor_temperature_adjustment + low_temperature_boost * low_indoor_temperature_adjustment`
    - Indoor comfort guards:
      - if `Ti > nominal_indoor`, cap `Tset_raw` to at most `Tnom`
      - if `Ti < nominal_indoor - low_temperature_protection_margin`, raise `Tset_raw` to at least `Tnom - low_temperature_protection_margin`
    - Final result is clamped to `[min_target_temperature, max_target_temperature]`.

- `when_to_heat.py`: a scheduling planner that decides whether the current quarter-hour should heat.
  - Implements `WhenToHeatPlanner` which builds a combined timeseries from quarter-hour prices and recent heating history.
  - Uses heuristics to compute parameters (heating duty cycle from outdoor temperature, `happy_price` cutoff, `max_gap`) and encodes constraints (`min_run`, `min_idle`, gap limits).
  - Solves an Integer Linear Program (PuLP/CBC) to minimize cost while prioritizing cheap slots and respecting run/idle constraints.
  - Returns a boolean indicating whether heating should be on for the current slot and logs a compact visual schedule for debugging.

Why this matters:
- Domain logic is deterministic and easy to unit-test.
- Control algorithm can evolve without touching infrastructure code.

### 2) Application (`src/application`)

Current implementation:
- `heating_control_service.py` — `HeatingControlService(settings).execute()` performs the optimizer use-case flow: reads prices and temperatures, computes the optimized target temperature, decides whether the current slot should heat (using the planner), applies settings to the heat pump, and persists heating history and legionella boost timestamps.
- `electricity_price_service.py` — `ElectricityPriceService` (used by the ingestor handler) fetches electricity prices from the configured API, normalizes/validates the payload, and persists the latest prices to S3 for use by the optimizer.
- Protocols define dependency contracts (`ParameterStoreClientProtocol`, `S3ClientProtocol`, `CozifyClientProtocol`, `ThermiaClientProtocol`, and the price-ingestion client used by `ElectricityPriceService`).
- `HeatingControlResult` is a Data Transfer Object (DTO) returned to the handler, including price, indoor_temperature, outdoor_temperature, target_temperature, and fallback status.
- `when_to_heat.py` provides the scheduling planner used by the service.
- `errors.py` contains application and adapter exception types.

Fallback behavior:
- If S3 price read fails: use Tnom (nominal temperature)
- If Cozify sensor read fails: use Tnom
- If Thermia control fails: propagate error (500 to caller)


### 3) Adapters (`src/adapters`)

Purpose:
- Integrates with external systems and converts low-level failures to controlled application errors.

Current implementation:
- `parameter_store.py`: `ParameterStoreClient` reads SecureString values from AWS SSM Parameter Store (Thermia and Cozify credentials).
- `s3_client.py`: `S3Client` reads and writes JSON data in S3 (prices, heating history, legionella boost timestamps).
- `cozify_client.py`: `CozifyClient` authenticates to Cozify, refreshes tokens when needed, and reads indoor temperature.
- `thermia_client.py`: `ThermiaClient` wraps Thermia Online API interactions (target temperature, heating curve, operation mode).
- All adapters translate external API specifics into application-level exceptions.
 - `electricity_price_client.py`: `ElectricityPriceClient` communicates with the configured electricity market API, handles authentication/retries, and normalizes provider-specific responses into the canonical price payload consumed by `ElectricityPriceService`. It maps remote API failures to application-level exceptions.

Why this matters:
- External API specifics are isolated from business/use-case logic.
- Swapping integration details does not require rewriting domain code.

### 4) Config and Entrypoint (`src/config` and `src/handler_optimizer.py`, `src/handler_ingestor.py`)

Purpose:
- Load runtime configuration and wire dependencies for Lambda execution.

Current implementation:
- `config/settings.py`: `OptimizerSettings.from_env()` and `IngestorSettings.from_env()` validate all required environment variables.
- `handler_optimizer.py`: Creates `HeatingControlService` with concrete adapters, calls the use case, and maps result/failure to response payloads.
- `handler_ingestor.py`: Invokes `ElectricityPriceService` to fetch prices and persist them to S3.

Why this matters:
- Lambda-specific concerns stay at the edge.
- Core behavior remains reusable and easy to test outside Lambda runtime.

## Dependency Direction (Clean Architecture Rule)

Dependencies should point inward toward business logic:
Dependencies point inward toward business logic:

- `handler` / `config` -> `application` -> `domain`
- `adapters` implement outward-facing contracts and are consumed by handlers and application services
- `domain` must not depend on AWS SDKs, HTTP clients, handlers, or other infrastructure code

Current wiring in this repository:
- `handler_optimizer.py` composes `HeatingControlService` with adapter implementations: `ParameterStoreClient`, `S3Client`, `ThermiaClient`, and `CozifyClient`.
- `handler_ingestor.py` composes `ElectricityPriceService` with `ElectricityPriceClient` and `S3Client`.
- `HeatingControlService` and `ElectricityPriceService` depend only on protocol interfaces and `src/domain` functions; they do not import adapters directly.
- Adapters (for example `thermia_client.py`, `cozify_client.py`, `electricity_price_client.py`, `s3_client.py`, `parameter_store.py`) translate external APIs into application-level DTOs and exceptions and do not reference domain logic.

## Request Flow Through Layers

Optimizer Lambda flow:

1. Lambda invokes `lambda_handler` in `src/handler_optimizer.py` (EventBridge schedule, every 15 minutes).
2. Handler loads `OptimizerSettings.from_env()` and validates configuration.
3. Handler composes concrete adapters: `ParameterStoreClient`, `S3Client`, `ThermiaClient`, `CozifyClient` and constructs `HeatingControlService` with those protocols.
4. `HeatingControlService` reads the latest normalized prices from S3 (e.g. `latest-prices.json`); if unavailable it uses nominal/fallback pricing.
5. Service reads indoor temperature via `CozifyClient` and outdoor temperature via `ThermiaClient`; sensor failures are handled with fallback to `Tnom` when appropriate.
6. Service computes the candidate target temperature using `compute_target_temperature()` and invokes `WhenToHeatPlanner` to decide whether the current quarter-hour should heat.
7. If heating is required, the service applies the computed target temperature, heating curve and operation mode through `ThermiaClient`, records heating history and any legionella boost timestamps, and persists them to S3.
8. `HeatingControlService` returns a `HeatingControlResult` DTO; the handler translates it to a JSON response and HTTP-style status code (200 on success). Adapter or control failures are surfaced as 5xx responses.

Price ingestor Lambda flow:

1. Lambda invokes `lambda_handler` in `src/handler_ingestor.py` (scheduled daily or triggered by optimizer fallback).
2. Handler loads `IngestorSettings.from_env()` and validates environment variables.
3. Handler composes `ElectricityPriceService` with `ElectricityPriceClient` (adapter) and `S3Client`.
4. `ElectricityPriceService` fetches market prices via `ElectricityPriceClient`, normalizes and validates the payload (timezone/region adjustments, format checks), and applies retries/backoff as needed.
5. Service persists the canonical `latest-prices.json` to S3 for the optimizer.
6. Handler returns a success response; ingestion errors are mapped to appropriate error responses (4xx/5xx) depending on the failure mode.

## Benefits of This Structure

- High testability: domain and application logic can be tested with mocks/fakes.
- Lower coupling: AWS, Thermia and Cozify details are isolated in adapters.
- Clear maintenance boundaries: each folder has one primary responsibility.
- Safer evolution: changing transport/infrastructure layers does not force domain rewrites.

## Practical Notes

- Add new business rules in `src/domain` first.
- Add or update use-case orchestration in `src/application`.
- Place new integrations in `src/adapters` and translate low-level errors.
- Keep Lambda/event formatting and response mapping inside `src/handler_optimizer.py` and `src/handler_ingestor.py`.
- Keep environment and runtime configuration in `src/config`.
