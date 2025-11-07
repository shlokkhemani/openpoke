#!/usr/bin/env python3
"""
Script to discover available Google Calendar tools in Composio.

Run this to see what tools are actually available in the GOOGLECALENDAR toolkit.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from server.services.composio_client import get_composio_client


def list_calendar_tools():
    """List all available Google Calendar tools from Composio."""
    print("Fetching Google Calendar tools from Composio...\n")
    
    try:
        client = get_composio_client()
        
        # Get all tools for GOOGLECALENDAR toolkit
        tools = client.client.tools.get_raw_composio_tools(
            toolkits=["GOOGLECALENDAR"],
            limit=100
        )
        
        print(f"Found {len(tools)} Google Calendar tools:\n")
        print("=" * 80)
        
        for tool in tools:
            name = tool.get("name", "Unknown")
            description = tool.get("description", "No description")
            print(f"\nTool: {name}")
            print(f"Description: {description}")
            
            # Show parameters if available
            parameters = tool.get("parameters", {}).get("properties", {})
            if parameters:
                print("Parameters:")
                for param_name, param_info in parameters.items():
                    param_type = param_info.get("type", "unknown")
                    param_desc = param_info.get("description", "")
                    print(f"  - {param_name} ({param_type}): {param_desc}")
        
        print("\n" + "=" * 80)
        print(f"\nTotal: {len(tools)} tools")
        
        # Save to file
        output_file = Path(__file__).parent / "composio_calendar_tools.txt"
        with open(output_file, "w") as f:
            f.write(f"Google Calendar Tools in Composio ({len(tools)} total)\n")
            f.write("=" * 80 + "\n\n")
            for tool in tools:
                f.write(f"Tool: {tool.get('name', 'Unknown')}\n")
                f.write(f"Description: {tool.get('description', 'No description')}\n\n")
        
        print(f"\nTools list saved to: {output_file}")
        
    except Exception as e:
        print(f"Error fetching tools: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    list_calendar_tools()
