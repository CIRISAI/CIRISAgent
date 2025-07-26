#!/bin/bash
# Test script for the new CIRISManager CLI

echo "=== Testing CIRISManager CLI v2 ==="
echo

# Set the path to use our new CLI
export PYTHONPATH=/home/ciris/ciris/CIRISAgent:$PYTHONPATH
CLI="python /home/ciris/ciris/CIRISAgent/ciris_manager/cli_v2.py"

echo "1. List current agents:"
$CLI agent list
echo

echo "2. List available templates:"
$CLI template list
echo

echo "3. Test the new CIRIS_MODE feature:"
echo "   Creating a test agent with mode='service'..."
$CLI test-mode --mode service
echo

echo "4. Test multi-mode:"
echo "   Creating a test agent with mode='service,discord'..."
$CLI test-mode --mode service,discord
echo

echo "=== Examples of other commands ==="
echo
echo "Create a service agent:"
echo "  $CLI agent create --name my-api --mode service"
echo
echo "Create a Discord bot:"
echo "  $CLI agent create --name my-bot --mode discord --env DISCORD_BOT_TOKEN=xxx"
echo
echo "Create a CLI tool agent (will exit after startup):"
echo "  $CLI agent create --name my-tool --mode tool"
echo
echo "Delete an agent:"
echo "  $CLI agent delete my-api"
echo
echo "Check agent status:"
echo "  $CLI agent status my-api"