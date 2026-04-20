# RouteWise AI: Agentic GenAI Trip Planner

## Slide 1: What This Demo Shows

RouteWise AI is a generative AI agentic system, not a single travel chatbot.

The demo shows how an LLM-based product can:

- Interpret an ambiguous natural-language request
- Convert it into structured state
- Route work across specialized agents
- Use tools only when prerequisites are satisfied
- Generate an itinerary from structured context
- Apply follow-up edits without rebuilding the whole trip
- Expose the reasoning path through an agent trace

The important part is the agentic architecture around the LLM.

---

## Slide 2: Agentic System Pattern

The core loop is:

```text
User instruction
  -> Central Agent interprets intent
  -> shared trip_state is updated
  -> orchestrator chooses next agent
  -> specialist agent executes
  -> tool results or generated plan update state
  -> response + agent_trace returned
```

The LLM is used as a bounded reasoning component.

It does not own:

- The full control flow
- Tool invocation permissions
- State persistence
- Error recovery behavior
- Output rendering

Those responsibilities live in the deterministic control plane.

---

## Slide 3: Agent Graph

```text
                         user message
                              |
                              v
                    +--------------------+
                    | Central Agent      |
                    | intent + routing   |
                    +---------+----------+
                              |
        +---------------------+----------------------+
        |                                            |
 missing required fields                       valid base state
        |                                            |
        v                                            v
 clarification response              +---------------+---------------+
                                     |                               |
                                     v                               v
                          +--------------------+        +--------------------+
                          | Flight Desk Agent  |        | Edit Agent         |
                          | tool reasoning     |        | state transform    |
                          +---------+----------+        +---------+----------+
                                    |                             |
                                    v                             v
                          +--------------------+          updated trip_state
                          | Day Plan Agent     |
                          | itinerary synthesis|
                          +---------+----------+
                                    |
                                    v
                            final trip_state
```

The graph is intentionally small so the agent mechanics are visible.

---

## Slide 4: Agent Responsibilities

| Agent | Main job | LLM role | Output |
|---|---|---|---|
| Central Agent | Understand request and route | semantic parsing + decisioning | state patch, missing fields, orchestration |
| Flight Desk Agent | Reason over flight tools | no LLM generation | ranked flight context |
| Day Plan Agent | Build itinerary | constrained synthesis | title, summary, itinerary, budget notes |
| Edit Agent | Modify existing plan | state transformation | updated trip_state and edit summary |

This separation keeps each prompt narrow.

The system is not asking one model to simultaneously parse, search, plan, edit, and explain everything.

---

## Slide 5: Shared State As Agent Memory

Agents communicate through a structured `trip_state`, not long natural-language handoffs.

```json
{
  "origin": "SFO",
  "destination": "Tokyo",
  "start_date": "2026-05-10",
  "end_date": "",
  "duration_days": 4,
  "travelers": 2,
  "interests": ["food", "anime"],
  "budget": 2500,
  "budget_currency": "USD",
  "pace": "balanced",
  "flight_preferences": {},
  "flight_search": {},
  "itinerary": [],
  "budget_notes": "",
  "last_edit_summary": ""
}
```

This state acts as the working memory for the agent system.

Benefits:

- Small prompts
- Inspectable intermediate state
- Easier validation
- Localized edits
- Lower risk of conversation drift

---

## Slide 6: LLM Gateway Contract

Every LLM-backed agent uses the same contract shape:

```text
system prompt:
  role, task boundary, schema, rules

user payload:
  JSON serialized state and instruction

model request:
  response_format = json_object
  agent-specific temperature
  agent-specific token budget

post-processing:
  parse JSON
  coerce to allowed state schema
  ignore unknown state fields
```

The model is useful for interpretation and synthesis, but the system only trusts parsed JSON objects.

---

## Slide 7: Prompt Anatomy

Each agent prompt contains five technical sections.

