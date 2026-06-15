
## Lambda Environment Parameters

The Lambda function requires the following environment variables to be configured in the SAM template (template.yaml) and passed during deployment:

### Core Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `NominalTargetTemperature` | Number | - | Target temperature for the heat pump in normal conditions (°C). |
| `NominalIndoorTemperature` | Number | - | Expected/comfortable indoor temperature (°C). |
| `MinTargetTemperature` | Number | - | Minimum allowed target temperature (°C). |
| `MaxTargetTemperature` | Number | - | Maximum allowed target temperature (°C). |
| `IdleTargetTemperature` | Number | - | Target temperature when the system is idle (°C). |

### Heat Pump Control

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `MinRun` | Number | 2 | Minimum number of consecutive 15-minute time slots during which the heat pump must run without stopping. |
| `MinIdle` | Number | 2 | Minimum number of consecutive 15-minute time slots during which the heat pump must stay off before it may start again. |

### S3 Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `S3BucketPrefix` | String | - | Prefix used to form the account-regional S3 general purpose bucket name. The deployed bucket becomes `<prefix>-<account-id>-<region>-an`. |
| `S3PriceKey` | String | `latest-prices.json` | S3 object key containing quarter-hour electricity prices. |
| `S3HeatingHistoryKey` | String | `heating-history.json` | S3 object key containing historical heating data for optimization. |
| `S3LegionellaBoostKey` | String | `latest-legionella-boost-time.json` | S3 object key containing the latest legionella boost timestamp. |

### Price-Based Control

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ReferencePrice` | Number | - | Reference electricity price (snt/kWh). Used as baseline for price adjustments. |
| `PriceGain` | Number | - | Weighting factor for price-based temperature adjustments. Higher values = greater temperature response to price changes. |
| `HappyPriceBias` | Number | 0.0 | Bias factor for extra heating during low-price periods. At 0.0, heating limited to minimum required time slots. At ~2.0, all available low-price slots are used. Recommended range: 0.0–2.0. |

### Temperature-Based Control

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `IndoorTemperatureGain` | Number | - | Weighting factor for indoor temperature deviation adjustments. |
| `LowTemperatureProtectionMargin` | Number | - | Safety margin to prevent the indoor temperature from falling too low (°C). |
| `LowTemperatureBoost` | Number | - | Additional temperature boost when indoor temperature is critically low. |
| `DefaultHeatingCurve` | Number | - | Default heating curve coefficient for the heat pump. |

### Shutdown Protection

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ShutdownOutdoorTemperatureLimit` | Number | - | Outdoor temperature threshold below which heating is not shut down (°C). Protects against freezing. |
| `ShutdownSupplyLineTemperatureLimit` | Number | - | Supply line temperature threshold. Heating remains active as long as line temperature is above this limit (°C). |

### Summer Mode

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SummerModeAverageTemperatureThreshold` | Number | - | Average outdoor temperature over the last 24 hours required before the controller treats conditions as summer mode (°C). |
| `SummerModeMinimumTemperatureThreshold` | Number | - | Minimum outdoor temperature over the last 24 hours required before the controller treats conditions as summer mode (°C). |

When both thresholds are met, the optimizer treats the current period as summer and skips active heating slots.

### Legionella Prevention

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `LegionellaDisinfectionTemperature` | Number | 61 | A hot water temperature higher than this setting suggests that the legionella boost has been activated. Legionella boost prevents legionella bacteria growth by ensuring adequate hot water temperature. |

### Runtime Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Timezone` | String | `Europe/Helsinki` | IANA time zone used for schedule logging and local time conversion in the heating planner. |
| `LogLevel` | String | - | Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL. |
| `ThermiaDemoMode` | String | - | Demo mode for Thermia API: "true" or "false". When enabled, the system reads data but does not update heat pump settings. |

