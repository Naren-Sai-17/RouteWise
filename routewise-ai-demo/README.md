# RouteWise AI Course Demo

Standalone toy version of an agentic AI trip planner.

## Run

```bash
cd /Users/mutyalarupesh/Desktop/airial/routewise-ai-demo
cp .env.example .env
# Fill GROQ_API_KEY. RAPIDAPI_KEY is optional for live flight cards.
./start.sh
```

Open:

```text
http://127.0.0.1:5055/agentic-trip-planner
```

## API Key Boundary

This demo reads only:

- `GROQ_API_KEY`
- `GROQ_MODEL`
- `RAPIDAPI_KEY`
- `ROUTEWISE_HOST`
- `ROUTEWISE_PORT`

It does not import the Airial frontend or backend app, does not use `fetchWithAuth`, and does not read OpenAI, Anthropic, Gemini, Azure, Google, Amadeus, or Booking RapidAPI keys.

## Structure

- `routewise_ai_demo/agents/central_agent`
- `routewise_ai_demo/agents/flight_desk_agent`
- `routewise_ai_demo/agents/day_plan_agent`
- `routewise_ai_demo/agents/edit_agent`
- `routewise_ai_demo/services`
- `web`

The Flight Desk Agent has two explicit tools:

- `calendar_tool`: scans a flexible date window for cheaper candidates.
- `flight_list_tool`: fetches exact flight cards for the selected dates and ranks by price, duration, and stops.