```text
1. Identity
   "You are RouteWise AI's Central Agent..."

2. Task boundary
   "Extract travel intent and decide the next agent handoff."

3. Required JSON shape
   trip_state_patch, missing_fields, is_edit_request, orchestration

4. Behavioral rules
   ISO dates, flight preference mapping, edit detection, missing field policy

5. Structured payload
   current_date, current_trip_state, user_message
```

This converts a conversational LLM into a typed reasoning step.

---

## Slide 8: Central Agent: Semantic Router

The Central Agent is the first LLM call in each turn.

It extracts:

- Origin and destination
- Start date, end date, or duration
- Traveler count
- Interests
- Budget and currency
- Trip pace
- Flight preferences
- Whether the user is asking for a new plan or an edit

It also decides the candidate handoff:

```json
{
  "missing_fields": [],
  "is_edit_request": false,
  "orchestration": ["flight_desk_agent", "day_plan_agent"]
}
```

This is agentic routing, not just entity extraction.

---

## Slide 9: Central Agent Output Contract

The Central Agent returns a patch, not a full new state.

```json
{
  "trip_state_patch": {
    "origin": "SFO",
    "destination": "Tokyo",
    "start_date": "2026-05-10",
    "duration_days": 4,
    "travelers": 2,
    "interests": ["food", "anime"],
    "budget": 2500,
    "flight_preferences": {
      "priority": "cheap",
      "flexible_dates": true,
      "flex_window_days": 3,
      "max_stops": null,
      "cabin_class": null
    }
  }
}
```

The patch is merged into the existing `trip_state`.

Unknown fields are ignored, which limits prompt injection and accidental schema drift.

---

## Slide 10: Central Agent Guardrails

The Central Agent can interpret intent, but it cannot run the whole system.

Guardrails:

- Destination is required for a base itinerary
- Dates or duration are required for a base itinerary
- Origin is useful for flights but does not block day planning
- Relative dates are normalized using current date context
- "cheap", "budget", "best fare", or "flexible" map to flexible flight search
- "nonstop" maps to `max_stops = 0`
- Edit requests are only valid when an itinerary already exists

This keeps the routing layer strict while still letting language stay natural.

---

## Slide 11: Orchestrator Control Policy

The orchestrator is the deterministic control plane around the agents.

```text
1. Coerce incoming trip_state
2. Run Central Agent
3. If required fields are missing, stop and ask a question
4. If edit request is valid, run Edit Agent
5. Otherwise run Flight Desk Agent
6. If day-plan inputs exist, run Day Plan Agent
7. Return assistant_message, trip_state, and agent_trace
```

The LLM can recommend orchestration, but the orchestrator enforces it.

This avoids an unrestricted "LLM calls anything" architecture.

---

## Slide 12: Flight Desk Agent: Tool Reasoning

The Flight Desk Agent is a specialist tool-using agent.

It does not generate prose with an LLM.

It reasons over structured state:

```text
if origin, destination, or start_date is missing:
    skip live flight search

elif cheap priority or flexible dates:
    call calendar_tool
    select best date candidate
    call flight_list_tool for selected dates

else:
    call flight_list_tool for exact dates
```

This is still agentic because the agent selects a tool path based on goals and state.

---

## Slide 13: Flight Calendar Tool

`calendar_tool` searches a flexible date window.

Example:

```text
requested start_date: 2026-05-10
flex_window_days: 3
calendar scan: 2026-05-07 through 2026-05-13
```

The tool normalizes raw price-calendar data into a small candidate list:

```json
{
  "departure_date": "2026-05-08",
  "return_date": "2026-05-12",
  "price": 510,
  "currency": "USD",
  "airline": "Example Air",
  "stops": 1,
  "total_duration_minutes": 690
}
```

The selected calendar candidate becomes the input to exact flight search.

---

## Slide 14: Calendar Selection Heuristic

