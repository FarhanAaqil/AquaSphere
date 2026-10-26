"""
Encoder networks for AquaSphere satellite embedding learning (SIH 26066).

Learns compact 16-dimensional latent representation of multi-sensor surface fields.
Architecture:
    Linear(in_dim, hidden) -> GELU -> LayerNorm -> ResidualBlock -> Linear(hidden, embed_dim)
    -> L2 Normalisation (unit sphere embedding)
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class ResidualBlock(nn.Module):
    """Residual dense block with GELU activations and LayerNorm."""

    def __init__(self, dim: int, dropout: float = 0.05) -> None:
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.ln1 = nn.LayerNorm(dim)
        self.fc2 = nn.Linear(dim, dim)
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        h = F.gelu(self.fc1(x))
        h = self.ln1(h)
        h = self.drop(self.fc2(h))
        return residual + h


class TierAEncoder(nn.Module):
    """Tier A multi-sensor MLP encoder mapping surface inputs to 16-d latent embedding."""

    def __init__(
        self,
        input_dim: int = 18,
        hidden_dim: int = 128,
        embed_dim: int = 16,
        normalize_embed: bool = True,
        dropout: float = 0.05,
    ) -> None:
        super().__init__()
        self.normalize_embed = normalize_embed
        self.input_layer = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.GELU(),
            nn.LayerNorm(hidden_dim),
        )
        self.res_block = ResidualBlock(hidden_dim, dropout=dropout)
        self.proj = nn.Linear(hidden_dim, embed_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: [B, input_dim] input features (scalars + availability masks)

        Returns:
            emb: [B, embed_dim] L2-normalised latent embedding
        """
        h = self.input_layer(x)
        h = self.res_block(h)
        emb = self.proj(h)

        if self.normalize_embed:
            emb = F.normalize(emb, p=2.0, dim=-1)

        return emb
