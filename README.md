# ASRock Industrial MCP Tool

An MCP (Model Context Protocol) tool designed specifically for ASRock Industrial products, helping users search and compare subtle differences between different products.

## Purpose

This tool can:
- Search ASRock Industrial product information
- Get detailed product specifications
- Compare subtle differences between different products
- Integrate into the MCP ecosystem for use

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Build Project

```bash
# Development mode installation
pip install -e .
```

## MCP Server Configuration

### Configuration Instructions

- **command**: Use your Python environment path (e.g., `/home/user/anaconda3/envs/mcp/bin/python`)
- **timeout**: Recommended to set to 120 seconds, as web scraping may take longer
- **autoApprove**: Optional operations to auto-approve, leave empty for manual confirmation

### Complete Configuration Example

```json
{
  "mcpServers": {
    "asrockind": {
      "autoApprove": [],
      "disabled": false,
      "timeout": 120,
      "type": "stdio",
      "command": "/home/user/anaconda3/envs/mcp/bin/python",
      "args": [
        "-m",
        "mcp_server_asrockind"
      ]
    }
  }
}
```

## Usage

### Search Products

```json
{
  "tool": "asrock_industrial_product_search",
  "arguments": {
    "query": "SBC-230"
  }
}
```

### Response Format

```json
{
  "query": "SBC-230",
  "total_results": 2,
  "products": [
    {
      "name": "SBC-230 3.5\" SBC",
      "url": "https://www.asrockind.com/en-gb/product/SBC-230",
      "specifications": {
        "CPU - Processor": "Intel Atom x6000E series",
        "Memory - System Memory": "Up to 8GB DDR4"
      }
    }
  ]
}
```

## Supported Search Types
- Product Models: `"SBC-230"`, `"IMB-1235"`...

## License

MIT License. 