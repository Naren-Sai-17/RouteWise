# RouteWise AI

An agentic AI-powered trip planning system that orchestrates multiple specialized agents to create comprehensive travel itineraries.

## Overview

RouteWise AI is a demonstration of an agentic AI architecture for travel planning. The system uses a central orchestrator that coordinates specialized agents:

- **Central Agent**: Handles user intent parsing, state management, and agent routing
- **Flight Desk Agent**: Searches and recommends flight options using real-time data
- **Day Plan Agent**: Creates detailed daily itineraries based on user interests and preferences
- **Edit Agent**: Handles modifications and updates to existing trip plans

## Features

- Multi-agent orchestration for complex trip planning
- Real-time flight search integration
- AI-powered itinerary generation
- Flexible trip state management
- Comprehensive logging and tracing
- Support for various travel preferences (pace, budget, flight priorities)

## Project Structure

```
routewise_ai_demo/
├── __init__.py                 # Package initialization
├── orchestrator.py             # Main orchestrator class
├── schemas.py                  # Data schemas and validation
├── stage_logger.py             # Logging utilities
├── agents/                     # Agent implementations
│   ├── central_agent/
│   ├── day_plan_agent/
│   ├── edit_agent/
│   └── flight_desk_agent/
└── services/                   # External service integrations
    ├── groq_client.py          # Groq AI API client
    └── rapidapi_flights.py     # RapidAPI flights service
```

## Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd routewise-ai-demo
   ```
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables:

   ```bash
   export GROQ_API_KEY="your-groq-api-key"
   export RAPIDAPI_KEY="your-rapidapi-key"
   ```

## Dependencies

- Python 3.8+
- Groq API key (for AI processing)
- RapidAPI key (for flight data)

## Usage

```python
from routewise_ai_demo.orchestrator import RouteWiseDemoOrchestrator

# Initialize the orchestrator
orchestrator = RouteWiseDemoOrchestrator()

# Handle a user message
response = orchestrator.handle_message(
    message="Plan a 5-day trip to Tokyo from Mumbai next month",
    trip_state=None,
    session_id=None
)

print(response["assistant_message"])
print(response["trip_state"])
```

## API Reference

### RouteWiseDemoOrchestrator

#### `__init__(groq_client=None, flights_client=None)`

Initialize the orchestrator with optional custom clients.

#### `handle_message(message, trip_state, session_id)`

Process a user message and return a response with updated trip state.

**Parameters:**

- `message` (str): User's request message
- `trip_state` (dict): Current trip state (can be None for new trips)
- `session_id` (str): Session identifier (auto-generated if None)

**Returns:**

- `dict`: Response containing assistant message, updated trip state, and agent trace

## Configuration

The system supports various configuration options through environment variables:

- `GROQ_API_KEY`: Your Groq API key
- `GROQ_MODEL`: AI model to use (default: llama-3.3-70b-versatile)
- `RAPIDAPI_KEY`: Your RapidAPI key for flight data