The Flight Desk Agent ranks calendar candidates with a deterministic heuristic.

```text
rank by:
  1. lowest normalized price
  2. shortest total duration
  3. stable date ordering
```

The agent writes both the selected pick and the reasoning into state:

```json
{
  "strategy": "calendar_then_flight_list",
  "reasoning": "Calendar prices were ranked by lowest fare before fetching exact flights.",
  "selected_calendar_pick": {},
  "tool_calls": [
    { "name": "calendar_tool" },
    { "name": "flight_list_tool" }
  ]
}
```

The reasoning is explicit and inspectable.

---

## Slide 15: Flight List Tool

`flight_list_tool` retrieves exact flight cards for a chosen date pair.

Normalized option:

```json
{
  "origin": "SFO",
  "destination": "HND",
  "departure_date": "2026-05-08",
  "arrival_date": "2026-05-12",
  "airline": "Example Air",
  "price": 540,
  "currency": "USD",
  "duration_minutes": 690,
  "stops": 1,
  "segments": []
}
```

Exact options are ranked by:

```text
1. price
2. duration
3. number of stops
```

The Day Plan Agent can use this as context, but it cannot claim the flight was booked.

---

## Slide 16: Day Plan Agent: Generative Synthesis

The Day Plan Agent is where the system uses LLM generation most directly.

Input:

- Destination
- Dates or duration
- Interests
- Pace
- Budget
- Traveler count
- Flight context when available

Output:

```json
{
  "title": "4-Day Tokyo Food and Anime Trip",
  "summary": "Compact trip overview.",
  "itinerary": [
    {
      "day": 1,
      "theme": "Arrival and Shibuya",
      "morning": "Arrival buffer and hotel drop-off",
      "afternoon": "Shibuya crossing and shops",
      "evening": "Ramen and arcades",
      "estimated_cost": "USD 80-120",
      "pace": "balanced"
    }
  ],
  "budget_notes": "Flight price is planning context only."
}
```

---

## Slide 17: Day Plan Constraints

The Day Plan Agent is constrained because itinerary generation is open ended.

Rules:

- Generate no more than 6 displayed days
- Use repeated day structure: morning, afternoon, evening
- Include estimated cost and pace
- Use flight search results only as planning context
- Avoid booking, payment, reservation, or ticket claims
- Keep the response compact enough for human review

The LLM is still creative, but it is creative inside a structured output frame.

---

## Slide 18: Edit Agent: Stateful Transformation

The Edit Agent handles follow-up turns.

Example:

```text
"Make day 2 slower and add museums."
```

Input:

```json
{
  "current_trip_state": {},
  "edit_request": "Make day 2 slower and add museums."
}
```

Output:

```json
{
  "trip_state": {},
  "assistant_message": "I slowed down day 2 and added museum time.",
  "edit_summary": "Updated day 2 pace and activities."
}
```

The model performs a transformation over existing state instead of regenerating a disconnected plan.

---

## Slide 19: Multi-Turn Agent Memory

RouteWise AI is turn-based, but not stateless.

```text
Turn 1:
  user asks for a Tokyo trip
  Central Agent extracts state
  Flight Desk Agent adds flight context
  Day Plan Agent generates itinerary

Turn 2:
  user asks to make day 2 slower
  Central Agent detects edit intent
  Edit Agent modifies existing trip_state
```

The important distinction:

- Chatbot pattern: answer each prompt independently
- Agentic pattern: preserve state and apply targeted changes

---

## Slide 20: Agent Trace

Every turn returns an `agent_trace`.

```json
[
  {
    "agent_id": "central_agent",
    "status": "done",
    "message": "Central Agent normalized intent and selected the next handoff.",
    "details": {
      "missing_fields": [],
      "is_edit_request": false,
      "orchestration": ["flight_desk_agent", "day_plan_agent"]
    }
  },
  {
    "agent_id": "flight_desk_agent",
    "status": "done",
    "message": "Used calendar_tool, then flight_list_tool."
  }
]
```

