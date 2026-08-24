"""Conversation history and context memory manager."""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Tuple


class MemoryManager:
    """Maintains in-memory short-term rolling buffers for active chat channels."""

    def __init__(self, max_history_per_pair: int = 8) -> None:
        self.max_history = max_history_per_pair
        # key: (player_name, bot_name) -> deque of {"role": "user"|"assistant", "content": "..."}
        self.buffers: Dict[Tuple[str, str], Deque[Dict[str, str]]] = {}

    def _get_key(self, player_name: str, bot_name: str) -> Tuple[str, str]:
        return (player_name.strip().lower(), bot_name.strip().lower())

    def get_history(self, player_name: str, bot_name: str) -> List[Dict[str, str]]:
        """Retrieve recent conversation turns for this player-bot context."""
        key = self._get_key(player_name, bot_name)
        if key not in self.buffers:
            return []
        return list(self.buffers[key])

    def add_user_turn(self, player_name: str, bot_name: str, message: str) -> None:
        """Record user input."""
        key = self._get_key(player_name, bot_name)
        if key not in self.buffers:
            self.buffers[key] = deque(maxlen=self.max_history)
        self.buffers[key].append({"role": "user", "content": message})

    def add_assistant_turn(self, player_name: str, bot_name: str, message: str) -> None:
        """Record bot reply."""
        key = self._get_key(player_name, bot_name)
        if key not in self.buffers:
            self.buffers[key] = deque(maxlen=self.max_history)
        self.buffers[key].append({"role": "assistant", "content": message})

    def clear(self, player_name: str, bot_name: str) -> None:
        """Reset short-term memory buffer for this pair."""
        key = self._get_key(player_name, bot_name)
        if key in self.buffers:
            self.buffers[key].clear()
