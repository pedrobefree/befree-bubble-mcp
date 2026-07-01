# HTML To Bubble

The HTML converter turns simple HTML component input into Bubble plans.

Planned command:

```bash
bubble-mcp import html --file component.html --context index --parent index
```

Planned stages:

```text
HTML -> intermediate layout model -> Bubble plan -> validation -> execute-plan when write_payload is available
```