The trace turns hidden model and tool behavior into an inspectable reasoning path.

---

## Slide 21: Observability Questions The Trace Answers

The trace answers operational questions that a plain chatbot cannot answer.

- Which agent ran first?
- Did the Central Agent classify this as planning or editing?
- Which fields were missing?
- Did the flight agent skip, fail, or complete?
- Which tool strategy was selected?
- Did itinerary generation happen?
- Where should debugging or prompt tuning focus?

For agentic systems, traceability is part of the product behavior.

---

## Slide 22: Failure Semantics

The system distinguishes failure classes instead of collapsing into one generic error.

| Failure | Behavior |
|---|---|
| Missing destination | Ask clarification |
| Missing dates and duration | Ask clarification |
| Missing origin | Skip flights, continue day plan |
| Flight API unavailable | Mark flight search skipped |
| Flight tool error | Mark flight search error, continue itinerary |
| Invalid LLM JSON | Reject agent output because state cannot be trusted |
| Edit request before itinerary exists | Treat as planning or ask for required fields |

The system can degrade gracefully because state, tools, and generation are separated.

---

## Slide 23: Model Settings By Agent

Different agents use different model behavior.

| Agent | LLM task | Temperature | Max tokens | Why |
|---|---|---:|---:|---|
| Central Agent | extraction + routing | 0.1 | 1600 | stable structured parsing |
| Day Plan Agent | itinerary synthesis | 0.35 | 2400 | controlled generation |
| Edit Agent | state transformation | 0.25 | 2400 | preserve state while changing targeted parts |
| Flight Desk Agent | none | n/a | n/a | deterministic tool policy |

Practical agentic systems do not need one universal model behavior for every step.

---

## Slide 24: LLM Risk Controls

The demo uses several layers to reduce LLM risk.

Model request controls:

- JSON object response format
- Low temperature for parsing and routing
- Explicit role-specific schema
- Structured JSON user payload

State controls:

- Coerce every incoming state into a default schema
- Merge patches instead of blindly replacing state
- Ignore unknown fields
- Validate required planning fields

Behavior controls:

- Tools are called by code, not arbitrary model text
- Flight search requires origin, destination, and date
- Day Plan Agent cannot claim bookings
- Edit Agent must preserve unrelated fields

---

## Slide 25: End-To-End Reasoning Example

User prompt:

```text
Plan a 4 day Tokyo trip from SFO starting 2026-05-10
for 2 people, food and anime, under $2500.
Find cheap flights if possible.
```

Reasoning path:

```text
Central Agent:
  extracts SFO, Tokyo, date, duration, travelers, interests, budget
  sets flight_preferences.priority = cheap
  routes to Flight Desk Agent and Day Plan Agent

Flight Desk Agent:
  runs calendar_tool over flexible date window
  selects cheapest candidate date
  runs flight_list_tool for exact options
  writes ranked flight context into trip_state

Day Plan Agent:
  generates structured itinerary
  uses interests, budget, pace, and flight context
```

The final answer is generated, but the path to it is structured and inspectable.

---

## Slide 26: Why This Is Agentic

This is agentic because the system has:

- Specialized agents with separate responsibilities
- A deterministic control plane
- Shared structured memory
- State-dependent tool choice
- LLM calls constrained by schemas
- Iterative edits over existing state
- Explicit traces of agent behavior
- Failure isolation across parsing, tools, and generation

It is not just "LLM writes a travel plan."

The agentic value is the reasoning pipeline around the LLM.

---

## Slide 27: Core Takeaway

The RouteWise AI pattern is:

```text
bounded LLM reasoning
+ typed shared state
+ deterministic orchestration
+ specialist tool agents
+ constrained generation
+ multi-turn state updates
+ traceable execution
```

That combination is the foundation of practical generative AI agent systems.
