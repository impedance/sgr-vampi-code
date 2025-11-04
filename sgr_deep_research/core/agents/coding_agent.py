import logging
import os
from datetime import datetime
from typing import Type

from openai import pydantic_function_tool
from openai.types.chat import ChatCompletionFunctionToolParam

from sgr_deep_research.core.agents.base_agent import BaseAgent
from sgr_deep_research.core.models import AgentStatesEnum, CodingContext
from sgr_deep_research.core.tools import (
    BaseTool,
    ClarificationTool,
    FinalAnswerTool,
    ReasoningTool,
    coding_agent_tools,
)
from sgr_deep_research.settings import get_config

config = get_config()
logger = logging.getLogger(__name__)


class CodingAgent(BaseAgent):
    """Terminal coding agent for repository work using ReAct + PlanAct approach.
    
    This agent:
    - Works with local repository files
    - Has no iteration limits (can work indefinitely)
    - Truncates conversation history intelligently (keeps tool calls)
    - Supports continuous dialogue with user
    - Uses cheap models effectively
    """
    
    name: str = "coding_agent"
    
    def __init__(
        self,
        task: str,
        workspace_path: str = ".",
        toolkit: list[Type[BaseTool]] | None = None,
        max_clarifications: int = 5,
        max_history_messages: int = 80,
    ):
        # Don't limit iterations - coding agent can work indefinitely
        super().__init__(
            task=task,
            toolkit=toolkit,
            max_iterations=999999,  # Effectively unlimited
            max_clarifications=max_clarifications,
        )
        
        self.toolkit = [
            ClarificationTool,
            ReasoningTool,
            FinalAnswerTool,
            *coding_agent_tools,
            *(toolkit if toolkit else []),
        ]
        
        # Replace ResearchContext with CodingContext
        self._context = CodingContext(workspace_path=os.path.abspath(workspace_path))
        self.max_history_messages = max_history_messages
        
        self.logger.info(f"🔧 Coding agent initialized for workspace: {self._context.workspace_path}")
    
    def _truncate_conversation_history(self):
        """Intelligently truncate conversation history while preserving tool calls.
        
        Strategy:
        - Always keep system message (if present)
        - Always keep recent messages (last 20)
        - Keep all tool call + tool result pairs to maintain context
        - Remove old user/assistant text messages
        """
        if len(self.conversation) <= self.max_history_messages:
            return
        
        logger.info(f"📝 Truncating history: {len(self.conversation)} → {self.max_history_messages} messages")
        
        # Separate messages by importance
        system_messages = []
        tool_pairs = []  # (assistant with tool_calls, tool result)
        recent_messages = []
        old_messages = []
        
        i = 0
        while i < len(self.conversation):
            msg = self.conversation[i]
            
            # Keep system messages
            if msg.get("role") == "system":
                system_messages.append(msg)
                i += 1
                continue
            
            # Keep recent messages (last 20)
            if i >= len(self.conversation) - 20:
                recent_messages.append(msg)
                i += 1
                continue
            
            # Detect and keep tool call pairs
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Found assistant message with tool calls
                tool_pair = [msg]
                # Look for corresponding tool results
                j = i + 1
                while j < len(self.conversation) and self.conversation[j].get("role") == "tool":
                    tool_pair.append(self.conversation[j])
                    j += 1
                tool_pairs.extend(tool_pair)
                i = j
                continue
            
            # Everything else goes to old_messages
            old_messages.append(msg)
            i += 1
        
        # Calculate how many messages we can keep
        essential_count = len(system_messages) + len(tool_pairs) + len(recent_messages)
        
        if essential_count > self.max_history_messages:
            # If even essential messages exceed limit, prioritize recent + system
            self.conversation = system_messages + recent_messages
            logger.warning(f"⚠️ History truncation aggressive: only system + recent kept")
        else:
            # We have room - keep system + some tool pairs + recent
            available_slots = self.max_history_messages - len(system_messages) - len(recent_messages)
            kept_tool_pairs = tool_pairs[-available_slots:] if available_slots > 0 else []
            self.conversation = system_messages + kept_tool_pairs + recent_messages
        
        logger.info(f"✅ History truncated to {len(self.conversation)} messages")
    
    def _log_reasoning(self, result: ReasoningTool) -> None:
        """Override to use CodingContext fields."""
        next_step = result.remaining_steps[0] if result.remaining_steps else "Completing"
        self.logger.info(
            f"""
    ###############################################
    🤖 CODING AGENT REASONING:
       🧠 Reasoning Steps: {result.reasoning_steps}
       📊 Current Situation: '{result.current_situation[:200]}...'
       📋 Plan Status: '{result.plan_status[:200]}...'
       🔍 Clarifications Done: {self._context.clarifications_used}
       ✅ Enough Data: {result.enough_data}
       📝 Remaining Steps: {result.remaining_steps}
       🏁 Task Completed: {result.task_completed}
       ➡️ Next Step: {next_step}
    ###############################################"""
        )
        self.log.append(
            {
                "step_number": self._context.iteration,
                "timestamp": datetime.now().isoformat(),
                "step_type": "reasoning",
                "agent_reasoning": result.model_dump(),
            }
        )
    
    async def _prepare_context(self) -> list[dict]:
        """Prepare conversation context with coding agent system prompt."""
        from sgr_deep_research.core.prompts import PromptLoader
        
        return [
            {
                "role": "system",
                "content": PromptLoader.get_coding_agent_prompt(self.toolkit, self._context.workspace_path)
            },
            *self.conversation,
        ]
    
    async def _prepare_tools(self) -> list[ChatCompletionFunctionToolParam]:
        """Prepare available tools for current agent state."""
        tools = set(self.toolkit)
        
        # Remove clarification tool if limit reached
        if self._context.clarifications_used >= self.max_clarifications:
            tools -= {ClarificationTool}
        
        return [pydantic_function_tool(tool, name=tool.tool_name, description="") for tool in tools]
    
    async def _reasoning_phase(self) -> ReasoningTool:
        """First phase: ReasoningTool to understand current situation."""
        async with self.openai_client.chat.completions.stream(
            model=config.openai.model,
            messages=await self._prepare_context(),
            max_tokens=config.openai.max_tokens,
            temperature=config.openai.temperature,
            tools=await self._prepare_tools(),
            tool_choice={"type": "function", "function": {"name": ReasoningTool.tool_name}},
        ) as stream:
            async for event in stream:
                if event.type == "chunk":
                    self.streaming_generator.add_chunk(event.chunk)
            
            reasoning: ReasoningTool = (
                (await stream.get_final_completion()).choices[0].message.tool_calls[0].function.parsed_arguments
            )
        
        self.conversation.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "type": "function",
                        "id": f"{self._context.iteration}-reasoning",
                        "function": {
                            "name": reasoning.tool_name,
                            "arguments": reasoning.model_dump_json(),
                        },
                    }
                ],
            }
        )
        
        tool_call_result = await reasoning(self._context)
        self.conversation.append(
            {"role": "tool", "content": tool_call_result, "tool_call_id": f"{self._context.iteration}-reasoning"}
        )
        
        self._log_reasoning(reasoning)
        return reasoning
    
    async def _select_action_phase(self, reasoning: ReasoningTool) -> BaseTool:
        """Second phase: Select and parse action tool."""
        async with self.openai_client.chat.completions.stream(
            model=config.openai.model,
            messages=await self._prepare_context(),
            max_tokens=config.openai.max_tokens,
            temperature=config.openai.temperature,
            tools=await self._prepare_tools(),
            tool_choice="required",
        ) as stream:
            async for event in stream:
                if event.type == "chunk":
                    self.streaming_generator.add_chunk(event.chunk)
        
        completion = await stream.get_final_completion()
        
        try:
            tool = completion.choices[0].message.tool_calls[0].function.parsed_arguments
        except (IndexError, AttributeError, TypeError):
            # LLM returned text response - treat as completion
            final_content = completion.choices[0].message.content or "Task completed"
            tool = FinalAnswerTool(
                reasoning="Agent decided to complete",
                completed_steps=[final_content],
                answer=final_content,
                status=AgentStatesEnum.COMPLETED,
            )
        
        if not isinstance(tool, BaseTool):
            raise ValueError("Selected tool is not a valid BaseTool instance")
        
        self.conversation.append(
            {
                "role": "assistant",
                "content": reasoning.remaining_steps[0] if reasoning.remaining_steps else "Processing",
                "tool_calls": [
                    {
                        "type": "function",
                        "id": f"{self._context.iteration}-action",
                        "function": {
                            "name": tool.tool_name,
                            "arguments": tool.model_dump_json(),
                        },
                    }
                ],
            }
        )
        
        self.streaming_generator.add_tool_call(
            f"{self._context.iteration}-action", tool.tool_name, tool.model_dump_json()
        )
        
        return tool
    
    async def _action_phase(self, tool: BaseTool) -> str:
        """Execute selected tool."""
        result = await tool(self._context)
        
        self.conversation.append(
            {
                "role": "tool",
                "content": result,
                "tool_call_id": f"{self._context.iteration}-action",
            }
        )
        
        # Stream tool result to user
        self.streaming_generator.add_chunk_from_str(f"\n📋 Result:\n{result[:2000]}\n")
        
        self._log_tool_execution(tool, result)
        
        return result
    
    async def execute(self):
        """Main execution loop without iteration limits."""
        self.logger.info(f"🚀 Starting coding agent for task: '{self.task}'")
        
        from sgr_deep_research.core.prompts import PromptLoader
        
        self.conversation.extend(
            [
                {
                    "role": "user",
                    "content": PromptLoader.get_coding_agent_initial_request(self.task),
                }
            ]
        )
        
        try:
            while self._context.state not in AgentStatesEnum.FINISH_STATES.value:
                self._context.iteration += 1
                self.logger.info(f"🔄 Iteration {self._context.iteration}")
                
                # Truncate history before each iteration
                self._truncate_conversation_history()
                
                # ReAct cycle
                reasoning = await self._reasoning_phase()
                self._context.current_step_reasoning = reasoning
                
                action_tool = await self._select_action_phase(reasoning)
                await self._action_phase(action_tool)
                
                # Handle clarifications
                if isinstance(action_tool, ClarificationTool):
                    self.logger.info("⏸️ Paused for clarification")
                    self._context.state = AgentStatesEnum.WAITING_FOR_CLARIFICATION
                    self._context.clarification_received.clear()
                    await self._context.clarification_received.wait()
                    continue
        
        except Exception as e:
            self.logger.error(f"❌ Agent execution error: {str(e)}")
            self._context.state = AgentStatesEnum.FAILED
            import traceback
            traceback.print_exc()
        finally:
            if self.streaming_generator is not None:
                self.streaming_generator.finish()
            self._save_agent_log()

