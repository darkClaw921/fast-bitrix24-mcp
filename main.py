from fast_bitrix24_mcp.main import mcp


if __name__ == "__main__":  
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
    # mcp.run(transport="streamable-http", host="127.0.0.1", port=9000)
