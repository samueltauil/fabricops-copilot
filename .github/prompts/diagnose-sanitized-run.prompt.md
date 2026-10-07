# Diagnose a sanitized FabricOps run

Analyze only the supplied sanitized plan, evidence, correlation IDs, and capability
report. Classify the likely failure as authentication, authorization, throttling,
validation, conflict, unsupported capability, long-running operation, or service error.

Do not request or expose access tokens, authorization headers, item definitions,
connection strings, PHI, raw customer data, or unrestricted audit exports. Recommend
the smallest safe diagnostic step and state whether a rerun is safe.

