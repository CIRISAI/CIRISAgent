# CIRIS Developer Guide

Welcome to CIRIS development! This guide will help you get up and running quickly with a streamlined local development environment.

> **Full-Stack Development?** See [Full-Stack Development](#full-stack-development) section for GUI + Backend setup!

## Quick Start (5 minutes)

### 1. Clone and Setup
```bash
git clone https://github.com/CIRISAI/CIRISAgent.git
cd CIRISAgent

# Run the automated setup
python dev_setup.py
```

This will:
- ✅ Check Python version (3.11+ required)
- ✅ Create virtual environment
- ✅ Install dependencies
- ✅ Set up development environment
- ✅ Create helper scripts
- ✅ Configure VS Code debugging

### 2. Activate Virtual Environment
```bash
# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Run CIRIS in Development Mode
```bash
# Option 1: With hot reload (recommended)
python ciris_dev_server.py

# Option 2: Simple run
python main.py --mock-llm --adapter cli

# Option 3: Quick script
./scripts/run_dev.sh
```

## New Development Tools

### 🔥 Hot Reload Development Server
Automatically restarts CIRIS when you change code:
```bash
python ciris_dev_server.py --adapter cli
```

Features:
- Watches for Python file changes
- Automatic restart with color-coded output
- Preserves terminal history
- Configurable adapter (cli/api/discord)

### 🧪 Test Runner with File Watching
Automatically runs tests when files change:
```bash
python ciris_test_runner.py --watch
```

Features:
- Runs related tests when source files change
- Color-coded test output
- Session statistics
- Specific test targeting

### 🔍 Interactive Debug Tools
Debug database, trace requests, and analyze performance:
```bash
python ciris_debug_tools.py
```

Interactive commands:
- `tables` - Show all database tables
- `thoughts` - View recent thoughts
- `tasks` - View recent tasks  
- `trace <id>` - Trace request flow
- `perf` - Performance analysis
- `errors` - Check recent errors
- `sql` - Execute custom SQL

### 📦 Development Docker Setup
Simplified Docker configuration for development:
```bash
docker-compose -f docker-compose.dev.yml up
```

Features:
- Volume mounting for hot reload
- Optimized for development
- Pre-configured environment
- Exposed debugging ports

## VS Code Development

### Debug Configurations
Three pre-configured debug profiles:

1. **CIRIS CLI (Mock)** - Debug CLI adapter with mock LLM
2. **CIRIS API (Mock)** - Debug API adapter with mock LLM  
3. **Run Tests** - Debug test execution

Press `F5` in VS Code to start debugging!

### Recommended Extensions
- Python
- Pylance
- Python Test Explorer
- Docker
- GitLens

## Common Development Tasks

### Running Tests
```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=ciris_engine tests/

# Run specific test
pytest tests/unit/test_specific.py

# Watch mode
python ciris_test_runner.py --watch
```

### Database Management
```bash
# Reset database
rm -f data/ciris_dev.db
python main.py --mock-llm --adapter cli  # Will recreate

# Interactive database exploration
python ciris_debug_tools.py
```

### Clean Development Environment
```bash
# Clean everything
./scripts/clean_dev.sh

# Or manually
rm -rf venv/ data/ logs/ __pycache__/
```

## Environment Configuration

### Development Environment Variables
The setup creates `.env.development` with optimized settings:

```env
CIRIS_ENV=development
CIRIS_DEBUG=true
CIRIS_MOCK_LLM=true
PROCESSING_ROUND_DELAY=0.5  # Faster processing
THOUGHT_PROCESSING_TIMEOUT=10  # Shorter timeouts
```

### Mock LLM Commands
When using mock LLM, use `$` prefix:
- `$speak <message>` - Send a message
- `$recall <query>` - Search memory
- `$memorize <content>` - Store memory
- `$tool <tool_name> <params>` - Execute tool

## Troubleshooting

### "No such table" Error
```bash
# Database not initialized
rm -f data/ciris_dev.db
python main.py --mock-llm --adapter cli
```

### Python Version Error
```bash
# Need Python 3.11+
pyenv install 3.11.9
pyenv local 3.11.9
```

### Docker Issues
```bash
# Rebuild containers
docker-compose -f docker-compose.dev.yml build --no-cache
docker-compose -f docker-compose.dev.yml up
```

### Slow Response Times
Check `.env.development` for:
```env
PROCESSING_ROUND_DELAY=0.5
THOUGHT_PROCESSING_TIMEOUT=10
```

## Performance Tips

1. **Use Mock LLM** for development (instant responses)
2. **Reduce delays** via environment variables
3. **Run specific tests** instead of full suite
4. **Use hot reload** to avoid restart time
5. **Profile with debug tools** to find bottlenecks

## Project Structure

```
CIRISAgent/
├── ciris_engine/          # Core engine code
│   ├── logic/            # Business logic
│   ├── api/              # API endpoints
│   └── schemas/          # Pydantic models
├── ciris_modular_services/  # Service implementations
├── tests/                # Test suite
├── docs/                 # Documentation
├── scripts/              # Helper scripts
└── data/                 # Local database
```

## Development Workflow

1. **Create feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes with hot reload**
   ```bash
   python ciris_dev_server.py
   ```

3. **Run tests continuously**
   ```bash
   python ciris_test_runner.py --watch
   ```

4. **Debug issues**
   ```bash
   python ciris_debug_tools.py
   ```

5. **Commit and push**
   ```bash
   git add .
   git commit -m "feat: add awesome feature"
   git push origin feature/my-feature
   ```

## Getting Help

- Check `docs/` directory for architecture docs
- Run `python ciris_debug_tools.py` for debugging
- Review `CLAUDE.md` for codebase guidelines
- Ask in Discord community

## Full-Stack Development

### GUI + Backend Development

CIRIS includes a modern web GUI built with Next.js. Here's how to run the full stack:

#### Quick Start
```bash
# One-command full-stack setup
python dev_setup_fullstack.py

# Start both backend and frontend
python ciris_fullstack_server.py
```

This gives you:
- 🔧 Backend API on http://localhost:8080
- 🎨 Frontend GUI on http://localhost:3000
- 🔥 Hot reload for both Python and React code
- 📚 API documentation on http://localhost:8080/docs

#### Manual Setup
```bash
# Backend setup (if not done)
python dev_setup.py

# Frontend setup
cd CIRISGUI
pnpm install
pnpm dev

# In another terminal, start backend
python ciris_dev_server.py --adapter api
```

#### GUI Features
- **Dashboard**: Real-time system monitoring
- **Chat Interface**: Talk to CIRIS
- **API Explorer**: Test API endpoints
- **Memory Graph**: Visual memory exploration
- **System Status**: Service health monitoring
- **Audit Trail**: Activity tracking

#### Full-Stack Scripts
```bash
# Start everything
./scripts/dev_fullstack.sh

# Run all tests
./scripts/test_fullstack.sh

# Docker full-stack
docker-compose -f docker-compose.fullstack.yml up
```

#### VS Code Full-Stack Debugging
Press F5 and choose "Backend + Frontend" to debug both simultaneously!

## Next Steps

1. Run the setup: `python dev_setup.py` (backend only) or `python dev_setup_fullstack.py` (full-stack)
2. Start developing with hot reload
3. Explore the debug tools
4. Read architecture docs in `docs/`
5. Contribute your improvements!

Happy coding! 🚀