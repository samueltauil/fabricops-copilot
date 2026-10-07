# Add support for a Fabric item type

Using current official Microsoft Fabric REST API and `fabric-cicd` documentation:

1. Identify create, update, deploy, bind, schedule, monitor, and delete support.
2. Identify supported identity types and required scopes/roles.
3. Add or update the capability registry.
4. Implement the resource handler without customer-specific branching.
5. Add sanitized contract fixtures and tests for create, rerun/no-op, update, unsupported
   operation, throttling, and long-running operation behavior.
6. Update the capability matrix with the review date and official sources.

Do not implement an optimistic fallback for unsupported behavior.

