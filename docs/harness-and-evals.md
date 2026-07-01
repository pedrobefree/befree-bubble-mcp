# Harness And Evals

The harness will measure whether natural-language requests route to the correct Bubble tools and arguments.

Planned metrics:

- matched cases
- correct tool
- correct args
- validation result
- warning expectations
- parser path
- token reduction from context selection

Planned command:

```bash
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --report reports/basic.json
```
