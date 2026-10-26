"""
Spatial-context Patch CNN Encoder and Tier B Model (SIH 26066).

Features:
- 3-block 2D CNN over 9x9xC satellite patches (C=7: sst, sss, sla, ug, vg, u10, v10).
- Auxiliary scalar feature projection (18-d scalars).
- Latent fusion layer producing L2-normalized spatial-temporal embeddings.
- Predicts 15-depth temperature mean and log-variance via Tier A decoder.
- Strictly capped parameter count (<= 300,000 params) for CPU training.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from aquasphere.models.decoder import TierADecoder


class PatchCNNEncoder(nn.Module):
    """3-block 2D CNN encoder mapping [B, C, 9, 9] spatial patches to latent vector."""

    def __init__(
        self,
        in_channels: int = 7,
        base_channels: int = 32,
        embed_dim: int = 32,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.embed_dim = embed_dim

        # Block 1: 9x9 -> 4x4
        self.conv1 = nn.Conv2d(in_channels, base_channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(base_channels)
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)  # 9 -> 4

        # Block 2: 4x4 -> 2x2
        self.conv2 = nn.Conv2d(base_channels, base_channels * 2, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(base_channels * 2)
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)  # 4 -> 2

        # Block 3: 2x2 -> 1x1
        self.conv3 = nn.Conv2d(base_channels * 2, base_channels * 4, kernel_size=2, padding=0)
        self.bn3 = nn.BatchNorm2d(base_channels * 4)

        self.proj = nn.Linear(base_channels * 4, embed_dim)
        self.ln = nn.LayerNorm(embed_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Satellite patch tensor of shape [B, C, 9, 9]

        Returns:
            Latent patch embedding of shape [B, embed_dim]
        """
        # Block 1
        h = F.gelu(self.bn1(self.conv1(x)))
        h = self.pool1(h)

        # Block 2
        h = F.gelu(self.bn2(self.conv2(h)))
        h = self.pool2(h)

        # Block 3
        h = F.gelu(self.bn3(self.conv3(h)))  # [B, 128, 1, 1]
        h = h.flatten(start_dim=1)

        out = self.ln(self.proj(h))
        return out


class TierBModel(nn.Module):
    """Tier B spatial context model combining 9x9 CNN patch features with scalar inputs."""

    def __init__(
        self,
        in_channels: int = 7,
        base_channels: int = 32,
        scalar_dim: int = 18,
        scalar_embed_dim: int = 16,
        embed_dim: int = 32,
        hidden_dim: int = 128,
        n_depths: int = 15,
        normalize_embed: bool = True,
    ) -> None:
        super().__init__()
        self.patch_encoder = PatchCNNEncoder(
            in_channels=in_channels,
            base_channels=base_channels,
            embed_dim=embed_dim,
        )

        # Scalar projection branch
        self.scalar_fc = nn.Sequential(
            nn.Linear(scalar_dim, scalar_embed_dim),
            nn.GELU(),
            nn.LayerNorm(scalar_embed_dim),
        )

        # Fusion layer
        self.fusion = nn.Sequential(
            nn.Linear(embed_dim + scalar_embed_dim, embed_dim),
            nn.GELU(),
            nn.LayerNorm(embed_dim),
        )

        self.normalize_embed = normalize_embed
        self.decoder = TierADecoder(
            embed_dim=embed_dim,
            hidden_dim=hidden_dim,
            n_depths=n_depths,
        )

    def forward(
        self,
        patches: torch.Tensor,
        scalars: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass.

        Args:
            patches: Tensor of shape [B, 7, 9, 9] (satellite spatial patch)
            scalars: Tensor of shape [B, 18] (satellite scalar features and masks)

        Returns:
            pred_mean: [B, 15] predicted temperature profiles
            pred_log_sigma2: [B, 15] predicted log variance
            embedding: [B, embed_dim] L2 normalized latent embedding
        """
        patch_emb = self.patch_encoder(patches)
        scalar_emb = self.scalar_fc(scalars)

        concat = torch.cat([patch_emb, scalar_emb], dim=-1)
        fused = self.fusion(concat)

        if self.normalize_embed:
            emb = F.normalize(fused, p=2, dim=-1)
        else:
            emb = fused

        pred_mean, pred_log_sigma2 = self.decoder(emb)
        return pred_mean, pred_log_sigma2, emb

    def count_parameters(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
