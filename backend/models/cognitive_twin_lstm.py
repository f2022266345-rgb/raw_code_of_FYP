"""
CognitiveTwinLSTM — PyTorch model for predicting student correctness.

Architecture matches the saved state dict in safe_cognitive_twin.pth:
  - skill_embeddings: Embedding(num_skills, skill_embed_dim)
  - lstm: 2-layer LSTM(input_dim, hidden_dim)
  - fc: Linear(hidden_dim, 1)

Input:
  num_feats  : (batch, seq_len, 4)  — [time_on_task, hints_used, attempt_count, cognitive_weight]
  skill_ids  : (batch, seq_len)     — integer skill identifiers

Output:
  (batch, seq_len, 1) — raw logits; apply sigmoid for probabilities
"""

import torch
import torch.nn as nn


class CognitiveTwinLSTM(nn.Module):
    def __init__(
        self,
        num_skills: int = 1005,
        skill_embed_dim: int = 16,
        num_features: int = 4,
        hidden_dim: int = 64,
    ):
        super().__init__()
        self.skill_embeddings = nn.Embedding(num_skills, skill_embed_dim, padding_idx=0)
        input_dim = num_features + skill_embed_dim
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=2, batch_first=True)
        self.fc = nn.Linear(hidden_dim, 1)

    def forward(self, num_feats: torch.Tensor, skill_ids: torch.Tensor) -> torch.Tensor:
        skill_embeds = self.skill_embeddings(skill_ids)
        x = torch.cat([num_feats, skill_embeds], dim=-1)
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out)
