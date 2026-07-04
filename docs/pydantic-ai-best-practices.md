# Pydantic AI — Best Practices

## 1. Architecture and Agent Management

**Reuse Agents like FastAPI Apps:** Instantiate agents globally to maximize reuse and efficiency across your application.

```python
# Instantiate once at the module level
support_agent = Agent('openai:gpt-5.2', name='support_desk')
```

**Leverage Capabilities for Modularity:** Use `Capability` to bundle related tools and instructions into reusable units.

```python
from pydantic_ai.capabilities import Capability

useful_tools = Capability(
    id='math_pack',
    instructions='Always show your work.',
    tools=[add_func, multiply_func]
)
agent = Agent('openai:gpt-5.2', capabilities=[useful_tools])
```

**Adopt Declarative Agent Specs:** Separate configuration from code by defining agents in YAML/JSON.

```yaml
# agent.yaml
model: anthropic:claude-3-5-sonnet-latest
instructions: "You are a helpful assistant."
capabilities:
  - WebSearch: {local: duckduckgo}
```

**Use Pydantic Graph for Complex Flows:** Build type-safe finite state machines for workflows that standard control flow can't easily handle.

```python
from pydantic_graph import BaseNode, GraphBuilder

@dataclass
class MyNode(BaseNode[MyState]):
    async def run(self, ctx) -> NextNode | End[int]:
        return NextNode()
```

**Manage Dependencies Type-Safely:** Define a dataclass for `deps_type` to enable full IDE type checking.

```python
@dataclass
class MyDeps:
    db: DatabaseConn
    api_key: str

agent = Agent('openai:gpt-5.2', deps_type=MyDeps)
```

## 2. Model Configuration and Prompting

**Prefer Instructions over System Prompts:** Use `instructions` for per-request dynamic guidance to enable better provider-side caching.

```python
agent = Agent('openai:gpt-5.2', instructions="Be concise.")

# Dynamic instructions are fresh on every run
@agent.instructions
def add_user(ctx: RunContext[User]):
    return f"User is {ctx.deps.name}"
```

**Implement Prompt Caching:** Use provider-specific settings to reduce latency and costs for large contexts.

```python
from pydantic_ai.models.anthropic import AnthropicModelSettings

settings = AnthropicModelSettings(anthropic_cache=True)
result = agent.run_sync("Prompt...", model_settings=settings)
```

**Use Provider-Prefixed Model Names:** Always prefix model names to let the framework handle selection automatically.

```python
# Framework automatically selects the correct Provider and Profile
agent = Agent('openai:gpt-5.2')
```

**Configure Fallback Models:** Automatically switch providers if the primary model fails or returns truncated responses.

```python
from pydantic_ai.models.fallback import FallbackModel

model = FallbackModel(['openai:gpt-5.2', 'anthropic:claude-3-5-sonnet-latest'])
agent = Agent(model)
```

## 3. Tool Development and Execution

**Document Tools with Docstrings:** Use standard docstrings for automatic schema generation.

```python
@agent.tool_plain
def get_weather(city: str) -> str:
    """Get weather for a city.
    Args:
        city: The name of the city.
    """
    return "Sunny"
```

**Utilize Tool Search for Large Catalogs:** Mark tools with `defer_loading=True` to hide them until needed.

```python
@agent.tool_plain(defer_loading=True)
def specialized_calc(data: str):
    """Perform a rare calculation."""

# Use ToolSearch to discover them dynamically
agent = Agent(capabilities=[ToolSearch()])
```

**Control Tool Concurrency:** Use `sequential=True` for operations that should not overlap, like database writes.

```python
@agent.tool_plain(sequential=True)
def write_db(data: str):
    """Writes to database alone."""
```

**Prefer Provider-Adaptive Capabilities:** Use built-in capabilities that automatically choose the best implementation for the active model.

```python
from pydantic_ai.capabilities import WebSearch

# Uses Anthropic native search or falls back to DuckDuckGo locally
agent = Agent(capabilities=[WebSearch(local='duckduckgo')])
```

## 4. Reliable Output and Error Handling

**Enforce Structured Output:** Use a Pydantic `BaseModel` to guarantee the model's response matches your schema.

```python
class UserInfo(BaseModel):
    name: str
    age: int

agent = Agent('openai:gpt-5.2', output_type=UserInfo)
```

**Implement Self-Correction Loops:** Raise `ModelRetry` to provide feedback and ask the model to fix its own mistakes.

```python
@agent.tool_plain
def validate_code(code: str):
    if "eval(" in code:
        raise ModelRetry("Security risk: eval() is not allowed. Try again.")
```

**Handle Partial Output During Streaming:** Check the `partial_output` flag in validators to avoid processing incomplete data.

```python
@agent.output_validator
def check_result(ctx: RunContext, output: MyModel):
    if not ctx.partial_output:
        # Perform expensive final validation here
        pass
    return output
```

## 5. Observability and Systematic Testing

**Enable Instrumentation Early:** Use `logfire` to trace every step of your agent's run.

```python
import logfire

logfire.configure()
logfire.instrument_pydantic_ai()
```

**Strict Test Environment:** Block real model requests in your test suite to prevent accidental costs.

```python
from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False
```

**Use Mock Models for Integration:** Use `TestModel` for schema verification or `FunctionModel` for logic testing.

```python
from pydantic_ai.models.test import TestModel

with agent.override(model=TestModel()):
    result = agent.run_sync("test")
```

**Build "Golden Datasets":** Use Pydantic Evals to systematically test performance against a ground truth.

```python
from pydantic_evals import Case, Dataset

dataset = Dataset(name='q_a', cases=[Case(inputs='Hi', expected_output='Hello')])
report = dataset.evaluate_sync(my_task)
```

## 6. Production Reliability (Durable Execution)

**Maintain Stable Agent Identities:** Give agents stable names so durable frameworks can correctly resume runs.

```python
agent = Agent('openai:gpt-5.2', name='customer_outreach_v1')
```

**Ensure Pickle-able Dependencies:** Verify all dependencies can be serialized for durable checkpoints.

```python
# Simple dataclasses are easily picklable for DBOS/Temporal
@dataclass
class DurableDeps:
    user_id: int
```

## 7. Governance Layer Practices

**Financial Governance:** Set `UsageLimits` to cap tokens and model turns per run.

```python
from pydantic_ai.usage import UsageLimits

limits = UsageLimits(request_limit=5, input_tokens_limit=10000)
result = agent.run_sync("Hi", usage_limits=limits)
```

**Operational Safety (Guardrails):** Implement a custom capability to redact sensitive info or block dangerous tools.

```python
class PIIRedactionGuardrail(AbstractCapability):
    async def after_model_request(self, ctx, *, request_context, response):
        # Redact email/phone from response.parts
        return response
```

**Human-in-the-Loop (HITL):** Require explicit approval for high-risk tools.

```python
@agent.tool_plain(requires_approval=True)
def delete_account(user_id: int):
    return f"Account {user_id} deleted."
```

**Security & Privacy (Sanitization):** Use `UIAdapter` to sanitize untrusted messages from clients.

```python
# Automatically strips dangerous FileUrls from client history
sanitized = VercelAIAdapter.sanitize_messages(client_messages)
```

**Audit Compliance:** Correlate all logs to a single `conversation_id` for full session auditing.

```python
agent.run_sync("User prompt", conversation_id="session_xyz_789")
```
