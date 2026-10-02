# Ghidra over MCP

Reverse-engineering the game's binaries from a Claude Code session, without
driving the Ghidra GUI by hand. Set up 2026-09-11 for the "why won't a
brand-new scenario package start" question ([new_scenario_loading.md](../new_scenario_loading.md)).

## Pieces

- **Ghidra 12.1.3** at `C:\tools\ghidra_12.1.3_PUBLIC`, project `C:\ghidra_proj\HCE_Analysis`.
  The project's top-level `HaloCampaignEvolved.exe` is the **CU3** build (PE stamp
  `0x7a1c4ff8`); the current binaries live under the project folder `CU4/`
  (`HaloCampaignEvolved.exe` stamp `0x8a03f777`, and `HaloSimulation_tag_release.dll`),
  imported with `support\analyzeHeadless.bat C:\ghidra_proj HCE_Analysis/CU4 -import ...`
  from `C:\ghidra_proj\cu4\` — the batch launcher cannot take the Steam path's spaces
  and parentheses. Every RVA in the docs is CU4 unless it says otherwise.
- **GhidraMCP 6.0.0** ([bethington/ghidra-mcp](https://github.com/bethington/ghidra-mcp)):
  the extension is installed under `%APPDATA%\ghidra\ghidra_12.1.3_PUBLIC\Extensions\GhidraMCP`
  with its `extension.properties` version bumped from 12.1.2 to 12.1.3, and the Python
  bridge is a `uv tool` (`bridge-mcp-ghidra`, in `%USERPROFILE%\.local\bin`).
- `.mcp.json` registers the bridge as the `ghidra` MCP server (stdio). The bridge
  multiplexes onto GhidraMCP's HTTP server at `127.0.0.1:8089`, which has to be running
  first — either the GUI plugin (Tools > GhidraMCP > Start MCP Server) or the headless
  server below.

## Headless server

`tools\re\ghidra_mcp_headless.ps1` runs `com.xebyte.headless.GhidraMCPHeadlessServer`
out of the extension jar on Ghidra's own classpath — no GUI, 195 endpoints:

```powershell
# a binary on its own: imports into a scratch project, then POST /run_analysis
tools\re\ghidra_mcp_headless.ps1 -File C:\ghidra_proj\cu4\HaloSimulation_tag_release.dll
# a program from the project (only once no analyzeHeadless holds the project lock)
tools\re\ghidra_mcp_headless.ps1 -Project C:\ghidra_proj\HCE_Analysis -Program CU4/HaloCampaignEvolved.exe
```

The REST surface is usable straight from curl while the MCP bridge is not connected:

```bash
curl http://127.0.0.1:8089/check_connection
curl -X POST http://127.0.0.1:8089/run_analysis
curl "http://127.0.0.1:8089/list_strings?filter=scenario&limit=50"
curl "http://127.0.0.1:8089/decompile_function?address=0x1802eb130"
```

Analysis of the 230 MB exe takes hours; the 14 MB tag DLL a few minutes. Script
endpoints are off unless `GHIDRA_MCP_ALLOW_SCRIPTS=1`, and the server binds loopback only.
