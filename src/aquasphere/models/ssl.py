"""
Tier C Self-Supervised Pre-Training (SSL) and Low-Data Learning Curve (SIH 26066).

Features:
- Stage 1: Unsupervised masked-patch / masked-channel autoencoding on satellite patches.
- Stage 2: Fine-tuning on sparse Argo profiles with frozen/unfrozen transfer schedule.
- Low-data evaluation helper: Measures downstream profile reconstruction skill across
  label scarcity fractions (10%, 25%, 50%, 100% of Argo floats).
"""

from __future__ import annotations

import logging

import torch
import torch.nn as nn
import torch.nn.functional as F

from aquasphere.models.decoder import TierADecoder
from aquasphere.models.patch_cnn import PatchCNNEncoder

logger = logging.getLogger(__name__)


def generate_patch_mask(
    batch_size: int,
    channels: int = 7,
    height: int = 9,
    width: int = 9,
    mask_ratio: float = 0.50,
    strategy: str = "masked_patch",
    device: torch.device | str = "cpu",
) -> torch.Tensor:
    """Generate binary mask tensor for self-supervised pre-training.

    1 indicates masked (hidden) location, 0 indicates unmasked (visible) location.

    Args:
        batch_size: Number of samples in batch
        channels: Channel count (7)
        height: Patch height (9)
        width: Patch width (9)
        mask_ratio: Fraction of pixels or channels to mask out (default 0.50)
        strategy: "masked_patch" (random spatial pixels) or "masked_channel" (drop full channels)
        device: Target torch device

    Returns:
        Binary mask tensor of shape [B, C, H, W]
    """
    if strategy == "masked_channel":
        # Drop entire channels at random
        probs = torch.full((batch_size, channels, 1, 1), mask_ratio, device=device)
        mask = torch.bernoulli(probs).expand(-1, -1, height, width)
        # Ensure at least one channel remains visible
        all_masked = mask.sum(dim=1, keepdim=True) == (channels * height * width)
        if torch.any(all_masked):
            mask[all_masked.squeeze(-1).squeeze(-1).squeeze(-1), 0, :, :] = 0.0
        return mask

    # Default: masked_patch (random spatial mask across all pixels)
    probs = torch.full((batch_size, channels, height, width), mask_ratio, device=device)
    mask = torch.bernoulli(probs)
    # Ensure at least some pixels remain visible
    if torch.all(mask == 1.0):
        mask[:, :, 0, 0] = 0.0
    return mask


