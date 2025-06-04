from dotenv import load_dotenv
from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
import ollama
import json
import asyncio
import nest_asyncio

nest_asyncio.apply()

load_dotenv()

SYSTEM_PROMPT = """
You are an AI assistant for Tool Calling.

Before you help a user, you need to work with tools to interact with Our Database
        """

class MCP_ChatBot:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
        # Tools list required for Anthropic API
        self.available_tools = []
        # Prompts list for quick display 
        self.available_prompts = []
        # Sessions dict maps tool/prompt names or resource URIs to MCP client sessions
        self.sessions = {}

    async def connect_to_server(self, server_name, server_config):
        try:
            server_params = StdioServerParameters(**server_config)
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            
            
            try:
                # List available tools
                response = await session.list_tools()
                for tool in response.tools:
                    self.sessions[tool.name] = session
                    self.available_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                        # local tools interface
                        'type': 'function',
                        'function': {
                            "name": tool.name,
                            "description": tool.description,
                            'parameters': tool.inputSchema
                        },
                    })
            
                # List available prompts
                prompts_response = await session.list_prompts()
                if prompts_response and prompts_response.prompts:
                    for prompt in prompts_response.prompts:
                        self.sessions[prompt.name] = session
                        self.available_prompts.append({
                            "name": prompt.name,
                            "description": prompt.description,
                            "arguments": prompt.arguments
                        })
                # List available resources
                resources_response = await session.list_resources()
                if resources_response and resources_response.resources:
                    for resource in resources_response.resources:
                        resource_uri = str(resource.uri)
                        self.sessions[resource_uri] = session
            
            except Exception as e:
                print(f"Error {e}")
                
        except Exception as e:
            print(f"Error connecting to {server_name}: {e}")

    async def connect_to_servers(self):
        try:
            with open("server_config.json", "r") as file:
                data = json.load(file)
            servers = data.get("mcpServers", {})
            for server_name, server_config in servers.items():
                await self.connect_to_server(server_name, server_config)
        except Exception as e:
            print(f"Error loading server config: {e}")
            raise
    
    async def process_query(self, query):
        messages = [{'role':'user', 'content':query}]
        
        while True:
            response = self.anthropic.messages.create(
                max_tokens = 2024,
                model = 'claude-3-7-sonnet-20250219', 
                tools = self.available_tools,
                messages = messages
            )
            
            assistant_content = []
            has_tool_use = False
            
            for content in response.content:
                if content.type == 'text':
                    print(content.text)
                    assistant_content.append(content)
                elif content.type == 'tool_use':
                    has_tool_use = True
                    assistant_content.append(content)
                    messages.append({'role':'assistant', 'content':assistant_content})
                    
                    # Get session and call tool
                    session = self.sessions.get(content.name)
                    if not session:
                        print(f"Tool '{content.name}' not found.")
                        break
                        
                    result = await session.call_tool(content.name, arguments=content.input)
                    messages.append({
                        "role": "user", 
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": result.content
                            }
                        ]
                    })
            
            # Exit loop if no tool was used
            if not has_tool_use:
                break
    
    async def process_query_local(self, query):
        messages = [{'role': 'user', 'content': query}]

        # print("------------available_tools - START-----------")
        # print(self.available_tools)
        # print("-------------available_tools - END------------")

        while True:
            response = ollama.chat(
                model = 'ai-assistant-tool-calling',
                messages = messages,
                tools = self.available_tools,
                # tools=[],
                stream = False
            )
            # If using requests.post, do: response = response.json()

            msg = response.get("message", {})
            tool_calls = msg.get("tool_calls", [])
            content = msg.get("content", "")

            # print("------------response - START-----------")
            # print(response.message)
            # print("-------------response - END------------")

            if content:
                print(content)

            if tool_calls:
                for tool_call in tool_calls:
                    fn = tool_call.get("function", {})
                    tool_name = fn.get("name")
                    arguments = fn.get("arguments", {})
                    session = self.sessions.get(tool_name)
                    if not session:
                        print(f"Tool '{tool_name}' not found.")
                        continue

                    # print("------------arguments - START-----------")
                    # print(arguments)
                    # print("-------------arguments - END------------")
                    # print("------------tool_name - START-----------")
                    # print(tool_name)
                    # print("-------------tool_name - END------------")
                    # print("------------call_tool - START-----------")
                    result = await session.call_tool(tool_name, arguments=arguments)
                    # print("-------------call_tool - END------------")
                    # print("------------result - START-----------")
                    # print(result.content[0].text)
                    # print("-------------result - END------------")
                    # # Add tool result to messages for next round
                    # messages.append({
                    #     "role": "user",
                    #     "content": [
                    #         {
                    #             "type": "tool_result",
                    #             "tool_use_id": tool_call.get("id", tool_name),
                    #             "content": result.content[0].text
                    #         }
                    #     ]
                    # })
                    # print("------------messages - START-----------")
                    # print(messages)
                    # print("-------------messages - END------------")

                    # print("------------messages - START-----------")
                    print(result.content[0].text)
            break

    async def get_resource(self, resource_uri):
        session = self.sessions.get(resource_uri)
        
        # Fallback for papers URIs - try any papers resource session
        if not session and resource_uri.startswith("papers://"):
            for uri, sess in self.sessions.items():
                if uri.startswith("papers://"):
                    session = sess
                    break
            
        if not session:
            print(f"Resource '{resource_uri}' not found.")
            return
        
        try:
            result = await session.read_resource(uri=resource_uri)
            if result and result.contents:
                print(f"\nResource: {resource_uri}")
                print("Content:")
                print(result.contents[0].text)
            else:
                print("No content available.")
        except Exception as e:
            print(f"Error: {e}")
    
    async def list_tools(self):
        """List all available tools."""
        if not self.available_tools:
            print("No tools available.")
            return
        
        print("\nAvailable tools:")
        print("-" * 50)
        for tool in self.available_tools:
            print(f"• {tool['name']}")
            print(f"  Description: {tool['description']}")
            
            # Show input schema in a readable format
            if tool['input_schema'] and 'properties' in tool['input_schema']:
                print("  Parameters:")
                properties = tool['input_schema']['properties']
                required = tool['input_schema'].get('required', [])
                
                for param_name, param_info in properties.items():
                    param_type = param_info.get('type', 'unknown')
                    param_desc = param_info.get('description', 'No description')
                    required_marker = " (required)" if param_name in required else " (optional)"
                    print(f"    - {param_name} ({param_type}){required_marker}: {param_desc}")
            print()
    
    async def list_prompts(self):
        """List all available prompts."""
        if not self.available_prompts:
            print("No prompts available.")
            return
        
        print("\nAvailable prompts:")
        print("-" * 50)
        for prompt in self.available_prompts:
            print(f"• {prompt['name']}")
            print(f"  Description: {prompt['description']}")
            if prompt['arguments']:
                print("  Arguments:")
                for arg in prompt['arguments']:
                    arg_name = arg.name if hasattr(arg, 'name') else arg.get('name', '')
                    print(f"    - {arg_name}")
            print()
    
    async def execute_prompt(self, prompt_name, args):
        """Execute a prompt with the given arguments."""
        session = self.sessions.get(prompt_name)
        if not session:
            print(f"Prompt '{prompt_name}' not found.")
            return
        
        try:
            result = await session.get_prompt(prompt_name, arguments=args)
            if result and result.messages:
                prompt_content = result.messages[0].content
                
                # Extract text from content (handles different formats)
                if isinstance(prompt_content, str):
                    text = prompt_content
                elif hasattr(prompt_content, 'text'):
                    text = prompt_content.text
                else:
                    # Handle list of content items
                    text = " ".join(item.text if hasattr(item, 'text') else str(item) 
                                  for item in prompt_content)
                
                print(f"\nExecuting prompt '{prompt_name}'...")
                await self.process_query(text)
        except Exception as e:
            print(f"Error: {e}")
    
    async def show_help(self):
        """Show help information about available commands."""
        help_text = """
Available Commands:
==================

Resource Commands:
  @folders                    - Show available paper topics/folders
  @<topic>                   - Search papers in a specific topic

Prompt Commands:
  /prompts                   - List all available prompts
  /prompt <name> <args>      - Execute a prompt with arguments
                              Example: /prompt analyze topic=AI

Tool Commands:
  /tools                     - List all available tools with descriptions

General Commands:
  /help                      - Show this help message
  quit                       - Exit the chatbot

Regular queries will be processed by Claude with access to all available tools.
        """
        print(help_text)
    
    async def chat_loop(self):
        print("\nMCP Chatbot Started!")
        print("Type your queries or 'quit' to exit.")
        print("Use /help to see all available commands.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                if not query:
                    continue
        
                if query.lower() == 'quit':
                    break
                
                # Check for @resource syntax first
                if query.startswith('@'):
                    # Remove @ sign  
                    topic = query[1:]
                    if topic == "folders":
                        resource_uri = "papers://folders"
                    else:
                        resource_uri = f"papers://{topic}"
                    await self.get_resource(resource_uri)
                    continue
                
                # Check for /command syntax
                if query.startswith('/'):
                    parts = query.split()
                    command = parts[0].lower()
                    
                    if command == '/help':
                        await self.show_help()
                    elif command == '/tools':
                        await self.list_tools()
                    elif command == '/prompts':
                        await self.list_prompts()
                    elif command == '/prompt':
                        if len(parts) < 2:
                            print("Usage: /prompt <name> <arg1=value1> <arg2=value2>")
                            continue
                        
                        prompt_name = parts[1]
                        args = {}
                        
                        # Parse arguments
                        for arg in parts[2:]:
                            if '=' in arg:
                                key, value = arg.split('=', 1)
                                args[key] = value
                        
                        await self.execute_prompt(prompt_name, args)
                    else:
                        print(f"Unknown command: {command}")
                        print("Use /help to see available commands.")
                    continue
                
                await self.process_query_local(query)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    chatbot = MCP_ChatBot()
    try:
        await chatbot.connect_to_servers()
        await chatbot.chat_loop()
    finally:
        await chatbot.cleanup()


if __name__ == "__main__":
    asyncio.run(main())