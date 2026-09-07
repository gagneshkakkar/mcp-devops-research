from mcp.server import MCPServer

mcp = MCPServer("DevOps Research MCP Server")


@mcp.tool()
def read_file(file_path: str) -> str:
    """Read a text file from the project."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return f"File not found: {file_path}"
    except Exception as error:
        return f"Error reading file: {error}"


@mcp.tool()
def get_build_status() -> str:
    """Return the current build status."""
    return "CI status tool is working."


@mcp.tool()
def get_build_logs() -> str:
    """Return build log information."""
    return "Build log tool is working."


if __name__ == "__main__":
    mcp.run()