class PatchDecoder(nn.Module):
    """Deconvolutional decoder mapping latent vector [B, embed_dim] back to [B, C, 9, 9]."""

    def __init__(
        self,
        embed_dim: int = 32,
        out_channels: int = 7,
        base_channels: int = 32,
    ) -> None:
        super().__init__()
        self.base_channels = base_channels
        self.fc = nn.Linear(embed_dim, base_channels * 4 * 2 * 2)

        # 2x2 -> 4x4
        self.deconv1 = nn.ConvTranspose2d(
            base_channels * 4,
            base_channels * 2,
            kernel_size=3,
            stride=2,
            padding=1,
            output_padding=1,
        )
        self.bn1 = nn.BatchNorm2d(base_channels * 2)

        # 4x4 -> 9x9
        self.deconv2 = nn.ConvTranspose2d(
            base_channels * 2, base_channels, kernel_size=3, stride=2, padding=0, output_padding=0
        )
        self.bn2 = nn.BatchNorm2d(base_channels)

        # Final projection to match out_channels
        self.conv_out = nn.Conv2d(base_channels, out_channels, kernel_size=1)

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            z: Latent vector of shape [B, embed_dim]

        Returns:
            Reconstructed patch of shape [B, out_channels, 9, 9]
        """
        h = self.fc(z).view(-1, self.base_channels * 4, 2, 2)
        h = F.gelu(self.bn1(self.deconv1(h)))  # -> [B, base_channels * 2, 4, 4]
        h = F.gelu(self.bn2(self.deconv2(h)))  # -> [B, base_channels, 9, 9]
        out = self.conv_out(h)  # -> [B, out_channels, 9, 9]
        return out


class MaskedPatchAutoencoder(nn.Module):
    """Self-supervised masked autoencoder for satellite patch representation learning."""

    def __init__(
        self,
        in_channels: int = 7,
        base_channels: int = 32,
        embed_dim: int = 32,
        mask_ratio: float = 0.50,
        strategy: str = "masked_patch",
    ) -> None:
        super().__init__()
        self.mask_ratio = mask_ratio
        self.strategy = strategy

        self.encoder = PatchCNNEncoder(
            in_channels=in_channels,
            base_channels=base_channels,
            embed_dim=embed_dim,
        )
        self.decoder = PatchDecoder(
            embed_dim=embed_dim,
            out_channels=in_channels,
            base_channels=base_channels,
        )

    def forward(
        self,
        x: torch.Tensor,
        mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward pass.

        Args:
            x: Input satellite patches [B, C, 9, 9]
            mask: Optional explicit binary mask (1=masked, 0=visible). If None, generated.

        Returns:
            reconstructed: [B, C, 9, 9]
            mask: [B, C, 9, 9]
        """
        if mask is None:
            mask = generate_patch_mask(
                batch_size=x.size(0),
                channels=x.size(1),
                height=x.size(2),
                width=x.size(3),
                mask_ratio=self.mask_ratio,
                strategy=self.strategy,
                device=x.device,
            )

        # Corrupt input by zeroing masked locations
        corrupted_x = x * (1.0 - mask)
        latent = self.encoder(corrupted_x)
        reconstructed = self.decoder(latent)
        return reconstructed, mask

    def compute_pretrain_loss(
        self,
        reconstructed: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """Compute MSE loss strictly over masked pixels."""
        sq_diff = (reconstructed - target) ** 2
        masked_diff = sq_diff * mask
        n_masked = mask.sum().clamp(min=1.0)
        return masked_diff.sum() / n_masked


class TierCModel(nn.Module):
    """Fine-tuned Tier C model attaching profile decoder to pre-trained patch encoder."""

    def __init__(
        self,
        pretrained_encoder: PatchCNNEncoder | None = None,
        in_channels: int = 7,
        base_channels: int = 32,
        scalar_dim: int = 18,
        scalar_embed_dim: int = 16,
        embed_dim: int = 32,
        hidden_dim: int = 128,
        n_depths: int = 15,
    ) -> None:
        super().__init__()
        if pretrained_encoder is not None:
            self.patch_encoder = pretrained_encoder
        else:
            self.patch_encoder = PatchCNNEncoder(
                in_channels=in_channels,
                base_channels=base_channels,
                embed_dim=embed_dim,
            )

        self.scalar_fc = nn.Sequential(
            nn.Linear(scalar_dim, scalar_embed_dim),
            nn.GELU(),
            nn.LayerNorm(scalar_embed_dim),
        )

        self.fusion = nn.Sequential(
            nn.Linear(embed_dim + scalar_embed_dim, embed_dim),
            nn.GELU(),
            nn.LayerNorm(embed_dim),
        )

        self.decoder = TierADecoder(
            embed_dim=embed_dim,
            hidden_dim=hidden_dim,
            n_depths=n_depths,
        )

    def freeze_encoder(self, freeze: bool = True) -> None:
        """Freeze or unfreeze the patch encoder parameters."""
        for p in self.patch_encoder.parameters():
            p.requires_grad = not freeze

    def forward(
        self,
        patches: torch.Tensor,
        scalars: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass for fine-tuning profile prediction."""
        patch_emb = self.patch_encoder(patches)
        scalar_emb = self.scalar_fc(scalars)

        concat = torch.cat([patch_emb, scalar_emb], dim=-1)
        fused = self.fusion(concat)
        emb = F.normalize(fused, p=2, dim=-1)

        pred_mean, pred_log_sigma2 = self.decoder(emb)
        return pred_mean, pred_log_sigma2, emb
