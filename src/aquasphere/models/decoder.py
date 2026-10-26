"""
Decoder network and unified Tier A architecture for AquaSphere (SIH 26066).

Decodes 16-dimensional ocean embeddings into:
1. Subsurface temperature anomalies for 15 standard depths.
2. Heteroscedastic uncertainty (log_sigma2) for calibrated prediction intervals.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from aquasphere.models.encoder import ResidualBlock, TierAEncoder


class TierADecoder(nn.Module):
    """Tier A decoder mapping 16-d latent embedding to 15 depth mean and log-variance."""

    def __init__(
        self,
        embed_dim: int = 16,
        hidden_dim: int = 128,
        n_depths: int = 15,
        dropout: float = 0.05,
    ) -> None:
        super().__init__()
        self.n_depths = n_depths
        self.input_layer = nn.Sequential(
            nn.Linear(embed_dim, hidden_dim),
            nn.GELU(),
            nn.LayerNorm(hidden_dim),
        )
        self.res_block = ResidualBlock(hidden_dim, dropout=dropout)
        # Outputs: 15 mean temperature predictions + 15 log_sigma2 variance estimates
        self.head = nn.Linear(hidden_dim, n_depths * 2)

    def forward(self, emb: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward pass.

        Args:
            emb: [B, embed_dim]

        Returns:
            pred_mean: [B, 15] predicted anomaly temperatures
            pred_log_sigma2: [B, 15] predicted log variance
        """
        h = self.input_layer(emb)
        h = self.res_block(h)
        out = self.head(h)

        pred_mean = out[:, : self.n_depths]
        pred_log_sigma2 = out[:, self.n_depths :]
        return pred_mean, pred_log_sigma2


class TierAModel(nn.Module):
    """Unified Tier A Encoder-Decoder neural network."""

    def __init__(
        self,
        input_dim: int = 18,
        hidden_dim: int = 128,
        embed_dim: int = 16,
        n_depths: int = 15,
        normalize_embed: bool = True,
        dropout: float = 0.05,
    ) -> None:
        super().__init__()
        self.encoder = TierAEncoder(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            embed_dim=embed_dim,
            normalize_embed=normalize_embed,
            dropout=dropout,
        )
        self.decoder = TierADecoder(
            embed_dim=embed_dim,
            hidden_dim=hidden_dim,
            n_depths=n_depths,
            dropout=dropout,
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass.

        Args:
            x: [B, input_dim] input features

        Returns:
            (pred_mean, pred_log_sigma2, emb)
        """
        emb = self.encoder(x)
        pred_mean, pred_log_sigma2 = self.decoder(emb)
        return pred_mean, pred_log_sigma2, emb
