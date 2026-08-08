# Operations

How we host, ship, and sequence the build.

## Documents

- [Hosting](./hosting.md) — where the Gateway runs
- [Roadmap](./roadmap.md) — phased delivery
- [Testing](../testing/index.md) — autonomous verification plan

## Operating principles

1. Prefer one always-on Gateway over many fragile services
2. Observe before expanding autonomy
3. Enable risky skills behind flags after safer slices work
4. Keep plan docs updated when decisions change
5. Do not exit a build phase until its testing unlock is green ([testing roadmap](../testing/roadmap.md))
