

from typing import Literal, Type

from openai import pydantic_function_tool
from openai.types.chat import ChatCompletionFunctionToolParam

from sgr_deep_research.core.agents.sgr_agent import SGRResearchAgent
from sgr_deep_research.core.models import AgentStatesEnum
from sgr_deep_research.core.prompts import PromptLoader
from sgr_deep_research.core.tools import (
    BaseTool,
    ClarificationTool,
    FinalAnswerTool,
    ReasoningTool,
    coding_agent_tools,
    system_agent_tools,
)
from sgr_deep_research.settings import get_config

config = get_config()


class SGRVampiCodeAgent(SGRResearchAgent):
    """Coding agent with continuous dialogue and conversation truncation.
    
    Features:
    - Uses SGR (Schema-Guided Reasoning) approach with ReasoningTool
    - Supports continuous multi-turn dialogue
    - Automatically truncates conversation to keep last 80 messages
    - Specialized for repository operations and coding tasks
    """

    name: str = "sgr_vampi_code"

    def __init__(
        self,
        task: str,
        toolkit: list[Type[BaseTool]] | None = None,
        max_clarifications: int = 5,
        max_iterations: int = 20,
        max_conversation_messages: int = 80,
    ):
        super().__init__(
            task=task,
            toolkit=toolkit,
            max_clarifications=max_clarifications,
            max_iterations=max_iterations,
            max_searches=0,  # No web searches for coding agent
        )
        self.toolkit = [
            *system_agent_tools,
            *coding_agent_tools,
            *(toolkit if toolkit else []),
        ]
        self.tool_choice: Literal["required"] = "required"
        self.max_conversation_messages = max_conversation_messages
        self.continuous_mode = False  # Flag to track if this is continuing a conversation

    def _truncate_conversation(self):
        """Truncate conversation to keep last N messages while preserving system prompt.
        
        Strategy:
        - Always keep the initial user task message
        - Keep the most recent max_conversation_messages messages
        - Preserve important context like clarifications
        - Maintain conversation coherence
        """
        if len(self.conversation) <= self.max_conversation_messages:
            return
        
        # Find important messages to preserve
        initial_user_msg = None
        clarification_msgs = []
        
        for i, msg in enumerate(self.conversation):
            if msg.get("role") == "user" and not initial_user_msg:
                initial_user_msg = (i, msg)
            
            # Preserve clarification-related messages
            content = msg.get("content", "")
            if "clarification" in content.lower() or "уточнение" in content.lower():
                clarification_msgs.append((i, msg))
        
        # Calculate how many recent messages to keep
        preserve_count = 1 if initial_user_msg else 0
        preserve_count += len(clarification_msgs)
        
        recent_messages_count = max(
            self.max_conversation_messages - preserve_count,
            self.max_conversation_messages // 2  # Keep at least half of limit as recent messages
        )
        
        # Build truncated conversation
        truncated = []
        
        # Add initial user message if exists
        if initial_user_msg:
            truncated.append(initial_user_msg[1])
        
        # Add truncation marker
        if len(self.conversation) > self.max_conversation_messages:
            truncated.append({
                "role": "system",
                "content": f"[Conversation truncated. Showing recent {recent_messages_count} messages from {len(self.conversation)} total]"
            })
        
        # Add recent messages
        recent_messages = self.conversation[-recent_messages_count:]
        truncated.extend(recent_messages)
        
        self.conversation = truncated
        self.logger.info(
            f"🔄 Conversation truncated: {len(self.conversation)} messages "
            f"(from original {len(self.conversation) + len(recent_messages)} messages)"
        )

    async def _prepare_context(self) -> list[dict]:
        """Prepare conversation context with system prompt and truncation."""
        # Truncate conversation if needed
        self._truncate_conversation()
        
        # Use code-specific system prompt
        system_prompt = self._get_code_system_prompt()
        
        return [
            {"role": "system", "content": system_prompt},
            *self.conversation,
        ]

    def _get_code_system_prompt(self) -> str:
        """Get code-specific system prompt."""
        try:
            # Try to load code-specific prompt
            from sgr_deep_research.core.prompts import PromptLoader
            
            # Temporarily override the system prompt file
            original_file = config.prompts.system_prompt_file
            config.prompts.system_prompt_file = "code_system_prompt.txt"
            
            prompt = PromptLoader.get_system_prompt(self.toolkit)
            
            # Restore original
            config.prompts.system_prompt_file = original_file
            
            return prompt
        except Exception as e:
            self.logger.warning(f"Failed to load code_system_prompt.txt: {e}, using default")
            return PromptLoader.get_system_prompt(self.toolkit)

    async def _prepare_tools(self) -> list[ChatCompletionFunctionToolParam]:
        """Prepare available tools for current agent state and progress."""
        tools = set(self.toolkit)
        
        # At max iterations, force completion
        if self._context.iteration >= self.max_iterations:
            tools = {
                ReasoningTool,
                FinalAnswerTool,
            }
        
        # Limit clarifications
        if self._context.clarifications_used >= self.max_clarifications:
            tools -= {
                ClarificationTool,
            }
        
        return [pydantic_function_tool(tool, name=tool.tool_name, description="") for tool in tools]

    async def _reasoning_phase(self) -> ReasoningTool:
        """Reasoning phase with streaming support."""
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
        """Select and execute action tool."""
        async with self.openai_client.chat.completions.stream(
            model=config.openai.model,
            messages=await self._prepare_context(),
            max_tokens=config.openai.max_tokens,
            temperature=config.openai.temperature,
            tools=await self._prepare_tools(),
            tool_choice=self.tool_choice,
        ) as stream:
            async for event in stream:
                if event.type == "chunk":
                    self.streaming_generator.add_chunk(event.chunk)

        completion = await stream.get_final_completion()

        try:
            tool = completion.choices[0].message.tool_calls[0].function.parsed_arguments
        except (IndexError, AttributeError, TypeError):
            # LLM returned a text response instead of a tool call - treat as completion
            final_content = completion.choices[0].message.content or "Task completed successfully"
            tool = FinalAnswerTool(
                reasoning="Agent decided to complete the task",
                completed_steps=[final_content],
                answer=final_content,
                status=AgentStatesEnum.COMPLETED,
            )
        
        if not isinstance(tool, BaseTool):
            raise ValueError("Selected tool is not a valid BaseTool instance")
        
        self.conversation.append(
            {
                "role": "assistant",
                "content": reasoning.remaining_steps[0] if reasoning.remaining_steps else "Completing",
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

    async def continue_conversation(self, user_message: str):
        """Continue an existing conversation with a new user message.
        
        This method allows for continuous multi-turn dialogue without creating a new agent.
        """
        self.continuous_mode = True
        self.conversation.append({
            "role": "user",
            "content": user_message,
        })
        self._context.state = AgentStatesEnum.RESEARCHING
        self.logger.info(f"📝 Continuing conversation with: {user_message[:100]}...")

