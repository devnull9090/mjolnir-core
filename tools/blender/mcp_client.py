"""Call the actual Blender MCP server from a checkout without an app restart.

uvx --from mcp-for-blender==2.2.7 python tools/blender/mcp_client.py --list
uvx --from mcp-for-blender==2.2.7 python tools/blender/mcp_client.py get_scene_info
The server talks to the enabled Blender add-on in a running GUI session.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--args", default="{}")
    parser.add_argument("--args-file", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--log", type=Path, default=Path("out/blender-mcp-client.log"))
    args = parser.parse_args()
    uvx = shutil.which("uvx")
    if not uvx:
        parser.error("uvx is not installed")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    server = StdioServerParameters(command=uvx, args=["--from", "mcp-for-blender==2.2.7", "mcp-for-blender"], env=env)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as errlog:
        async with asyncio.timeout(args.timeout), stdio_client(server, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if args.list:
                    result = await session.list_tools()
                else:
                    if not args.tool:
                        parser.error("specify a tool or --list")
                    payload = json.loads(args.args_file.read_text(encoding="utf-8-sig") if args.args_file else args.args)
                    result = await session.call_tool(args.tool, payload)
                output = result.model_dump_json(indent=2)
                if args.out:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    args.out.write_text(output, encoding="utf-8")
                    print(str(args.out.resolve()))
                else:
                    print(output)
                if getattr(result, "isError", False):
                    raise RuntimeError("Blender MCP tool returned an error")
                # Upstream execute_blender_code returns Python failures as a
                # normal text result rather than setting the MCP error bit.
                if args.tool == "execute_blender_code" and any(
                    getattr(block, "text", "").lstrip().startswith("Error executing code:")
                    for block in getattr(result, "content", [])
                ):
                    raise RuntimeError("Blender Python failed; inspect the saved MCP receipt")


if __name__ == "__main__":
    asyncio.run(main())
