# Thermia Dependency Layer

This directory is used by AWS SAM to build a Lambda Layer containing third-party Python dependencies.

## Build Inputs

- `layers/thermia-python/requirements.txt`
- `requirements/layer-thermia.txt`

## Build

SAM builds this layer automatically during:

```bash
sam build
```
