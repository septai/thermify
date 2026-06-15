# Layered Architecture Diagram

The project now has two separate Lambda flows. The optimizer decides whether to heat and updates the Thermia controls, while the ingestor only fetches and stores spot prices.

## Optimizer Lambda

```mermaid
flowchart TB
    subgraph L4[Configuration and Entrypoint Layer]
        H1[src/handler_optimizer.py]
        S[src/config/settings.py]
    end

    subgraph L3[Application Layer]
        HCS[src/application/heating_control_service.py]
    end

    subgraph L2[Domain Layer]
        TM[src/domain/how_much_to_heat.py]
        WT[src/domain/when_to_heat.py]
    end

    subgraph L1[Adapter Layer]
        PS[src/adapters/parameter_store.py]
        SPC[src/adapters/s3_client.py]
        CC[src/adapters/cozify_client.py]
        ThC[src/adapters/thermia_client.py]
    end

    H1 --> HCS
    S --> HCS
    HCS --> TM
    HCS --> WT
    HCS --> PS
    HCS --> SPC
    HCS --> CC
    HCS --> ThC

    classDef layer fill:#eef7f2,stroke:#2f6f4f,stroke-width:1.5px,color:#1c3a2b;
    class L1,L2,L3,L4 layer;
```

## Ingestor Lambda

```mermaid
flowchart TB
    subgraph I4[Configuration and Entrypoint Layer]
        H2[src/handler_ingestor.py]
        S2[src/config/settings.py]
    end

    subgraph I3[Application Layer]
        EPS[src/application/electricity_price_service.py]
    end

    subgraph I1[Adapter Layer]
        PC[src/adapters/electricity_price_client.py]
        SPC[src/adapters/s3_client.py]
    end

    H2 --> EPS
    S2 --> EPS
    EPS --> PC
    EPS --> SPC

    classDef layer fill:#eef7f2,stroke:#2f6f4f,stroke-width:1.5px,color:#1c3a2b;
    class I1,I3,I4 layer;
```
